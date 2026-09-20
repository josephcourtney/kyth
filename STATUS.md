# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Kyth 1.0.0 establishes the stable compatibility boundary for the V1 design. The complete V1 surface, post-v0.2.0 hardening, explicit synchronization for non-injectable HTML, and scoped conservative fallback are implemented. Work is now evidence-driven maintenance rather than planned feature completion.

## Current state

- `just check` and `just complexity --strict` pass; every analyzed source block is below the configured complexity threshold.
- The 90-case Chromium/Firefox acceptance matrix passes.
- Lifecycle/socket/watcher behavior has been rehearsed on macOS and Linux across Python 3.12-3.14.
- Browser registration/reconnect, bounded SSE queues, duplicate-tab identity, watcher atomic-save handling, and generated-output readiness races have dedicated hardening coverage.
- Direct output/resource provenance, Jinja/render provenance, generated manifests, explicit render/data dependencies, readiness hooks, state preservation, external-HMR ownership, and fallback scopes are implemented.
- Streaming and explicitly encoded HTML can opt into the normal browser protocol through `kyth.injection.client_script()`.
- Fallback scopes narrow only otherwise-uncertain views; precise provenance still wins, unmatched ambiguity remains application-wide, and restart/external-HMR classification retains precedence.
- The current mutation slice covers `changes.py`, `fallback.py`, `invalidation.py`, and `protocol.py`; its 772-mutant run killed 752, skipped 20, and had no surviving, timeout, or suspicious mutants.
- `just release-check` validates the repository, builds without local source overrides, installs the resulting wheel into a fresh environment, runs `kyth --help`, and imports the documented Python integration surface.
- Project and package licensing are aligned on GNU LGPL v3.0 only (`LGPL-3.0-only`).

## Next priorities

- inspect uncovered branches only when they represent plausible development failures;
- keep the canonical, browser, complexity, and supported lifecycle gates green;
- tag and publish 1.0.0 only from the exact commit that passes the final release gates;
- add WebKit, diagnostic history, or a broader plugin framework only in response to a concrete product need.
