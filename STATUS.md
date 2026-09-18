# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 through 5 of the ground-up Kyth implementation are complete. The next implementation boundary is Phase 6: narrow generic browser updates for CSS and directly referenced assets.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public application listening socket and separate loopback control service across child replacement;
- `watchfiles` observes configurable roots, normalizes deterministic batches, and drives restart classification/coalescing;
- successful Python restart publishes browser reload only after replacement ASGI readiness;
- ordinary buffered `text/html` responses receive the browser client transparently;
- the browser client registers tab-scoped view identity and maintains generation-aware SSE synchronization;
- direct output provenance maps explicit HTML/trailing-slash URLs to exactly one matching file beneath configured watch roots;
- previously observed direct outputs remain known after their views disappear;
- browser invalidation is represented separately from browser presentation;
- changes to known direct outputs reload only dependent direct views plus any active views whose dependency relationship remains unknown;
- known unrelated direct views are marked current without navigation;
- a known inactive direct output can change without reloading unrelated direct views;
- any unknown changed browser dependency still falls back to application-wide full reload;
- reconnect synchronization is per-view, so an unrelated prior targeted change does not cause a delayed reload.

## Known gaps

- CSS and direct asset hot replacement are not implemented yet;
- extensionless routes and ambiguous URL-to-file mappings intentionally remain conservative;
- template/render provenance remains design-only until Phase 7;
- generated source-to-output manifests remain Phase 8;
- CSP sandbox policies that create an opaque origin can still prevent the separate loopback control connection;
- descriptor/handle transfer has not yet been exercised on every supported operating system.
