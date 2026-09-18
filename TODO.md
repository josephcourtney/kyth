# TODO

- run `just dead-code`, `just complexity --strict`, and `just dup`; resolve actionable findings without changing established architecture solely to satisfy metrics;
- inspect coverage by test/context and identify important branches with weak behavioral assertions, especially failure cleanup, reconnect recovery, and conservative provenance fallbacks;
- establish a mutation-testing recipe around pure modules first (`changes`, `invalidation`, provenance models/indexes, protocol encoding) and kill surviving meaningful mutants with stronger tests;
- reduce the medium-test share by extracting filesystem/network-independent policy assertions from lifecycle/control tests into small tests; do not relabel tests that genuinely perform I/O;
- consolidate repeated lifecycle/control test setup into focused fixtures/helpers only where doing so makes test intent clearer;
- add fault-injection/regression cases for child crash during readiness, failed generation acknowledgement, broken control connection, malformed/live-reloaded manifests, atomic delete/add output rebuilds, and queued watcher events during restart;
- add property-based tests for deterministic batch normalization, invalidation monotonicity/conservatism, manifest path validation, and generation ordering;
- add a minimal real-browser acceptance harness for injected client registration, SSE reconnect, full reload fallback, CSS replacement success/failure, and asset replacement success/failure;
- exercise socket transfer/restart behavior across the supported Python/platform matrix and explicitly document any unsupported combinations;
- keep `just check` green after each hardening change; do not add Phase 9 hooks unless a concrete failing use case requires them.
