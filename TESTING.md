# Testing Kyth

Kyth spans pure invalidation policy, local filesystem/network I/O, subprocess lifecycle, optional render provenance, generated outputs, and browser behavior. The suite is intentionally layered rather than forcing all behavior through process-level tests.

## Default Python suite

`just test` runs the ordinary `tests/` suite. Use the narrowest truthful categories:

- **unit / small**: pure data, policy, protocol, and state transitions with no real I/O;
- **component / small**: bounded in-process collaborations using fakes/mocks;
- **integration / medium**: real filesystem or localhost-network behavior;
- **system / medium**: supervisor/child lifecycle involving sockets or subprocesses.

Do not improve the size distribution by relabeling I/O-bound tests. Extract pure policy from mechanisms where doing so makes behavior clearer.

## Property-based tests

Hypothesis properties run in the default suite and are marked `property_based` plus `small`. Current invariants include:

- deterministic/idempotent filesystem batch canonicalization;
- associative batch merging;
- exhaustive/disjoint change classification;
- conservative fallback for unknown dependencies;
- complete accounting of affected/current views;
- monotonic view generations;
- SSE serialization;
- direct URL/path traversal safety.

Property tests stay in pure state/policy layers. Filesystem/process fuzzing is separate robustness work.

Hypothesis lazily imports its execution engine and normally uses a filesystem-backed example database. The test harness warms the public Hypothesis execution path during pytest session setup, before per-test isolation begins, and uses an in-memory example database. This keeps property tests truthfully `small` without granting them filesystem exceptions. Regressions that must persist across runs should be promoted to explicit `@example` cases.

## Hermetic fault injection

Small component tests exercise failure policy without paying subprocess cost where real process behavior is not essential. Current coverage includes:

- render-report serialization, rejection, and unavailable-control behavior;
- child control-channel EOF/shutdown/generation handling;
- ASGI target parsing/resolution;
- startup timeout/EOF/invalid-event handling;
- generation acknowledgement failures;
- graceful shutdown → terminate → kill escalation.

Real descriptor transfer, socket ownership, and actual child replacement remain system tests.

## Test-app matrix

Kyth uses several deliberately different fixture applications rather than one universal demo app.

| Fixture | Purpose / scenarios |
| --- | --- |
| Generated lifecycle apps in `tests/test_lifecycle.py` | ordinary restart, rapid same-size source replacement, syntax/import startup failure and recovery, explicit lifespan startup failure, apps without lifespan support, delayed readiness, hanging shutdown, unexpected post-ready child exit, persistent application/control sockets, HTML injection, targeted SSE decisions |
| `tests/browser/apps/resource_app.py` | direct HTML output, CSS, image/SVG, JavaScript, independent tabs, duplicate stylesheet references, query-bearing resource URLs, `srcset`/`picture` unsafe images, CSS-observed assets, fonts, CSP, fragment HTML, multiple stylesheet updates, mixed update types, unknown resources, and readiness-gated restart failure |
| `tests/browser/apps/passthrough_app.py` | ordinary injectable HTML contrasted with streaming HTML, explicit gzip content encoding, byte-range responses, and non-HTML bodies that must pass through unchanged |
| `tests/browser/apps/jinja_app.py` | real optional Jinja rendering with inheritance and includes, validating runtime render provenance and selective/shared-template invalidation |
| Manifest-backed generated fixture | explicit source→output dependency, stale-output deferral, and browser reload only after the generated output is rebuilt |

The collection is intended to cover distinct semantic boundaries, not permutations that do not change Kyth behavior. Security validation of malformed control requests remains in control-plane tests; manifest schema/path validation remains in provenance tests; external frontend HMR ownership is outside v0.2.0's implemented surface.

## Real-browser acceptance

The browser acceptance module is `tests/browser/browser_acceptance.py`. Its filename intentionally does not match the default `test_*.py` pattern: normal `just check` still compiles, formats, lints, and type-checks the browser harness and fixture apps, but it does not launch or download browsers.

Install pinned Playwright browser builds once:

```console
just browser-install
```

This installs both Chromium and Firefox into `.cache/playwright`.

Run the complete browser contract:

```console
just browser-test
```

The dedicated test environment supplies Playwright plus Jinja only for acceptance execution; neither becomes a Kyth runtime dependency.

Every browser acceptance test is parameterized over Chromium and Firefox. The current matrix verifies:

- initial injected-client registration and complete resource snapshots;
- successful server restart → document reload;
- failed replacement startup → no reload until a ready replacement exists;
- CSS replacement without document navigation;
- image/SVG cache busting without document navigation;
- JavaScript/font/observed-resource fallback to full reload;
- failed CSS/image narrow update fallback;
- distinct-tab targeting;
- duplicate stylesheet references;
- preservation of pre-existing resource query parameters;
- unsafe `srcset`/`picture` image fallback;
- mixed narrow-update kinds collapsing to reload;
- multiple stylesheet updates as one narrow transaction;
- unknown-resource conservative reload;
- direct HTML output reload;
- CSP-compatible injection/control connection;
- HTML fragments without closing tags;
- offline/missed SSE event recovery through reconnect synchronization;
- duplicate reload events for the current generation being ignored;
- streaming/compressed/ranged/non-HTML pass-through behavior;
- real Jinja include/base-template invalidation;
- generated source changes waiting for regenerated output before navigation.

Browser acceptance tests observable user behavior. Internal broker/event decisions belong in the Python suite.

## Quality characterization

Use:

```console
just cov
just dead-code
just complexity
just complexity --strict
just dup
```

Radon is isolated from `pyproject.toml` through `radon.cfg` because Radon 6.0.1 incorrectly feeds pytest percent-style log strings through ConfigParser interpolation.

Coverage is diagnostic rather than a target by itself. Prefer important failure branches and invariant assertions over aggregate percentage.

## Mutation testing

Mutation testing is deliberately deferred until property-based and browser-acceptance layers are stable. Start later with pure modules such as change classification, invalidation, provenance, and protocol encoding rather than subprocess/browser code.

## Platform matrix

Cross-platform/socket-transfer matrix testing is later hardening work and does not block the current test-architecture cleanup.
