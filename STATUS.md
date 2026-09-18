# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phase 1 of the ground-up Kyth implementation is complete. The next implementation boundary is Phase 2: filesystem watching and restart classification.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor binds and retains the public listening socket across child replacement;
- spawned children receive a duplicated socket descriptor/handle rather than a pickled socket object;
- application children run under Uvicorn without Uvicorn reload mode;
- readiness is reported only after ASGI lifespan startup completes;
- startup failure leaves the supervisor recoverable without rebinding the public port;
- shutdown is graceful for a bounded interval, then escalates through terminate and kill;
- child status and committed development generation are explicit model state;
- lifecycle tests cover stable socket ownership, restart, startup failure/recovery, readiness ordering, and hung shutdown;
- tests are categorized for strict `pytest-test-categories` enforcement.

## Known gaps

- no filesystem watcher or automatic restart trigger exists yet;
- the browser control plane, HTML injection, and provenance/invalidation behavior remain design-only;
- descriptor/handle transfer has not yet been exercised on every supported operating system.
