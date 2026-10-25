"""One shared polling cycle for all inverter sensors."""

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CannotConnect, ElinterClient, WrongInverter
from .const import CONF_POLL_INTERVAL, CONF_SERIAL, DEFAULT_POLL_INTERVAL, DOMAIN
from .energy import EnergyAccumulator
from .protocol import ProtocolError

_LOGGER = logging.getLogger(__name__)


class SolarkCoordinator(DataUpdateCoordinator):
    """Mark all sensors unavailable together when a complete snapshot fails."""

    def __init__(self, hass, entry, client: ElinterClient):
        self.client = client
        self.serial = entry.data[CONF_SERIAL]
        self.interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        self.failures = 0
        self._verify_identity = True
        self.energy = EnergyAccumulator(hass, entry, self.interval)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=self.interval),
        )

    async def _async_update_data(self):
        try:
            snapshot = await self.client.async_snapshot(
                expected_serial=self.serial if self._verify_identity else None
            )
        except (CannotConnect, ProtocolError, WrongInverter) as error:
            self.energy.break_continuity()
            self.failures += 1
            self._verify_identity = True
            self.update_interval = timedelta(
                seconds=min(max(120, self.interval), self.interval * 2 ** min(self.failures, 3))
            )
            raise UpdateFailed(str(error)) from error
        self.failures = 0
        self._verify_identity = False
        self.update_interval = timedelta(seconds=self.interval)
        snapshot["values"].update(self.energy.update(snapshot))
        # Checkpoint before exposing totals so an ordinary process crash cannot
        # roll them back to an older delayed checkpoint and look like a meter reset.
        await self.energy.async_save()
        return snapshot
