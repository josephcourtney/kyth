# TODO

- inspect `just cov --lines` and add focused regressions for important remaining failure branches rather than chasing aggregate percentage;
- keep `just check` and `just complexity --strict` green while hardening;
- keep the passing 72-case Chromium/Firefox matrix stable; add browser fixtures only for distinct Kyth contracts;
- review remaining medium tests and extract pure policy assertions where possible; keep genuine filesystem/network/subprocess tests medium;
- design the first mutation-testing slice for pure policy/provenance modules;
- rehearse Python/platform socket-transfer and child-lifecycle behavior across the supported matrix;
- avoid adding a general hook/plugin framework unless a second concrete integration requires capabilities beyond the narrow V1 APIs.
