# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Kyth v0.2.0 is the validated Phase 1-8 baseline. Near-term work is hardening rather than feature expansion: improve code quality, test architecture, and robustness while preserving existing behavior.

## Current state

- the full local `just check` gate passes on the v0.2.0 baseline;
- supervisor-owned application/control sockets, restartable ASGI lifecycle, watching, HTML injection, targeted reload, narrow CSS/image updates, render provenance/Jinja tracing, and generated dependency manifests are implemented;
- direct, render, resource, and manifest provenance all retain conservative reload fallbacks when evidence is incomplete;
- application hooks are intentionally deferred until a concrete use case cannot be represented by existing provenance mechanisms;
- package metadata and lockfile identify the baseline as 0.2.0.

## Hardening priorities

- reduce unnecessary complexity/duplication and remove dead code without redesigning stable boundaries;
- strengthen pure policy/provenance tests and reduce reliance on medium integration tests where real I/O is not essential;
- add systematic failure/race coverage around child lifecycle, IPC, control connections, watcher batching, manifests, and resource/render provenance;
- use coverage, mutation testing, and property-based tests to find weak assertions rather than chasing line coverage alone;
- exercise browser synchronization and supported-platform lifecycle behavior end to end before expanding the public API.

## Known gaps

- browser-client behavior has less black-box coverage than the Python control/supervisor layers;
- the suite remains integration-heavy, with a substantially higher medium-test share than the project target;
- unusual custom rendering stacks still fall back conservatively;
- descriptor/socket transfer needs broader supported-platform rehearsal;
- no Phase 9 hook API is planned unless hardening exposes a concrete requirement.
