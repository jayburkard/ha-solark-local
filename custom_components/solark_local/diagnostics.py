"""Downloadable diagnostics with IP and inverter identity removed."""

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST

from .const import CONF_SERIAL


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "configuration": async_redact_data(dict(entry.data), {CONF_HOST, CONF_SERIAL}),
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "consecutive_failures": coordinator.failures,
        "snapshot": coordinator.data,
    }
