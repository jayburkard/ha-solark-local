import asyncio
import json
import struct

import aiohttp
import pytest
from aiohttp import web

from custom_components.solark_local.api import CannotConnect, ElinterClient, WrongInverter
from custom_components.solark_local.protocol import ProtocolError, crc16

from .conftest import SERIAL

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.fixture
async def adapter_server(snapshot):
    calls = []
    mode = {"value": "normal"}

    async def handler(request):
        if mode["value"] == "timeout":
            await asyncio.sleep(0.1)
        if mode["value"] == "redirect":
            raise web.HTTPFound("/unexpected")
        if mode["value"] == "oversize":
            return web.Response(body=b"x" * 65537)
        if mode["value"] == "malformed":
            return web.json_response({"data": None})
        payload = await request.json()
        frame = bytes.fromhex(payload["data"])
        assert frame[1] == 3  # Every request must be read-only.
        assert crc16(frame[:-2]) == int.from_bytes(frame[-2:], "little")
        address, function, start, count = struct.unpack(">BBHH", frame[:-2])
        calls.append((start, count))
        if start == 3:
            data = SERIAL.encode()
        else:
            data = struct.pack(
                f">{count}H", *[snapshot["registers"][i] for i in range(start, start + count)]
            )
        body = bytes([address, 3, len(data)]) + data
        response = body + struct.pack("<H", crc16(body))
        if mode["value"] == "bad_crc":
            response = response[:-1] + bytes([response[-1] ^ 1])
        return web.Response(text=json.dumps({"data": response.hex(" ")}), content_type="text/plain")

    app = web.Application()
    app.router.add_post("/fdbg.cgi", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with aiohttp.ClientSession() as session:
            yield ElinterClient(session, "127.0.0.1", port=port, delay=0), mode, calls
    finally:
        await runner.cleanup()


async def test_full_http_read_and_serialization(adapter_server):
    client, mode, calls = adapter_server
    first, second = await asyncio.gather(
        client.async_snapshot(expected_serial=SERIAL), client.async_snapshot(expected_serial=SERIAL)
    )
    expected = [(3, 5), (79, 21), (100, 20), (120, 20), (140, 20), (160, 20), (180, 20)]
    assert calls == expected * 2
    assert first["values"]["battery_soc"] == second["values"]["battery_soc"] == 55
    assert first["values"]["pv_power"] == 600


async def test_wrong_serial_stops_before_measurements(adapter_server):
    client, mode, calls = adapter_server
    with pytest.raises(WrongInverter):
        await client.async_snapshot(expected_serial="OTHER12345")
    assert calls == [(3, 5)]


@pytest.mark.parametrize("value", ["redirect", "oversize", "malformed", "bad_crc"])
async def test_invalid_http_responses(adapter_server, value):
    client, mode, calls = adapter_server
    mode["value"] = value
    with pytest.raises(ProtocolError):
        await client.async_identify()


async def test_total_request_timeout(adapter_server):
    client, mode, calls = adapter_server
    mode["value"] = "timeout"
    client.timeout = aiohttp.ClientTimeout(total=0.01)
    with pytest.raises(CannotConnect):
        await client.async_identify()
