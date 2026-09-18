# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 and 2 of the ground-up Kyth implementation are complete. The next implementation boundary is Phase 3: the persistent browser control plane.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public listening socket across child replacement;
- spawned children receive a duplicated socket descriptor/handle and report readiness after ASGI startup;
- `watchfiles` observes configurable roots and filters default development noise plus explicit ignored paths;
- filesystem notifications are normalized into deterministic logical batches;
- Python sources, `.env*`, and `pyproject.toml` trigger restart; browser-facing files are classified but intentionally have no Phase 2 browser action;
- watcher activity continues while synchronous restart is in progress, and all queued edits are merged before deciding whether one follow-up restart is necessary;
- startup failure remains recoverable through a subsequent restart-requiring edit;
- concise logs explain whether each batch causes restart, deferred browser work, or no action.

## Known gaps

- the browser control plane, HTML injection, and provenance/invalidation behavior remain design-only;
- descriptor/handle transfer has not yet been exercised on every supported operating system;
- default change classification is intentionally narrow and will gain provenance-aware behavior in later phases.
