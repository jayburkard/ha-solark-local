"""Energy accounting, persistence and hardware-presence regression tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.solark_local.energy import EnergyAccumulator


def sample(seconds, grid=-3600, battery=1800, pv=7200):
    return {
        "sample_completed_at": (
            datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)
        ).isoformat(),
        "values": {
            "grid_ct_power": grid,
            "grid_power": 100,
            "battery_power": battery,
            "pv_power": pv,
        },
    }


def accumulator(hass, entry):
    energy = EnergyAccumulator(hass, entry, 15)
    energy.store = Mock(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
    return energy


async def test_direction_units_and_left_rectangles(hass, entry):
    energy = accumulator(hass, entry)
    assert energy.update(sample(0))["grid_import_energy"] == 0
    result = energy.update(sample(30, grid=3600, battery=-1800))
    assert result["grid_import_energy"] == 0.03
    assert result["grid_export_energy"] == 0
    assert result["battery_charge_energy"] == 0.015
    assert result["pv_energy"] == 0.06
    result = energy.update(sample(60))
    assert result["grid_export_energy"] == 0.03
    assert result["battery_discharge_energy"] == 0.015


@pytest.mark.parametrize("elapsed", [0, -1, 43, 3600])
async def test_invalid_time_gaps_do_not_accumulate(hass, entry, elapsed):
    energy = accumulator(hass, entry)
    energy.update(sample(100))
    assert energy.update(sample(100 + elapsed))["grid_import_energy"] == 0


async def test_failed_poll_breaks_continuity(hass, entry):
    energy = accumulator(hass, entry)
    energy.update(sample(0))
    energy.break_continuity()
    assert energy.update(sample(30))["grid_import_energy"] == 0
    assert energy.update(sample(60))["grid_import_energy"] == 0.03


async def test_restore_does_not_integrate_downtime(hass, entry):
    energy = accumulator(hass, entry)
    energy.update(sample(0))
    energy.update(sample(30))
    await energy.async_save()
    restored = accumulator(hass, entry)
    restored.store.async_load.return_value = energy.store.async_save.call_args.args[0]
    await restored.async_load()
    assert restored.update(sample(3600))["grid_import_energy"] == 0.03
    assert restored.update(sample(3630))["grid_import_energy"] == 0.06


@pytest.mark.parametrize("invalid", [-1, float("nan"), float("inf"), "4", True])
async def test_invalid_storage_is_not_silently_reset(hass, entry, invalid):
    energy = accumulator(hass, entry)
    saved = energy._data()
    saved["totals"]["grid_import_energy"] = invalid
    energy.store.async_load.return_value = saved
    with pytest.raises(ValueError):
        await energy.async_load()


async def test_alternate_source_and_polarity(hass, entry):
    hass.config_entries.async_update_entry(
        entry, options={"grid_source": "grid_power", "grid_import_negative": False}
    )
    energy = accumulator(hass, entry)
    energy.update(sample(0))
    result = energy.update(sample(36))
    assert result["grid_import_energy"] == 0.001
    assert result["pv_energy"] == result["battery_charge_energy"] == 0


async def test_no_connected_equipment_and_energy_metadata(hass, entry, mock_client):
    hass.config_entries.async_update_entry(entry, options={})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 17
    assert not any("battery_" in item.unique_id or "_pv" in item.unique_id for item in entities)
    energy = next(item for item in entities if item.unique_id.endswith("grid_import_energy"))
    state = hass.states.get(energy.entity_id)
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["state_class"] == "total_increasing"
    assert "estimated" in state.name.lower()


async def test_coordinator_checkpoints_each_published_total(hass, entry, mock_client, snapshot):
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = entry.runtime_data
    later = dict(snapshot)
    later["sample_completed_at"] = "2026-10-23T12:00:33+00:00"
    mock_client.async_snapshot.return_value = later
    await coordinator.async_refresh()
    saved = await coordinator.energy.store.async_load()
    assert saved["totals"]["grid_import_energy"] == pytest.approx(1610 * 30 / 3_600_000)
    assert coordinator.data["values"]["grid_import_energy"] == round(
        saved["totals"]["grid_import_energy"], 6
    )


async def test_unload_reload_preserves_totals_and_disabling_hardware(
    hass, entry, mock_client, snapshot
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    coordinator.energy.totals["grid_import_energy"] = 12.3456789
    coordinator.energy.totals["battery_charge_energy"] = 4.5
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.config_entries.async_update_entry(
        entry, options={"battery_installed": False, "pv_installed": False}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.energy.totals["grid_import_energy"] == 12.3456789
    assert entry.runtime_data.energy.totals["battery_charge_energy"] == 4.5
    # Removed entities retain their registry/history; they no longer report fake measurements.
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    battery = next(item for item in entities if item.unique_id.endswith("battery_soc"))
    assert hass.states.get(battery.entity_id).state == "unavailable"
