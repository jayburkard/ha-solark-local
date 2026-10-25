"""Persistent energy estimates from adjacent, successful power samples."""

import math
from datetime import datetime

from homeassistant.helpers.storage import Store

from .const import (
    CONF_BATTERY_INSTALLED,
    CONF_GRID_IMPORT_NEGATIVE,
    CONF_GRID_SOURCE,
    CONF_PV_INSTALLED,
    DEFAULT_GRID_SOURCE,
    DOMAIN,
)

ENERGY_KEYS = (
    "grid_import_energy",
    "grid_export_energy",
    "pv_energy",
    "battery_charge_energy",
    "battery_discharge_energy",
)


class EnergyAccumulator:
    """Use left rectangles; never bridge restarts, errors, or excessive gaps.

    Totals are estimates since installation, not the inverter's hardware counters.
    Store the full precision total, rounding only the exposed entity value.
    """

    def __init__(self, hass, entry, interval):
        self.options = entry.options
        self.interval = interval
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.energy")
        self.totals = dict.fromkeys(ENERGY_KEYS, 0.0)
        self.previous = None

    async def async_load(self):
        if (saved := await self.store.async_load()) is not None:
            # A corrupt total must not silently restart at zero and inflate statistics.
            for key in ENERGY_KEYS:
                value = saved["totals"][key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Invalid stored energy total")
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid stored energy total")
                self.totals[key] = value

    def break_continuity(self):
        self.previous = None

    def powers(self, values):
        grid = values[self.options.get(CONF_GRID_SOURCE, DEFAULT_GRID_SOURCE)]
        if self.options.get(CONF_GRID_IMPORT_NEGATIVE, True):
            grid = -grid
        result = {"grid_import_energy": max(grid, 0), "grid_export_energy": max(-grid, 0)}
        if self.options.get(CONF_PV_INSTALLED, False):
            result["pv_energy"] = max(values["pv_power"], 0)
        if self.options.get(CONF_BATTERY_INSTALLED, False):
            battery = values["battery_power"]  # Positive charging in the model profile.
            result["battery_charge_energy"] = max(battery, 0)
            result["battery_discharge_energy"] = max(-battery, 0)
        return result

    def update(self, snapshot):
        timestamp = datetime.fromisoformat(snapshot["sample_completed_at"]).timestamp()
        powers = self.powers(snapshot["values"])
        if not math.isfinite(timestamp) or not all(math.isfinite(v) for v in powers.values()):
            self.break_continuity()
            raise ValueError("Non-finite energy sample")
        if self.previous is not None:
            previous_time, previous_powers = self.previous
            elapsed = timestamp - previous_time
            # Includes normal six-request acquisition time, but excludes long outages.
            if 0 < elapsed <= 2 * self.interval + 12:
                for key, power in previous_powers.items():
                    self.totals[key] += power * elapsed / 3_600_000
        self.previous = (timestamp, powers)
        return {key: round(value, 6) for key, value in self.totals.items()}

    def _data(self):
        return {"totals": dict(self.totals)}

    async def async_save(self):
        await self.store.async_save(self._data())
