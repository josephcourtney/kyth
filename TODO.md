# TODO

- inspect `just cov --lines` for uncovered branches that represent plausible development failures and add focused regressions only where useful;
- keep `just check`, `just complexity --strict`, and the 90-case Chromium/Firefox acceptance matrix green;
- periodically rehearse the lifecycle/socket/watcher subset on macOS and Linux across supported Python versions when lifecycle code changes;
- review remaining medium tests and extract pure policy assertions where possible; keep genuine filesystem/network/subprocess tests medium;
- expand the narrow mutation-testing slice beyond change classification and protocol encoding only when another pure policy/provenance module is likely to yield actionable survivors;
- add WebKit acceptance only if Safari/WebKit becomes an intended development target;
- add bounded diagnostic-history retention only if real debugging demonstrates that `last_change_report` is insufficient;
- avoid adding a general hook/plugin framework unless a second concrete integration requires capabilities beyond the narrow V1 APIs.
