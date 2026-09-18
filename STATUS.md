# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 through 4 of the ground-up Kyth implementation are complete. The initial useful vertical slice is implemented. The next implementation boundary is Phase 5: static/generated resource awareness and reload precision.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public application listening socket and a separate loopback browser-control service across child replacement;
- `watchfiles` observes configurable roots, normalizes deterministic batches, and drives restart classification/coalescing;
- successful Python restart publishes browser reload only after the replacement ASGI application reaches readiness;
- the control service provides token-gated SSE, view registration, reconnect synchronization, client JavaScript, and inactive-view cleanup;
- ordinary buffered `text/html` responses receive the browser client transparently at the ASGI response boundary;
- response mutation recalculates content length, drops stale validators, and augments existing CSP for the exact Kyth script/control origin;
- the injected client assigns tab-scoped view identity, registers URL/generation/render identity, reconnects SSE, and suppresses duplicate-generation reload loops;
- browser-facing file changes can advance the generation without restarting Python: the live child receives and acknowledges the new injected generation before reload is published;
- if that live generation update fails, Kyth conservatively restarts the child before notifying browsers;
- streaming, range, and explicitly compressed HTML remain unchanged and therefore receive reduced zero-touch functionality.

## Known gaps

- reload decisions are still conservative at application scope; Phase 5 will map static/generated outputs to active views;
- CSS and direct asset hot replacement are not implemented yet;
- template/render provenance and generated dependency manifests remain design-only;
- CSP sandbox policies that create an opaque origin can still prevent the separate loopback control connection;
- descriptor/handle transfer has not yet been exercised on every supported operating system.
