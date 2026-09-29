# Status

This file records the current implementation state and immediate handoff context. `DESIGN.md` remains authoritative for architecture and `PLAN.md` for sequencing.

## Current focus

Kyth 1.0.1 is the current stable V1 patch baseline. It preserves the compatibility boundary established by 1.0.0 while incorporating the bounded correctness, compatibility, validation, and documentation fixes identified by the post-1.0 review.

## Current state

- `v1.0.0` remains the annotated tag on the original 1.0 release commit; 1.0.1 incorporates the subsequent reviewed hardening without rewriting that historical tag.
- Browser-facing classification now covers all image suffixes supported by narrow invalidation, including AVIF and BMP.
- Generation commit now reconciles views that appear after the original invalidation snapshot, closing a missed-event race without weakening generated-output deferral.
- Render/data source versions include change-time and filesystem identity metadata, matching the watcher hardening needed to detect same-size atomic replacements with preserved mtimes.
- Optional Jinja tracing validates the installed class shape and fails soft to conservative synchronization when unsupported.
- Kyth preserves application-visible request content negotiation; encoded or streaming HTML remains untouched and may opt in through `kyth.injection.client_script()`.
- Persistent GitHub Actions CI runs `just check`, `just complexity --strict`, and the Chromium/Firefox browser acceptance suite; tag release preflight depends on both validation jobs before running `just release-check`.
- Existing lifecycle/socket/watcher behavior has been rehearsed on macOS and Linux across Python 3.12-3.14; rerun that matrix when those mechanisms change.
- The mutation slice remains focused on `changes.py`, `fallback.py`, `invalidation.py`, and `protocol.py` rather than expanding mutation testing mechanically.

## Next priorities

- keep the canonical, browser, complexity, and supported lifecycle gates green;
- perform a bounded coverage audit focused on uncovered branches that represent plausible development failures;
- exercise Kyth against structurally different real projects and turn unexplained field behavior into concrete issues;
- add WebKit, diagnostic history, a standalone JavaScript source/lint path, or a broader plugin framework only in response to concrete product or maintenance needs.
