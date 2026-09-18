# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Phases 1 through 6 of the ground-up Kyth implementation are complete. The next implementation boundary is Phase 7: render provenance and the first template-engine adapter.

## Current state

- `kyth package.module:app` runs an ASGI target under a long-lived supervisor;
- the supervisor retains the public application listening socket and separate loopback control service across child replacement;
- `watchfiles` observes configurable roots, normalizes deterministic batches, and drives restart classification/coalescing;
- successful Python restart publishes browser reload only after replacement ASGI readiness;
- ordinary buffered `text/html` responses receive the browser client transparently;
- the browser client registers tab-scoped view identity and maintains generation-aware SSE synchronization;
- direct output provenance maps explicit HTML/trailing-slash URLs to exactly one matching file beneath configured watch roots;
- browser resource registration combines direct DOM references with same-origin Resource Timing observations;
- incomplete resource snapshots remain explicitly conservative rather than silently omitting dependency edges;
- directly linked external stylesheets receive targeted `css-update` events and are replaced only after generation-specific replacements load successfully;
- ordinary direct `<img src>` image/SVG resources without `srcset`/`picture` indirection receive targeted `asset-update` cache busting;
- observed-only CSS/images, fonts, JavaScript, unsupported assets, and mixed narrow-update kinds fall back to targeted full reload;
- unknown changed browser resources retain the application-wide full-reload fallback;
- one filesystem batch produces at most one browser action per view;
- views requiring no action are marked current immediately, while views receiving reload/narrow updates remain stale until navigation or successful mutation re-registers them;
- reconnect synchronization therefore recovers missed/failed updates conservatively without causing delayed reloads for unrelated views.

## Known gaps

- template/render provenance remains design-only until Phase 7;
- generated source-to-output manifests remain Phase 8;
- CSS replacement is limited to direct enabled stylesheet links; imported/observed-only stylesheets reload;
- image replacement intentionally excludes `srcset`, `picture`, CSS backgrounds, and other non-generic mutation paths;
- fonts are dependency-tracked but not mutated in place;
- JavaScript remains full-reload only unless a later external-HMR integration owns it;
- CSP sandbox policies that create an opaque origin can still prevent the separate loopback control connection;
- descriptor/handle transfer has not yet been exercised on every supported operating system.
