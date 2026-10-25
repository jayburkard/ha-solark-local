# Changelog

## 0.2.0

- Energy dashboard compatible kWh estimates for grid import/export, PV production,
  and battery charge/discharge, with persistent totals and outage-gap handling.
- Hardware options suppress PV and battery entities when disconnected; both default
  off, including upgrades. Existing entity history and totals remain available.
- Grid measurement-point and import-polarity options.
- Generator presence option records topology; generator metering remains unsupported.
- Telemetry coverage review identifies remaining load, temperature, status, and
  hardware-counter gaps that still need model-specific validation.

## 0.1.0

- Native read-only sensors for the Sol-Ark 18K PV factory E-Linter adapter.
- GUI model/IP setup, optional Modbus unit address, automatic serial identity.
- IP reconfiguration and configurable 15-second polling interval.
- Thirty sensor entities, shared asynchronous polling, availability and recovery.
- Redacted diagnostics, English translations, local integration icon.
- Home Assistant 2026.9.3 and 2026.10.2 automated coverage and a live-inverter test.
- HACS repository layout and validation workflow.
