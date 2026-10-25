"""UI setup, IP reconfiguration, and polling options."""

import logging

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import CannotConnect, ElinterClient, WrongInverter
from .const import (
    CONF_BATTERY_INSTALLED,
    CONF_GENERATOR_INSTALLED,
    CONF_GRID_IMPORT_NEGATIVE,
    CONF_GRID_SOURCE,
    CONF_MODBUS_ADDRESS,
    CONF_MODEL,
    CONF_POLL_INTERVAL,
    CONF_PV_INSTALLED,
    CONF_SERIAL,
    DEFAULT_ADDRESS,
    DEFAULT_GRID_SOURCE,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    MODEL_18K_PV,
)
from .protocol import MODEL_NAMES, ProtocolError, normalize_host
from .schema import vol

_LOGGER = logging.getLogger(__name__)


def setup_schema(defaults):
    fields = {
        vol.Required(CONF_MODEL, default=defaults.get(CONF_MODEL, MODEL_18K_PV)): SelectSelector(
            SelectSelectorConfig(
                options=list(MODEL_NAMES), translation_key="model", mode=SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): TextSelector(),
    }
    fields[vol.Optional("advanced")] = section(
        vol.Schema(
            {
                vol.Optional(
                    CONF_MODBUS_ADDRESS, default=defaults.get(CONF_MODBUS_ADDRESS, DEFAULT_ADDRESS)
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
                )
            }
        ),
        {"collapsed": True},
    )
    return vol.Schema(fields)


class SolarkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Validate local communication before storing an entry."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarkOptionsFlow()

    async def async_step_user(self, user_input=None):
        return await self._async_setup(user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._async_setup(user_input, self._get_reconfigure_entry())

    async def _async_setup(self, user_input, entry=None):
        errors = {}
        defaults = dict(entry.data) if entry else {}
        if user_input is not None:
            defaults.update(user_input)
            defaults.update(user_input.get("advanced", {}))
            try:
                host = normalize_host(user_input[CONF_HOST])
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            else:
                address = defaults.get(CONF_MODBUS_ADDRESS, DEFAULT_ADDRESS)
                model = user_input[CONF_MODEL]
                if model not in MODEL_NAMES:
                    errors[CONF_MODEL] = "unsupported_model"
                elif int(address) != address or not 1 <= address <= 247:
                    errors["base"] = "invalid_address"
                else:
                    # One entry per adapter; protect its serial link from duplicate polling.
                    for existing in self._async_current_entries():
                        if existing != entry and existing.data[CONF_HOST] == host:
                            return self.async_abort(reason="already_configured")
                    data = {CONF_HOST: host, CONF_MODEL: model, CONF_MODBUS_ADDRESS: int(address)}
                    try:
                        client = ElinterClient(
                            async_get_clientsession(self.hass), host, model, int(address)
                        )
                        # Share the existing client's lock during a same-address reconfiguration.
                        if entry and getattr(entry, "runtime_data", None):
                            current = entry.runtime_data.client
                            if (current.host, current.address, current.model) == (
                                host,
                                address,
                                model,
                            ):
                                client = current
                        serial = await client.async_identify()
                        if entry and serial != entry.unique_id:
                            errors["base"] = "wrong_inverter"
                        else:
                            await client.async_snapshot(expected_serial=serial)
                    except CannotConnect:
                        errors["base"] = "cannot_connect"
                    except ProtocolError:
                        errors["base"] = "invalid_response"
                    except WrongInverter:
                        errors["base"] = "wrong_inverter"
                    except Exception:
                        _LOGGER.exception("Unexpected error validating local inverter")
                        errors["base"] = "unknown"
                    else:
                        if not errors:
                            data[CONF_SERIAL] = serial
                            if entry:
                                return self.async_update_reload_and_abort(entry, data_updates=data)
                            await self.async_set_unique_id(serial)
                            self._abort_if_unique_id_configured()
                            return self.async_create_entry(
                                title=f"{MODEL_NAMES[model]} ({serial})", data=data
                            )
        return self.async_show_form(
            step_id="reconfigure" if entry else "user",
            data_schema=setup_schema(defaults),
            errors=errors,
        )


class SolarkOptionsFlow(OptionsFlowWithReload):
    """Changing polling frequency reloads the coordinator automatically."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            options = dict(self.config_entry.options)
            options.update(user_input)
            options[CONF_POLL_INTERVAL] = int(user_input[CONF_POLL_INTERVAL])
            return self.async_create_entry(title="", data=options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_POLL_INTERVAL,
                            max=MAX_POLL_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    **{
                        vol.Required(
                            key, default=self.config_entry.options.get(key, False)
                        ): BooleanSelector()
                        for key in (
                            CONF_BATTERY_INSTALLED,
                            CONF_PV_INSTALLED,
                            CONF_GENERATOR_INSTALLED,
                        )
                    },
                    vol.Required(
                        CONF_GRID_IMPORT_NEGATIVE,
                        default=self.config_entry.options.get(CONF_GRID_IMPORT_NEGATIVE, True),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_GRID_SOURCE,
                        default=self.config_entry.options.get(
                            CONF_GRID_SOURCE, DEFAULT_GRID_SOURCE
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["grid_ct_power", "grid_power"],
                            translation_key="grid_source",
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )
