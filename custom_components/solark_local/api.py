"""Asynchronous, read-only access to the factory E-Linter adapter."""

import asyncio
import json
import struct
from datetime import UTC, datetime

import aiohttp

from .const import DEFAULT_ADDRESS, MODEL_18K_PV
from .protocol import (
    MODEL_SENSORS,
    READ_RANGES,
    ProtocolError,
    decode_response,
    decode_values,
    normalize_host,
    read_frame,
)


class CannotConnect(Exception):
    """The adapter could not be reached."""


class WrongInverter(Exception):
    """The configured address now points to a different inverter."""


class ElinterClient:
    """Use an injected HA session; serialize complete transactions for this client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        model=MODEL_18K_PV,
        address=DEFAULT_ADDRESS,
        *,
        port=80,
        delay=0.3,
        timeout=6,
    ):
        self.host = normalize_host(host)
        if model not in MODEL_SENSORS:
            raise ValueError("Unsupported model")
        read_frame(address, 3, 5)  # Validate the address before any I/O.
        self.model, self.address = model, address
        self.session, self.delay = session, delay
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        authority = f"[{self.host}]" if ":" in self.host else self.host
        self.url = f"http://{authority}:{port}/fdbg.cgi"
        self._lock = asyncio.Lock()

    async def _read(self, start, count):
        frame = read_frame(self.address, start, count)
        payload = json.dumps({"data": frame.hex(" ").upper()}, separators=(",", ":"))
        try:
            async with self.session.post(
                self.url,
                data=payload,
                headers={"Content-Type": "application/octet-stream", "Connection": "close"},
                timeout=self.timeout,
                allow_redirects=False,
            ) as response:
                if response.status != 200:
                    raise ProtocolError(f"Adapter HTTP status {response.status}")
                body = bytearray()
                async for chunk in response.content.iter_chunked(4096):
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ProtocolError("Oversized adapter response")
                try:
                    result = json.loads(body)
                    frame = bytes.fromhex(result["data"])
                except (ValueError, KeyError, TypeError) as error:
                    raise ProtocolError("Invalid adapter response") from error
                return decode_response(frame, self.address, count)
        except (aiohttp.ClientError, TimeoutError) as error:
            raise CannotConnect("Could not communicate with the local adapter") from error
        finally:
            await asyncio.sleep(self.delay)

    async def _serial(self):
        words = await self._read(3, 5)
        try:
            serial = struct.pack(">5H", *words).decode("ascii").strip("\x00 ")
        except UnicodeError as error:
            raise ProtocolError("Invalid inverter serial") from error
        if not serial.isalnum():
            raise ProtocolError("Invalid inverter serial")
        return serial

    async def async_identify(self):
        """Read identity without relying on the adapter registration key."""
        async with self._lock:
            return await self._serial()

    async def async_snapshot(self, expected_serial=None):
        """Read the captured register ranges and optionally verify device identity."""
        async with self._lock:
            started = datetime.now(UTC).isoformat()
            if expected_serial and await self._serial() != expected_serial:
                raise WrongInverter("The inverter serial number has changed")
            registers = {}
            for start, count in READ_RANGES:
                registers.update(zip(range(start, start + count), await self._read(start, count)))
            values = decode_values(registers, self.model)
            if not 0 <= values["battery_soc"] <= 100:
                raise ProtocolError("Battery SOC outside 0-100; incompatible register data")
            return {
                "sample_started_at": started,
                "sample_completed_at": datetime.now(UTC).isoformat(),
                "values": values,
                "registers": registers,
            }
