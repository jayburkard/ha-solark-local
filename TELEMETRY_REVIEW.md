# Telemetry coverage review — October 23, 2026

## Conclusion

Version 0.1.0 exposed thirty native measurements, covering a subset of the
observed telemetry. Version 0.2.0 adds estimated energy
totals for Home Assistant and hardware-presence options. Several live fields still
need model-specific validation; adding guessed register formulas would not close
those gaps reliably.

The validation system had **no PV, generator or battery connected**. The recorded
comparisons of those channels establish only what the inverter reports when
disconnected. They do not validate actual PV generation, battery SOC/current/power,
or generator power under load.

## Evidence reviewed

- Original 204-second packet capture: all 128 Modbus request/response pairs pass
  the native integration's frame and CRC checks.
- The capture's six recurring blocks cover registers 79–199, exactly the range
  acquired by the native integration. Other startup/settings reads are not all
  repeated by the native integration.
- A fresh read-only MQTT inventory contained 131 topics: 111 inverter topics,
  six battery topics, three aggregate topics, five weather topics, five host/system
  topics, and availability.
- A forty-second passive observation received 1,267 non-retained state messages.
  Replaying 100 recorded register snapshots through the native protocol code
  reproduced the recorded decoded values.
- Near-time comparisons of existing grid/inverter readings show no obvious
  factor-of-ten regression. They are not synchronized calibration measurements:
  pairing skew reached 9.2 seconds and CT demand changed during observation.

## Coverage inventory

| Category | Finding |
| --- | --- |
| Grid voltage, frequency, internal power, CT power | Covered, including per-leg voltages and powers |
| Inverter voltage, frequency and total power | Covered |
| Three PV inputs: voltage/current/power, total power | Implemented; real generation scaling unvalidated; hardware option defaults off |
| Battery voltage/current/power/SOC/temperature | Implemented; no installed battery to validate; hardware option defaults off |
| Grid import/export energy | Added in 0.2.0 as persistent estimates |
| PV and battery directional energy | Added in 0.2.0, conditional on installed hardware; depend on unvalidated loaded power channels |
| Generator power | Missing; disconnected generator cannot establish scaling |
| Total, essential and non-essential load power | Missing; mode/topology-dependent derivation unvalidated |
| Load percentage | Missing; depends on validated load power and rated-power basis |
| Inverter temperature | Missing; generic temperature formula conflicts with observed data |
| Device mode | Missing; reference telemetry includes a derived description such as a discharge threshold |
| Battery capacity metadata | Missing; reference telemetry reports 200, while generic corrected-capacity register 107 reports 202; not proof of a physical battery |
| Grid-connected status, faults, inverter per-leg currents/power | Potential additional telemetry in existing register blocks; not established as missing from the observed live-topic inventory |
| Settings readbacks | 75 observed fields, such as time-of-use, charge limits and mode settings, are not entities; read-only presentation could be added separately from controls |
| Serial number | Represented as native device identity metadata |
| Single-device aggregate duplicates | Three battery aggregate topics repeat measurements already represented; separate duplicate entities are unnecessary |
| Weather/forecast and CPU/memory/storage/version | Service/host data, not telemetry extracted from this inverter |

The observed inverter MQTT inventory contains **seven missing live fields**:
`load_power`, `load_power_essential`, `load_power_non-essential`, `load_percentage`,
`generator_power`, `temperature`, and `device_mode`.
Twenty-eight inverter topics and five battery topics map to thirty unique existing
sensor keys because several topics are aliases. In particular, `grid_power` and
`grid_power_ld` agree in the observed mode; equivalence in all modes is not proven.

## Important interpretation and validation findings

### Disconnected battery values are not physical battery telemetry

The inverter reports 100% SOC, roughly 55.6 V, 25 °C, and small power/current values
despite the absence of a battery. The reference telemetry contains the same values. A
numeric match is therefore insufficient evidence of a real measurement. Version
0.2.0 omits battery entities by default and does not accumulate battery energy until
the installed-battery option is explicitly enabled. PV entities are treated
similarly. Existing disabled entities retain history and become unavailable.

### Energy dashboard support needs explicit semantics

No energy totals were found in this particular MQTT observation. The integration's
energy estimates should not be confused with inverter lifetime counters.

The new implementation supplies five separate, increasing **estimated** kWh totals,
with Home Assistant energy metadata, persistence and gap handling. It integrates
power locally and does not claim to decode hardware counters. Grid CT polarity and
measurement location are configurable; internal grid-port power is not necessarily
whole-property grid consumption. Changing those choices does not repair history.

Generic register references suggest energy counters below 79 and at 84–86, 96–97,
and 108. This capture does **not** read 60–78. Values in the other candidate counters
were largely zero or constant, so counter width, word order, scaling, reset and
rollover behavior remain unvalidated on the 18K PV. The references also differ on
some counter widths. Hardware counters should not be enabled from those references
alone. A future validated counter could recover energy across polling outages,
which software integration cannot do.

### Temperature is a promising candidate, not yet a verified sensor

Older samples have register 90 = 724 with a reference temperature of 162.3; newer
samples have about 733 with a reference temperature of 163.9. Interpreting the MQTT
temperature as Fahrenheit yields about 72.4 and 73.3 °C, consistent with register 90
times 0.1 without an offset. Generic Deye references instead use an offset on
temperature registers. The physical temperature source and display-unit assumption
still need confirmation against the inverter display; blindly copying the generic
formula would produce a substantially different result.

### Load and generator need nonzero operating evidence

At idle, observed load power is close to the sum of inverter power and internal
grid power. Generic load register 178 does not match those values directly. Near-zero
agreement cannot distinguish alternative topology-dependent formulas or confirm
generator sign/scale. Essential versus non-essential loads must be checked while
known loads change; generator mapping needs a separately observed nonzero case.
The generator-presence option records topology only until metering is supported.

### Sampling and statistics

The reference capture's block update median is approximately 6.95–6.96 seconds.
The native integration defaults to a 15-second configured interval, plus acquisition
time; it is therefore not equivalent in time resolution. Faster changes can be
missed, and power-derived energy is approximate. A failed block invalidates the
whole snapshot; recovery checks identity, and energy does not bridge the outage.
The new entities honor each definition's state class instead of hardcoding
`measurement`, allowing energy totals to use `total_increasing`.

## Next validation priorities

1. Verify grid import polarity and CT measurement location against the display or
   known consumption; compare the accumulated energy over a measured interval.
2. Confirm inverter temperature units and physical sensor source on the display.
3. Observe changing known loads to establish essential/non-essential load formulas.
4. Once commissioned, validate PV voltage/current/power at meaningful output and
   battery current/power in both directions before relying on their energy totals.
5. Validate generator telemetry when connected; add grid-connected/fault/status
   entities and hardware energy counters only with model-specific evidence.

References used as candidate mappings, not authoritative 18K validation:
[Sol-Ark community register map](https://github.com/pbix/HA-solark-PV/blob/main/custom_components/solark/solark_register_map.py),
[Sunsynk single-phase map](https://github.com/kellerza/sunsynk/blob/main/src/sunsynk/definitions/single_phase.py),
[Deye 16kW scaling](https://github.com/kellerza/sunsynk/blob/main/src/sunsynk/definitions/single_phase_16kw.py).
Energy behavior follows [HA sensor metadata](https://contributors.home-assistant.io/core/entities/sensor/)
and the same left-rectangle estimation concept supported by
[HA's Integral helper](https://www.home-assistant.io/integrations/integration/).
