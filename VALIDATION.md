# Validation for v0.2.0

Verified on October 23, 2026:

| Check | Result |
| --- | --- |
| Home Assistant Core 2026.9.3 / Python 3.14 | 58 automated tests passed; hardware test skipped |
| Home Assistant Core 2026.10.2 / Python 3.14 | 58 automated tests passed; hardware test skipped |
| Home Assistant hassfest | 1 integration checked; 0 invalid integrations |
| Ruff | Lint and formatting passed |
| Original capture replay | Native protocol validates all 128 read request/response pairs |
| Recorded snapshot replay | Native decoding matches all 100 sampled register snapshots |

New tests cover W-seconds to kWh conversion, directional separation, left-rectangle
integration, restart/unload persistence, checkpointing before publishing totals,
failed/duplicate/backward/long-gap samples, invalid saved totals, alternate grid
source/polarity, hardware option reloads, energy metadata, and preservation of
disabled hardware history/totals.

The validation system had **no PV, generator or battery connected**; numerical
agreement on those idle channels is not physical validation. The automated checks
and passive reference observations do not establish loaded operation of that
equipment. See [the telemetry review](TELEMETRY_REVIEW.md).

## Historical v0.1.0 validation

Verified on October 23, 2026:

| Check | Result |
| --- | --- |
| Home Assistant Core 2026.9.3 / Python 3.14 | 41 automated tests passed; hardware test skipped by default |
| Home Assistant Core 2026.10.2 / Python 3.14 | 41 automated tests passed; hardware test skipped by default |
| Live 18K PV through factory E-Linter adapter | Native config flow, 30 registered sensor entities, initial poll and subsequent fresh poll passed under Core 2026.9.3 |
| Home Assistant hassfest | 1 integration checked; 0 invalid integrations |
| Ruff | Lint and formatting checked |

The automated suite covers HTTP/Modbus validation, serialized reads, total request
timeout, malformed and oversized responses, rejected redirects, model decoding,
setup success/failure, duplicate IP/serial detection, IP reconfiguration, wrong
inverter rejection, polling options/reload, availability/recovery, initial setup
retry, unload, and diagnostics redaction.

The live test ran in an isolated Home Assistant test environment with exclusive
local polling access to the inverter.

The v0.1.0 GitHub CI checks passed after repository topics were added, including
HACS, hassfest and both supported Home Assistant test versions.

Hardware/register limitations in README.md still apply; successful transport and
entity setup do not independently validate every sensor across its operating range.
