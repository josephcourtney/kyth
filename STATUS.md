# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Kyth 1.1.0 is being qualified as a backward-compatible feature release for separately installed application interpreters. The Haint field session and local canonical/browser suites demonstrated working startup, API requests, readiness-gated restart, and recovery after source edits. The first remote post-merge CI run revealed four suppression-style lint errors in the committed tree; the release-qualification branch corrects those and adds bounded dependency-sync recovery. Remote CI is the remaining release gate.

## Current state

- `v1.0.0` remains the annotated tag on the original 1.0 release commit; 1.0.1 incorporates the subsequent reviewed hardening without rewriting that historical tag.
- Browser-facing classification covers all image suffixes supported by narrow invalidation, including AVIF and BMP.
- Generation commit reconciles views that appear after the original invalidation snapshot, closing a missed-event race without weakening generated-output deferral.
- Render/data source versions include change-time and filesystem identity metadata, matching the watcher hardening needed to detect same-size atomic replacements with preserved mtimes.
- Optional Jinja tracing validates the installed class shape and fails soft to conservative synchronization when unsupported.
- Kyth preserves application-visible request content negotiation; encoded or streaming HTML remains untouched and may opt in through `kyth.injection.client_script()`.
- The post-v1.0.1 coverage audit added focused regressions for plausible lifecycle, watcher, control, manifest, middleware, and cleanup failures without pursuing aggregate coverage mechanically.
- `examples/e2e/` contains runnable field-test projects for plain ASGI resources, Jinja provenance, generated manifests, explicit streaming/encoded HTML, and the public integration APIs.
- Persistent GitHub Actions CI runs `just check`, `just complexity --strict`, and the Chromium/Firefox browser acceptance suite; tag release preflight depends on both validation jobs before running `just release-check`.
- Existing lifecycle/socket/watcher behavior has been rehearsed on macOS and Linux across Python 3.12-3.14; rerun that matrix when those mechanisms change.
- The mutation slice remains focused on `changes.py`, `fallback.py`, `invalidation.py`, and `protocol.py` rather than expanding mutation testing mechanically.

## Next priorities

- require the committed qualification branch to pass remote `just check`, strict complexity, 90 browser acceptance tests, and the macOS/Linux isolated-worker interpreter matrix;
- confirm bounded dependency-restart coalescing and recovery regressions, including missing interpreter and no-follow-up-edit cases;
- publish/tag 1.1.0 only after the full release preflight is green; do not treat a local dirty-tree check as release evidence;
- continue ordinary field use and add further browser/tool integrations only for demonstrated gaps.
