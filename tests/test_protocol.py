import struct

import pytest

from custom_components.solark_local.protocol import (
    ProtocolError,
    crc16,
    decode_response,
    normalize_host,
    read_frame,
)


def response(payload):
    return payload + struct.pack("<H", crc16(payload))


def test_known_read_frame():
    assert read_frame(1, 3, 5).hex() == "01030003000575c9"


@pytest.mark.parametrize(
    "address,start,count", [(0, 3, 5), (1, -1, 5), (1, 65535, 2), (1, 0, 22), (1, 0, 0)]
)
def test_invalid_read_ranges(address, start, count):
    with pytest.raises(ValueError):
        read_frame(address, start, count)


@pytest.mark.parametrize(
    "frame",
    [
        b"\x01",
        response(bytes.fromhex("02 03 02 00 64")),
        response(bytes.fromhex("01 04 02 00 64")),
        response(bytes.fromhex("01 03 04 00 64 00 64")),
        response(bytes.fromhex("01 83 02")),
        b"\x01\x03\x02\x00\x64\x00\x00",
    ],
)
def test_bad_modbus_responses(frame):
    with pytest.raises(ProtocolError):
        decode_response(frame, 1, 1)


@pytest.mark.parametrize(
    "host",
    ["http://192.0.2.1", "192.0.2.1:80", "host/path", "0.0.0.0", "224.0.0.1", "user@192.0.2.1"],
)
def test_bad_hosts(host):
    with pytest.raises(ValueError):
        normalize_host(host)


def test_model_decoding(snapshot):
    values = snapshot["values"]
    assert values["battery_soc"] == 55
    assert values["grid_ct_power"] == -1610
    assert values["battery_power"] == 10
    assert values["battery_current"] == 0.02
    assert values["pv_power"] == 600
    assert values["battery_temperature"] == 25
