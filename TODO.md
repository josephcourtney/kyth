# TODO

- inspect `just cov --lines` for uncovered branches that represent plausible development failures and add focused regressions only where useful;
- keep `just check`, `just complexity --strict`, and the 90-case Chromium/Firefox acceptance matrix green;
- periodically rehearse the lifecycle/socket/watcher subset on macOS and Linux across supported Python versions when lifecycle code changes;
- before tagging 1.0.0, update the project version/lockfile, replace the README baseline, cut the Unreleased changelog into a dated 1.0.0 section, and run `just release-check` plus `just browser-test`;
- add WebKit acceptance only if Safari/WebKit becomes an intended development target;
- add bounded diagnostic-history retention only if real debugging demonstrates that `last_change_report` is insufficient;
- avoid adding a general hook/plugin framework unless a second concrete integration requires capabilities beyond the narrow public APIs.
