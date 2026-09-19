# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

The V1 design surface and the prioritized development-server hardening program are implemented. Current work is maintenance and evidence-driven follow-up rather than feature or robustness completion.

## Current state

- the current implementation passes `just check`;
- `just complexity --strict` passes with every analyzed source block below the configured threshold;
- the full 78-case real-browser acceptance matrix passes across Chromium and Firefox;
- lifecycle/socket/watcher behavior passes on macOS and Linux across Python 3.12, 3.13, and 3.14;
- browser view registration is monotonic by generation and registration sequence, so delayed registrations cannot overwrite newer dependency/resource snapshots;
- duplicated browser tabs rekey inherited tab identities rather than allowing two live documents to control the same view;
- the browser opens its control EventSource before publishing its initial view registration, eliminating the registration-before-SSE race that could turn safe narrow updates into missed events and conservative reloads;
- reconnect recovery closes the SSE stream while offline and requires a fresh authoritative synchronization when connectivity returns;
- SSE subscriber queues are bounded; a slow subscriber is disconnected on overflow and recovers through normal reconnect synchronization rather than accumulating unbounded pending events;
- watcher duplicate suppression includes filesystem identity/change metadata in addition to modification time and size, so common atomic-save replacement patterns are not discarded as duplicates;
- restart-requiring generated sources do not reload a generated view until its rebuilt output is ready, including transient output deletion and partial rebuilds of sibling outputs sharing a source;
- runtime restart classification is extensible with repeated `--restart-on PATTERN` options;
- verbose diagnostics expose a structured change-cycle report containing classifications, restart outcome, generated invalidations, affected views, browser actions, and resulting generation;
- Kyth-managed ASGI responses use development `Cache-Control: no-store` semantics so immutable application caches cannot mask known changes;
- explicit integrations remain narrow and typed: `depend_on`, `depend_on_data`, custom readiness checks, semantic browser data updates, opt-in state preservation, startup-error events, and external-HMR ownership;
- property/reference-model, fault-injection, lifecycle, provenance, and browser tests cover the corresponding synchronization invariants;
- the first mutation-testing slice covers `changes.py` and `protocol.py`; its initial run generated 103 mutants, killed 85, skipped 18, and reported no surviving, timeout, or suspicious mutants;
- browser installation/testing and mutation testing remain explicit and outside `just check`.

## Remaining hardening priorities

- inspect uncovered failure branches only where they correspond to plausible development failures; do not chase aggregate coverage;
- keep `just check`, `just complexity --strict`, the Chromium/Firefox acceptance matrix, and the supported lifecycle matrix green;
- review remaining medium tests and extract pure policy assertions where doing so improves isolation;
- expand mutation testing to another pure policy/provenance module only when it is likely to expose a meaningful assertion gap;
- add WebKit only if Safari/WebKit becomes an intended development target;
- add bounded diagnostic history only if real debugging shows that `last_change_report` is insufficient.
