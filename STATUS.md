# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

The V1 design surface is implemented. Current work is hardening, portability, and maintenance rather than feature completion.

## Current state

- the current implementation passes `just check`;
- `just complexity --strict` passes with every analyzed source block below the configured threshold;
- the full 72-case real-browser acceptance matrix passes across Chromium and Firefox;
- restart-requiring generated sources no longer reload a generated view until its rebuilt output is ready;
- duplicate filesystem notifications describing the same observed file state are suppressed across logical batches;
- runtime restart classification is extensible with repeated `--restart-on PATTERN` options;
- verbose diagnostics expose a structured change-cycle report containing classifications, restart outcome, generated invalidations, affected views, browser actions, and resulting generation;
- Kyth-managed ASGI responses use a development `Cache-Control: no-store` policy so immutable application caches cannot mask known changes;
- explicit integrations are implemented without a plugin framework: `depend_on`, `depend_on_data`, custom readiness checks, semantic browser data updates, opt-in state preservation, startup-error events, and external-HMR ownership;
- reconnect recovery closes the SSE stream when the browser goes offline, preventing buffered narrow updates from racing ahead of a fresh staleness sync;
- property-based, fault-injection, lifecycle, provenance, and browser tests cover the corresponding invariants;
- browser installation/testing remains explicit and outside `just check`.

## Remaining hardening priorities

- inspect remaining uncovered failure branches in control/process/supervisor code and add focused regression cases rather than chasing aggregate coverage;
- keep `just check`, `just complexity --strict`, and the Chromium/Firefox acceptance matrix green;
- review remaining medium tests and extract pure policy assertions where doing so improves isolation;
- introduce mutation testing selectively for pure policy/provenance modules;
- rehearse socket transfer and child lifecycle across the intended operating-system and Python-version matrix.
