"""Read-only protocol and model-specific register definitions; no Home Assistant dependency."""

import ipaddress
import struct
from dataclasses import dataclass

from .const import MODEL_18K_PV


def normalize_host(value: str) -> str:
    """Accept an IP address, without a scheme, port, credentials, or URL path."""
    address = ipaddress.ip_address(value.strip())
    if address.is_unspecified or address.is_multicast:
        raise ValueError("Enter a unicast IP address")
    return str(address)


class ProtocolError(Exception):
    pass


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def read_frame(address, start, count):
    # There is deliberately no function-code argument or raw-command interface.
    if not 1 <= address <= 247 or not 1 <= count <= 21 or not 0 <= start <= 65536 - count:
        raise ValueError("Invalid read range/address (maximum 21 registers per request)")
    frame = struct.pack(">BBHH", address, 3, start, count)
    return frame + struct.pack("<H", crc16(frame))


def decode_response(frame, address, count):
    if len(frame) < 5:
        raise ProtocolError("Truncated Modbus response")
    if crc16(frame[:-2]) != int.from_bytes(frame[-2:], "little"):
        raise ProtocolError("Modbus CRC mismatch")
    if frame[0] != address:
        raise ProtocolError("Wrong Modbus address")
    if frame[1] == 0x83:
        raise ProtocolError(f"Modbus read exception {frame[2]}")
    if frame[1] != 3 or frame[2] != count * 2 or len(frame) != count * 2 + 5:
        raise ProtocolError("Wrong function, byte count, or response length")
    return list(struct.unpack(f">{count}H", frame[3:-2]))


@dataclass(frozen=True)
class Sensor:
    key: str
    name: str
    register: int
    unit: str
    device_class: str
    scale: float = 1
    signed: bool = False
    offset: float = 0
    state_class: str = "measurement"


# Base map: pbix/HA-solark-PV and kellerza/sunsynk; grid power x10 verified on this 18k.
# Only the subset corroborated by reference telemetry is published. No inverter controls.
SENSORS = [
    Sensor("grid_frequency", "Grid frequency", 79, "Hz", "frequency", 0.01),
    Sensor("grid_voltage_l1", "Grid L1 voltage", 150, "V", "voltage", 0.1),
    Sensor("grid_voltage_l2", "Grid L2 voltage", 151, "V", "voltage", 0.1),
    Sensor("grid_voltage", "Grid L1-L2 voltage", 152, "V", "voltage", 0.1),
    Sensor("inverter_voltage_l1", "Inverter L1 voltage", 154, "V", "voltage", 0.1),
    Sensor("inverter_voltage_l2", "Inverter L2 voltage", 155, "V", "voltage", 0.1),
    Sensor("inverter_voltage", "Inverter L1-L2 voltage", 156, "V", "voltage", 0.1),
    Sensor("grid_power_l1", "Grid internal L1 power", 167, "W", "power", 10, True),
    Sensor("grid_power_l2", "Grid internal L2 power", 168, "W", "power", 10, True),
    Sensor("grid_power", "Grid internal total power", 169, "W", "power", 10, True),
    Sensor("grid_ct_power_l1", "Grid CT L1 power", 170, "W", "power", 10, True),
    Sensor("grid_ct_power_l2", "Grid CT L2 power", 171, "W", "power", 10, True),
    Sensor("grid_ct_power", "Grid CT total power", 172, "W", "power", 10, True),
    Sensor("inverter_power", "Inverter power", 175, "W", "power", signed=True),
    Sensor(
        "battery_temperature", "Battery temperature", 182, "°C", "temperature", 0.1, offset=-100
    ),
    Sensor("battery_voltage", "Battery voltage", 183, "V", "voltage", 0.01),
    Sensor("battery_soc", "Battery state of charge", 184, "%", "battery"),
    Sensor("battery_power", "Battery power (positive charging)", 190, "W", "power", -1, True),
    Sensor(
        "battery_current", "Battery current (positive charging)", 191, "A", "current", -0.01, True
    ),
    Sensor("inverter_frequency", "Inverter frequency", 193, "Hz", "frequency", 0.01),
]
for number in range(1, 4):
    SENSORS.extend(
        [
            Sensor(
                f"pv{number}_voltage", f"PV{number} voltage", 107 + 2 * number, "V", "voltage", 0.1
            ),
            Sensor(
                f"pv{number}_current", f"PV{number} current", 108 + 2 * number, "A", "current", 0.1
            ),
            Sensor(f"pv{number}_power", f"PV{number} power", 185 + number, "W", "power"),
        ]
    )


MODEL_NAMES = {MODEL_18K_PV: "18K PV"}
MODEL_SENSORS = {MODEL_18K_PV: tuple(SENSORS)}
READ_RANGES = ((79, 21), (100, 20), (120, 20), (140, 20), (160, 20), (180, 20))


def sensor_definitions(model):
    return MODEL_SENSORS[model] + (Sensor("pv_power", "PV total power", 0, "W", "power"),)


def decode_values(registers, model=MODEL_18K_PV):
    values = {}
    for sensor in MODEL_SENSORS[model]:
        raw = registers[sensor.register]
        if sensor.device_class == "temperature" and raw == 0:
            values[sensor.key] = None
            continue
        value = raw - 65536 if sensor.signed and raw & 0x8000 else raw
        values[sensor.key] = round(value * sensor.scale + sensor.offset, 3)
    values["pv_power"] = sum(values[f"pv{number}_power"] for number in range(1, 4))
    return values
