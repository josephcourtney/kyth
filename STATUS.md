# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Kyth v0.2.0 is in hardening. Feature expansion and application hooks remain deferred. Current work is improving test architecture and robustness while preserving behavior.

## Current state

- the validated v0.2.0 baseline passes `just check`;
- dead-code and duplication scans report no findings;
- aggregate source coverage is about 81% lines / 65% branches, with the weakest areas concentrated in process lifecycle, control error paths, render reporting, and manifest validation;
- Radon 6.0.1 cannot safely auto-read this project's pytest percent-style log format from `pyproject.toml`; complexity analysis is now isolated through `radon.cfg`;
- property-based tests exercise pure batch, invalidation, generation, protocol, and path-safety invariants in the normal Python suite;
- additional small fault-injection tests cover render reporting and child-process readiness/control/escalation policy without spawning processes;
- a separate real-browser acceptance suite runs the same contract against Chromium and Firefox and covers injection, restart/readiness gating, narrow updates, conservative fallbacks, reconnect recovery, Jinja provenance, and generated-output readiness;
- browser installation/testing is explicit and remains outside `just check` so normal validation never downloads a browser;
- mutation testing is deliberately deferred until the property and browser layers have been exercised and stabilized.

## Remaining hardening priorities

- run the expanded `just check`, `just complexity --strict`, and dedicated browser acceptance suite and resolve findings;
- inspect remaining uncovered failure branches in control/process/supervisor code and add focused regression cases;
- run and stabilize the expanded Chromium/Firefox matrix, then add only regression fixtures justified by observed failures;
- only then introduce mutation testing for pure policy/provenance modules;
- platform/socket-transfer matrix testing is explicitly later work.
