import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er

from custom_components.solark_local.api import CannotConnect, WrongInverter
from custom_components.solark_local.diagnostics import async_get_config_entry_diagnostics

from .conftest import DATA, SERIAL


async def test_entities_unavailability_recovery_and_unload(hass, entry, mock_client, snapshot):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 35
    soc = next(entity for entity in entities if entity.unique_id == f"{SERIAL}_battery_soc")
    assert hass.states.get(soc.entity_id).state == "55"
    assert hass.states.get(soc.entity_id).attributes["device_class"] == "battery"
    coordinator = entry.runtime_data
    mock_client.async_snapshot.side_effect = CannotConnect("offline")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert all(hass.states.get(entity.entity_id).state == STATE_UNAVAILABLE for entity in entities)
    assert coordinator.update_interval.total_seconds() == 30
    mock_client.async_snapshot.side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    mock_client.async_snapshot.assert_awaited_with(expected_serial=SERIAL)
    assert hass.states.get(soc.entity_id).state == "55"
    assert coordinator.update_interval.total_seconds() == 15
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not coordinator._listeners
    # HA retains an unavailable restored state for registry entities after unload.
    assert hass.states.get(soc.entity_id).state == STATE_UNAVAILABLE


async def test_startup_offline_retries(hass, entry, mock_client):
    mock_client.async_snapshot.side_effect = CannotConnect("offline")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_wrong_serial_never_exposes_readings(hass, entry, mock_client):
    mock_client.async_snapshot.side_effect = WrongInverter("serial changed")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert not er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


async def test_diagnostics_redaction(hass, entry, mock_client):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    encoded = json.dumps(diagnostics)
    assert DATA["host"] not in encoded
    assert SERIAL not in encoded
    assert diagnostics["snapshot"]["values"]["battery_soc"] == 55
