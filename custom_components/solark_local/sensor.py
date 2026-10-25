"""Native measurement sensors; no MQTT or inverter controls."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_BATTERY_INSTALLED, CONF_MODEL, CONF_PV_INSTALLED, DOMAIN
from .energy import ENERGY_KEYS
from .protocol import MODEL_NAMES, Sensor, sensor_definitions

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    """Create one device with the selected model's sensor definitions."""
    coordinator = entry.runtime_data
    definitions = list(sensor_definitions(entry.data[CONF_MODEL]))
    definitions.extend(
        Sensor(key, key.replace("_", " "), 0, "kWh", "energy", state_class="total_increasing")
        for key in ENERGY_KEYS
    )
    definitions = [
        definition
        for definition in definitions
        if (
            not definition.key.startswith("battery_")
            or entry.options.get(CONF_BATTERY_INSTALLED, False)
        )
        and (not definition.key.startswith("pv") or entry.options.get(CONF_PV_INSTALLED, False))
    ]
    async_add_entities(
        SolarkSensor(coordinator, definition, entry.data[CONF_MODEL]) for definition in definitions
    )


class SolarkSensor(CoordinatorEntity, SensorEntity):
    """A sensor backed by a shared validated snapshot."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, definition, model):
        super().__init__(coordinator)
        self.entity_description = SensorEntityDescription(
            key=definition.key,
            translation_key=definition.key,
            native_unit_of_measurement=definition.unit,
            device_class=SensorDeviceClass(definition.device_class),
            state_class=SensorStateClass(definition.state_class),
        )
        self._attr_unique_id = f"{coordinator.serial}_{definition.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.serial)},
            name=f"Sol-Ark {MODEL_NAMES[model]} {coordinator.serial[-4:]}",
            manufacturer="Sol-Ark",
            model=MODEL_NAMES[model],
            serial_number=coordinator.serial,
        )

    @property
    def native_value(self):
        """Return None for unsupported/missing measurements, never a fabricated zero."""
        return self.coordinator.data["values"].get(self.entity_description.key)
