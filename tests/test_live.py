"""Explicitly opted-in read-only hardware test. Never runs in normal CI."""

import json
import os
from pathlib import Path

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_socket import socket_allow_hosts

from custom_components.solark_local.const import DOMAIN

pytestmark = [
    pytest.mark.skipif(not os.getenv("SOLARK_LIVE_HOST"), reason="No live adapter requested"),
    pytest.mark.usefixtures("socket_enabled"),
]


async def test_live_native_setup_and_poll(hass):
    socket_allow_hosts([os.environ["SOLARK_LIVE_HOST"]])
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={"host": os.environ["SOLARK_LIVE_HOST"], "model": "18k_pv"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    entry = result["result"]
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 17
    coordinator = entry.runtime_data
    assert coordinator.last_update_success
    before = coordinator.data["sample_completed_at"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.data["sample_completed_at"] != before
    assert coordinator.last_update_success
    energy = next(item for item in entities if item.unique_id.endswith("_grid_import_energy"))
    assert hass.states.get(energy.entity_id).state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)
    report = {
        "core_version": HA_VERSION,
        "native_entities": len(entities),
        "initial_sample": before,
        "latest_sample": coordinator.data["sample_completed_at"],
        "values": coordinator.data["values"],
    }
    if output := os.getenv("SOLARK_LIVE_REPORT"):
        Path(output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert await hass.config_entries.async_unload(entry.entry_id)
