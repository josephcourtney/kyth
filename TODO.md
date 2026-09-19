# TODO

- run `just check` after the manifest-validation refactor and resolve any lint/type/test regressions;
- run `just complexity --strict` and confirm all source blocks are below the configured threshold;
- inspect `just cov --lines` after the new hermetic tests and add focused regressions for important remaining failure branches rather than chasing aggregate percentage;
- keep the passing Chromium/Firefox matrix stable; add new test apps only when they exercise a distinct Kyth contract rather than another permutation of covered behavior;
- review remaining medium tests and extract pure policy assertions where possible; keep genuine filesystem/network/subprocess tests medium;
- after property-based and browser acceptance are stable, design the first mutation-testing slice for pure modules only;
- defer Python/platform socket-transfer matrix work until later hardening;
- keep Phase 9 hooks deferred unless a concrete failing use case requires them.
