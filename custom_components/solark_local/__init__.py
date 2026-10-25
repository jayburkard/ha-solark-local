"""Sol-Ark Local: native Home Assistant access through the factory adapter."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ElinterClient
from .const import CONF_MODBUS_ADDRESS, CONF_MODEL, DEFAULT_ADDRESS, DOMAIN
from .coordinator import SolarkCoordinator

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Validate the inverter before adding native entities."""
    client = ElinterClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_MODEL],
        entry.data.get(CONF_MODBUS_ADDRESS, DEFAULT_ADDRESS),
    )
    coordinator = SolarkCoordinator(hass, entry, client)
    await coordinator.energy.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove listeners so the coordinator stops polling."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.energy.async_save()
    return unloaded
