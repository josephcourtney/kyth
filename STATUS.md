# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 through 3 of the ground-up Kyth implementation are complete. The next implementation boundary is Phase 4: transparent HTML injection and generic browser reload.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public application listening socket and a separate loopback browser-control service across child replacement;
- spawned application children receive a duplicated socket descriptor/handle and report readiness after ASGI startup;
- `watchfiles` observes configurable roots, normalizes deterministic batches, and drives restart classification/coalescing;
- the control service binds only to `127.0.0.1`, uses a per-session unguessable token, and permits browser CORS only from loopback HTTP(S) origins;
- `GET /events` provides SSE with immediate and reconnect `sync` events carrying the current committed generation;
- `POST /views` registers or updates per-tab view identity, URL, client generation, and optional render identity;
- inactive views expire from the in-memory registry;
- successful child startup advances the control-plane generation only after ASGI readiness; failed startup does not advertise a new generation;
- the control address and session token remain stable across application-child restart.

## Known gaps

- no browser client is injected yet, so the Phase 3 control endpoints are infrastructure rather than an end-user live-reload path;
- browser-facing filesystem changes are still classified but not emitted as reload/update events;
- descriptor/handle transfer has not yet been exercised on every supported operating system;
- provenance/invalidation behavior remains design-only.
