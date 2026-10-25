from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.solark_local.api import CannotConnect
from custom_components.solark_local.const import DOMAIN
from custom_components.solark_local.protocol import ProtocolError

from .conftest import DATA, SERIAL


async def test_two_field_form_and_success(hass, mock_client):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    fields = {str(key): value for key, value in result["data_schema"].schema.items()}
    assert set(fields) == {"host", "model", "advanced"}
    assert fields["advanced"].options["collapsed"]
    with patch("custom_components.solark_local.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": DATA["host"], "model": "18k_pv"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == DATA
    assert result["result"].unique_id == SERIAL


@pytest.mark.parametrize(
    "error,expected",
    [
        (CannotConnect(), "cannot_connect"),
        (ProtocolError(), "invalid_response"),
        (RuntimeError(), "unknown"),
    ],
)
async def test_connection_errors(hass, mock_client, error, expected):
    mock_client.async_identify.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": DATA["host"], "model": "18k_pv"}
    )
    assert result["errors"] == {"base": expected}


async def test_invalid_ip_does_not_connect(hass, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": "http://192.0.2.1", "model": "18k_pv"}
    )
    assert result["errors"] == {"host": "invalid_host"}
    mock_client.async_identify.assert_not_awaited()


async def test_duplicate_ip_does_not_poll(hass, entry, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": DATA["host"], "model": "18k_pv"}
    )
    assert result["reason"] == "already_configured"
    mock_client.async_identify.assert_not_awaited()


async def test_duplicate_serial_at_other_ip(hass, entry, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={"host": "192.0.2.11", "model": "18k_pv"}
    )
    assert result["reason"] == "already_configured"


async def test_reconfigure_preserves_identity(hass, entry, mock_client):
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reconfigure", "entry_id": entry.entry_id},
            data={"host": "192.0.2.11", "model": "18k_pv"},
        )
        await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "192.0.2.11"
    assert entry.unique_id == SERIAL


async def test_reconfigure_rejects_other_inverter(hass, entry, mock_client):
    mock_client.async_identify.return_value = "OTHER12345"
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reconfigure", "entry_id": entry.entry_id},
        data={"host": "192.0.2.11", "model": "18k_pv"},
    )
    assert result["errors"] == {"base": "wrong_inverter"}
    assert entry.data == DATA


async def test_options_reloads_poll_interval(hass, entry, mock_client):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"poll_interval": 30}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["poll_interval"] == 30
    assert entry.runtime_data.interval == 30


async def test_advanced_modbus_address(hass, mock_client):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER, "show_advanced_options": True}
    )
    fields = {str(key): value for key, value in result["data_schema"].schema.items()}
    assert "modbus_address" in {str(key) for key in fields["advanced"].schema.schema}
    with patch("custom_components.solark_local.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"host": DATA["host"], "model": "18k_pv", "advanced": {"modbus_address": 2}},
        )
        await hass.async_block_till_done()
    assert result["data"]["modbus_address"] == 2


async def test_hardware_and_energy_options_reload(hass, entry, mock_client):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    options = {
        "poll_interval": 20,
        "battery_installed": False,
        "pv_installed": False,
        "generator_installed": False,
        "grid_source": "grid_power",
        "grid_import_negative": False,
    }
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(entry.options) == options
    assert entry.runtime_data.energy.options == options
