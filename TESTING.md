# Testing Kyth

Kyth uses several test layers because its correctness spans pure invalidation policy, local I/O, subprocess lifecycle, and browser behavior.

## Default Python suite

`just test` runs `tests/` and remains the normal development suite. Tests should use the narrowest truthful structural and size categories.

- **unit / small**: pure data, policy, protocol, and state-transition behavior with no real I/O;
- **component / small**: bounded in-process collaborations using fakes or mocks;
- **integration / medium**: real filesystem or localhost-network behavior;
- **system / medium**: supervisor/child lifecycle involving sockets or subprocesses.

Do not improve the category distribution by relabeling I/O-bound tests. Prefer extracting policy from mechanisms so important invariants can be tested hermetically.

## Property-based tests

Hypothesis properties run as part of the default suite and are marked `property_based` plus `small`. They target invariants rather than examples, including:

- deterministic/idempotent filesystem batch normalization;
- associative batch merging;
- exhaustive/disjoint change classification;
- conservative fallback for unknown dependencies;
- complete accounting of affected versus current views;
- monotonic view generations;
- SSE serialization;
- URL/path traversal safety.

Property tests should focus on pure state/policy layers. Filesystem, network, and process fuzzing belongs in later robustness work rather than being hidden inside a nominally small test.

## Real-browser acceptance

The browser suite is intentionally separate from `just check` because Chromium is a large external runtime and should never be downloaded implicitly.

Install the pinned browser once:

```console
just browser-install
```

Run acceptance tests:

```console
just browser-test
```

The acceptance module lives at `tests/browser/browser_acceptance.py`. Its filename intentionally does not match the default `test_*.py` pattern: normal `just check` still formats, lints, and type-checks it as source under `tests/`, but does not launch Chromium. The dedicated recipe uses Playwright 1.63.0 through an ephemeral `uv --with` environment, stores Chromium under `.cache/playwright`, and explicitly collects that module.

The current acceptance suite verifies:

- injected client registration and complete resource observation;
- stylesheet replacement without document reload;
- direct image/SVG cache busting without document reload;
- JavaScript change fallback to full reload;
- failed stylesheet replacement fallback to full reload;
- failed image replacement fallback to full reload.

Browser acceptance should test observable user behavior. Internal event structures belong in the Python suite.

## Quality characterization

The existing quality tools have distinct purposes:

```console
just cov
just dead-code
just complexity
just complexity --strict
just dup
```

Radon is isolated from `pyproject.toml` through `radon.cfg` because Radon 6.0.1 incorrectly interprets pytest percent-style log format strings as ConfigParser interpolation.

Coverage is diagnostic rather than a target by itself. Prioritize untested failure branches and invariants over increasing aggregate line percentage.

## Mutation testing

Mutation testing is deliberately deferred until the property-based and browser-acceptance layers are established and stable. When introduced, start with pure modules such as change classification, invalidation, provenance, and protocol encoding rather than subprocess/browser code.

## Platform matrix

Cross-platform/socket-transfer matrix testing is later hardening work. It should not block the current test-architecture cleanup.
