# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 through 8 of the ground-up Kyth implementation are complete. The next implementation boundary is Phase 9: optional application hooks, only where concrete use cases justify them.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public application listening socket and separate loopback control service across child replacement;
- `watchfiles` observes configurable development roots, normalizes deterministic batches, and drives restart/invalidation decisions;
- successful Python restart publishes browser reload only after replacement ASGI readiness;
- ordinary buffered `text/html` responses receive the browser client transparently;
- direct HTML and browser-resource provenance supports targeted reload and narrow CSS/image replacement;
- incomplete or ambiguous browser-resource evidence remains conservative;
- render provenance uses an adapter-neutral `RenderRecord` with opaque render identity, source versions, dependency set, adapter name, and completeness;
- the child reports render records to a bounded supervisor-owned registry through a token-gated child-only control endpoint;
- when Jinja is available, Kyth installs request-scoped zero-touch tracing of filesystem-backed templates used by normal runtime lookup/render paths;
- complete Jinja renders allow unrelated template edits to leave unaffected views current, and source-version comparison suppresses redundant reload when a view already rendered the new template version;
- incomplete/unavailable render provenance falls back to reload;
- repeated `--manifest PATH` options load stable version-1 generated dependency manifests;
- manifest source changes mark generated outputs stale without reloading them before regeneration;
- generated output deletion-only events remain stale; an add/modify event is required before browser synchronization;
- inactive stale generated outputs require no eager browser action;
- manifest directories are included in effective development roots automatically;
- the Phase 1-6 generic fallbacks remain intact when no Jinja adapter or manifest applies.

## Known gaps

- Jinja tracing covers normal Jinja environment/template entry points; unusual custom rendering stacks may require a later explicit hook;
- non-filesystem Jinja templates deliberately produce incomplete provenance;
- source versions currently use path, nanosecond mtime, and size rather than content hashes;
- Phase 8 manifests are explicit inputs; Kyth does not execute arbitrary generators;
- CSS/image narrow updates remain intentionally limited to safe generic mutation paths;
- JavaScript remains full-reload only unless an external HMR owner is later integrated;
- CSP sandbox policies that create an opaque origin can still prevent the separate loopback control connection;
- descriptor/handle transfer has not yet been exercised on every supported operating system.
