# TODO

- run `just check` and resolve any lint/type/test issues from the hardening test additions;
- run `just complexity` and `just complexity --strict` using the isolated Radon config; refactor only findings that represent real maintenance cost;
- run `just browser-install` once, then `just browser-test`; fix any Chromium/Firefox discrepancies across registration, readiness-gated restart, narrow updates, reconnect recovery, Jinja provenance, generated manifests, and conservative fallbacks;
- inspect `just cov --lines` after the new hermetic tests and add focused regressions for important remaining failure branches rather than chasing aggregate percentage;
- review browser failures for missing semantic fixture classes; add new test apps only when they exercise a distinct Kyth contract rather than another permutation of covered behavior;
- review remaining medium tests and extract pure policy assertions where possible; keep genuine filesystem/network/subprocess tests medium;
- after property-based and browser acceptance are stable, design the first mutation-testing slice for pure modules only;
- defer Python/platform socket-transfer matrix work until later hardening;
- keep Phase 9 hooks deferred unless a concrete failing use case requires them.
