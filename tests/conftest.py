"""Fixtures use the real Home Assistant test framework, not stub HA modules."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.solark_local.const import DOMAIN
from custom_components.solark_local.protocol import decode_values

SERIAL = "TEST123456"
DATA = {"host": "192.0.2.10", "model": "18k_pv", "modbus_address": 1, "serial": SERIAL}


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def snapshot():
    registers = dict.fromkeys(range(79, 200), 0)
    registers.update(
        {
            79: 6000,
            150: 1200,
            151: 1201,
            152: 2401,
            172: 65375,
            182: 1250,
            183: 5560,
            184: 55,
            186: 100,
            187: 200,
            188: 300,
            190: 65526,
            191: 65534,
            193: 6000,
        }
    )
    return {
        "sample_started_at": "2026-10-23T12:00:00+00:00",
        "sample_completed_at": "2026-10-23T12:00:03+00:00",
        "registers": registers,
        "values": decode_values(registers),
    }


@pytest.fixture
def mock_client(snapshot):
    with (
        patch("custom_components.solark_local.ElinterClient", autospec=True) as setup,
        patch("custom_components.solark_local.config_flow.ElinterClient", autospec=True) as flow,
    ):
        client = setup.return_value
        client.host, client.address, client.model = DATA["host"], 1, "18k_pv"
        client.async_identify = AsyncMock(return_value=SERIAL)
        client.async_snapshot = AsyncMock(return_value=snapshot)
        flow.return_value = client
        yield client


@pytest.fixture
def entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="18K PV",
        unique_id=SERIAL,
        data=DATA,
        options={"pv_installed": True, "battery_installed": True},
    )
    entry.add_to_hass(hass)
    return entry
