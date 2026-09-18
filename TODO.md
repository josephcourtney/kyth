# TODO

- run `just check` and resolve any lint/type/test issues from the hardening test additions;
- run `just complexity` and `just complexity --strict` using the isolated Radon config; refactor only findings that represent real maintenance cost;
- run `just browser-install` once, then `just browser-test`; fix any Chromium-observed discrepancies in registration, narrow updates, or reload fallback;
- inspect `just cov --lines` after the new hermetic tests and add focused regressions for important remaining failure branches rather than chasing aggregate percentage;
- add browser acceptance for SSE disconnect/reconnect and missed-event recovery once the initial browser harness is stable;
- review remaining medium tests and extract pure policy assertions where possible; keep genuine filesystem/network/subprocess tests medium;
- after property-based and browser acceptance are stable, design the first mutation-testing slice for pure modules only;
- defer Python/platform socket-transfer matrix work until later hardening;
- keep Phase 9 hooks deferred unless a concrete failing use case requires them.
