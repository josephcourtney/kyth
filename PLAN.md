# Kyth Implementation Plan

This plan realizes the architecture in `DESIGN.md`. It describes sequencing rather than implementation status.

## Phase 1: establish the supervisor core

Build the smallest end-to-end process lifecycle before browser synchronization.

Deliver:

- CLI accepting an ASGI import target and host/port options;
- supervisor-owned listening socket;
- restartable child process using the inherited/passed socket;
- explicit child readiness signal after ASGI startup;
- bounded graceful shutdown with termination escalation;
- startup-failure recovery while the supervisor remains alive;
- structured internal state for child status and development generation.

Verification should prove that repeated Python-side restarts do not require rebinding the public port and that a failed child can be corrected by a subsequent edit.

## Phase 2: filesystem watching and restart classification

Add `watchfiles`-based observation and batch filesystem events into logical change sets.

Deliver:

- configurable watched roots and ignored paths;
- deterministic change batches;
- default path classification;
- restart coalescing when edits arrive during startup/shutdown;
- concise logging of changed paths and restart decisions.

Initially, non-Python browser-facing changes may be logged without browser action. The purpose of this phase is to make process restart semantics reliable independently of the browser layer.

## Phase 3: persistent browser control plane

Add a supervisor-owned control server that remains available while the ASGI child restarts.

Deliver:

- SSE endpoint for supervisor-to-browser events;
- per-session control token/origin restrictions appropriate to local development;
- generation identifiers in emitted events;
- browser registration endpoint;
- inactive-view cleanup;
- protocol tests independent of an application framework.

The browser control service must not share lifecycle ownership with the restartable child.

## Phase 4: transparent HTML injection and generic reload

Wrap the child ASGI application so supported HTML responses receive the development client without application changes.

Deliver:

- external browser-client resource;
- HTML-response injection;
- correct response-header adjustment;
- handling of content length and cache validators;
- a documented fallback for streaming or otherwise non-injectable responses;
- per-tab view identity;
- generation tracking and reconnection;
- full-page reload events.

At the end of this phase, Python changes must produce the complete sequence:

`change -> restart -> readiness -> generation -> affected browser reload`.

## Phase 5: static/generated resource awareness

Track direct relationships visible without framework-specific instrumentation.

Deliver:

- mapping from served static/generated HTML files to active views;
- mapping of current document resource references where reliable;
- invalidation separate from browser action;
- no reload for known unrelated static HTML changes;
- conservative reload fallback for ambiguous relationships.

This establishes the `source -> output -> view` model before template-engine adapters are added.

## Phase 6: narrow generic browser updates

Add only hot-update mechanisms that are simple and framework-independent.

Deliver:

- CSS link replacement/cache busting;
- asset cache busting for directly mapped image/SVG/font resources where safe;
- fallback from failed narrow update to full reload;
- coherent batching so one build burst does not produce repeated reloads.

Do not implement JavaScript module HMR.

## Phase 7: render provenance API and Jinja adapter

Introduce the first dependency provider for server-rendered pages.

Deliver:

- internal provenance interface independent of Jinja;
- render identities associated with active views;
- source-version/invalidation representation;
- Jinja dependency capture covering inheritance, includes/imports, and runtime-selected templates where feasible;
- conservative behavior when dynamic dependencies cannot be resolved;
- tests demonstrating that unrelated template edits do not reload the current page while shared-template edits do.

The adapter should require no application-source changes for normal supported integrations where practical. Explicit integration remains available for unusual rendering stacks.

## Phase 8: generated-site dependency manifests

Define a small stable format by which external generators can report source-to-output dependencies.

Deliver:

- manifest schema;
- loader/validator;
- invalidation of generated outputs from source changes;
- lazy handling of inactive stale outputs;
- browser reload only when an affected generated output is currently displayed.

Do not make Kyth responsible for arbitrary build execution in this phase.

## Post-v0.2.0 hardening

Kyth is a local development server, not production infrastructure. Hardening therefore targets **semantic correctness and automatic recovery during ordinary development disruption** rather than high availability, hostile-client resistance, or indefinite operation.

The reliability criterion is:

> Kyth must not silently leave a browser displaying state that Kyth believes is current when that state is stale. Rapid edits, invalid source, failed startup, child crashes, temporary browser disconnection, duplicate filesystem notifications, and delayed generated output should either recover automatically or fail conspicuously while preserving the last coherent generation.

Implement hardening in the following priority order.

### H1: synchronization-state correctness

**Status: delivered.**

Treat filesystem observation, supervisor generation state, child readiness, browser view state, and generated-output readiness as one synchronization protocol.

Deliver:

- an independent Hypothesis state-machine/reference model for generation and view synchronization rather than testing only individual helper functions;
- generated sequences covering registration, stale registration, generation advancement, acknowledgement, disconnect/reconnect, and duplicate delivery;
- invariants that generations never regress, stale browser registrations cannot overwrite newer view state, and a view becomes current only through an explicit valid transition;
- property coverage that reload dominates narrower actions and every active view is accounted for as affected, deliberately current, or conservatively stale;
- regression cases for generated-output deferral interacting with restart and render/data provenance.

Keep the model small and independent of the implementation. Do not introduce a production state-machine framework merely to support the tests.

### H2: realistic development-race coverage

**Status: delivered for the identified V1 development races.**

Exercise event orderings that occur during normal editing rather than production-scale stress.

Deliver regression tests for:

- repeated edits while a replacement child is starting or stopping;
- syntax/import/readiness failure followed by another edit and successful recovery;
- browser disconnect or reconnect during a restart or narrow update;
- stale or delayed view registration arriving after a newer generation;
- generated source change, output deletion/recreation, and output rebuild around a child restart;
- multiple generated outputs sharing or not sharing source inputs;
- unexpected post-ready child exit followed by recovery;
- duplicate-tab/view-identity behavior, with an explicit conservative policy if two live clients present the same identity.

Prefer deterministic component tests for ordering semantics and retain real subprocess/browser tests only where the mechanism itself matters.

### H3: cheap defensive boundaries

**Status: delivered.**

Add small defenses where recovery semantics already exist. Do not build production backpressure or durability subsystems.

Deliver:

- strengthen watcher duplicate detection against common atomic-save/replacement patterns using filesystem identity/change metadata in addition to modification time and size; introduce content hashing only if realistic tests demonstrate that metadata remains ambiguous;
- bound each SSE subscriber queue to a small finite size;
- if an SSE subscriber falls behind, drop its pending narrow-update history, close that subscription, and rely on the existing reconnect sync path for authoritative recovery;
- retain bounded registries and request-size limits and add focused malformed-input tests only for control paths that can corrupt synchronization state.

The overload rule is: discard precision and force resynchronization rather than risk stale state.

### H4: supported-environment rehearsal

**Status: delivered for macOS/Linux and Python 3.12-3.14; Chromium/Firefox remain the browser targets.**

Make portability claims executable only for environments Kyth intends to support.

Deliver:

- run socket-transfer, watcher, child-lifecycle, failed-startup, and generation-acknowledgement tests on the supported Python versions;
- run the same lifecycle subset on macOS and Linux if both are claimed supported;
- keep Chromium and Firefox acceptance green;
- add WebKit only if Safari/WebKit is an intended development target;
- document unsupported operating systems rather than adding speculative compatibility machinery.

This is compatibility rehearsal, not a production deployment matrix.

### H5: diagnostic/test-quality follow-up

**Status: active maintenance.** The first narrow mutation slice covers change classification and protocol encoding; further expansion remains evidence-driven.

Only after H1-H4 are stable:

- use mutation testing selectively on pure modules such as change classification, invalidation, protocol encoding, and provenance;
- inspect uncovered failure branches and add tests only where the branch represents a plausible development failure;
- consider a small bounded history of recent structured change-cycle reports if real debugging experience shows that last_change_report is insufficient.

Mutation score, aggregate coverage, soak duration, and resource-usage benchmarks are diagnostic signals rather than release targets.

### Explicit hardening non-goals

Do not add the following without evidence from actual Kyth use:

- production-style high availability or zero-downtime guarantees;
- large soak/stress systems intended to prove months-long uptime;
- generalized queue/backpressure infrastructure;
- hostile-client or network-adversary fuzzing beyond the existing loopback development security boundary;
- arbitrary transactional frameworks around the supervisor;
- content hashing of every changed file;
- a general plugin or HMR framework.

### Hardening verification

The hardening program is successful when:

1. property/state-machine tests cannot produce a sequence that regresses generation state or marks a stale view current;
2. realistic restart, failure, reconnect, rapid-save, and generated-output races have deterministic regressions;
3. a slow SSE subscriber cannot grow memory without bound and reconnects through authoritative synchronization;
4. common atomic-save patterns are not suppressed as duplicate filesystem states;
5. the existing static gates, strict complexity gate, lifecycle suite, and Chromium/Firefox browser acceptance suite remain green;
6. supported platform/Python combinations pass the lifecycle/socket subset.

Do not optimize test-category percentages by relabeling genuinely I/O-bound tests. Improve the boundary between pure policy and I/O mechanisms instead.

## Phase 9: narrow optional application integrations

The remaining V1 integration points are implemented without introducing a general hook framework.

Delivered:

- `depend_on(path)` for explicit request-scoped filesystem dependencies using the same source-version model as automatic render provenance;
- `depend_on_data(identity, path)` for semantic browser-consumed data dependencies;
- targeted `data-update` events whose browser handlers explicitly claim an identity and fall back to full reload when absent or unsuccessful;
- `register_readiness_check` for synchronous or asynchronous application-specific readiness after successful ASGI lifespan startup;
- opt-in `kyth:before-reload` / `kyth:restore-state` browser state preservation using tab-scoped JSON serialization;
- non-navigating `kyth:server-error` diagnostics for failed replacement startup;
- repeated `--external-hmr-on PATTERN` configuration so selected browser changes can remain owned by a dedicated frontend development server.

These are deliberately small typed/configured extensions. Do not replace them with a plugin framework unless a concrete second implementation requires a capability that cannot be expressed through the existing provenance, control-event, readiness, or classification mechanisms.

## Phase 10: explicit synchronization for non-injectable HTML

**Status: delivered.**

Extend the existing browser synchronization protocol to HTML responses Kyth deliberately does not rewrite, especially streaming and explicitly encoded responses. This is an explicit application integration, not a second browser-control mechanism.

The invariant is:

> An explicitly integrated page must register and synchronize exactly like an automatically injected page. The only difference is who places the client script into the HTML.

### 10.1 Request-local client bootstrap context

Create one request-local bootstrap context for every Kyth-managed HTTP request before the wrapped application runs. It should contain the same information automatic injection already embeds:

- control URL;
- session token;
- candidate/committed generation;
- render identifier;
- per-response CSP nonce;
- whether explicit client inclusion has been requested;
- whether response headers have already been committed.

Use a context-local mechanism so concurrent requests cannot observe one another's bootstrap state. Keep the browser protocol and client JavaScript unchanged.

### 10.2 Public explicit-inclusion helper

Add one narrow public helper, provisionally `kyth.injection.client_script()`, that returns the complete Kyth `<script>` element for the current request.

Required behavior:

- inside an active Kyth-managed request, return the same client URL/data attributes used by transparent injection and mark the request as explicitly integrated;
- outside an active Kyth-managed request, return an empty string so a development-only integration does not alter normal application output;
- if called after Kyth has committed the response headers/body boundary required for safe CSP adjustment, fail conspicuously rather than silently claim synchronization support;
- document template auto-escaping requirements explicitly; do not add a template-framework abstraction merely to mark the returned HTML safe.

The helper is an opt-in escape hatch for response forms Kyth cannot safely mutate. It must not become necessary for ordinary buffered HTML.

### 10.3 Middleware cooperation without body rewriting

Teach the injection middleware to distinguish three HTML paths:

1. **automatic injection** — current behavior for ordinary complete HTML;
2. **explicit inclusion** — the application has emitted the helper result, so Kyth must not inject a second client;
3. **unintegrated pass-through** — unsupported response remains untouched apart from the existing development cache policy.

For explicitly integrated responses, Kyth should:

- leave body bytes and streaming boundaries unchanged;
- apply the same CSP allowance using the request's bootstrap nonce and control origin before the stored response start is released;
- retain development `no-store` cache semantics;
- permit explicit integration even when the body is streaming or explicitly compressed, because Kyth no longer needs to decode or rewrite the body;
- preserve existing HEAD/range/status semantics and never fabricate a client for responses that are not complete browser documents.

The existing buffering of `http.response.start` until the first body message is sufficient for common streaming responses where the helper is evaluated while constructing the first chunk. Do not buffer arbitrary streaming bodies.

### 10.4 Provenance and generation parity

Explicitly integrated documents must participate in the same synchronization state as injected documents.

Deliver:

- report captured render provenance when either automatic injection succeeded or explicit inclusion was activated;
- use the same render identifier in the explicit script and provenance record;
- register the same per-tab view/resource snapshot;
- use the same EventSource, registration sequence, generation, reconnect, narrow-update, data-update, and full-reload behavior;
- prevent double registration/client startup when an otherwise injectable response also uses the explicit helper.

No new SSE event kind or browser-view model should be introduced.

### 10.5 Failure semantics

Explicit integration is allowed to be application code, but it must still fail safely.

Required behavior:

- malformed or late explicit inclusion must be visible in development diagnostics;
- a page that never includes either automatic or explicit client integration is simply outside browser synchronization and must not be recorded as an active synchronized view;
- failure to report optional render provenance must reduce precision, not prevent the explicitly included browser client from reconnecting and conservatively reloading;
- startup/restart readiness semantics remain unchanged.

### 10.6 Verification

Add deterministic middleware/component tests for:

- explicit helper context isolation across concurrent requests;
- empty output outside a managed request;
- ordinary buffered HTML with explicit inclusion receiving exactly one client;
- streaming HTML with explicit inclusion preserving chunking while receiving correct CSP/cache headers;
- explicitly encoded HTML remaining byte-for-byte body pass-through;
- late helper use failing conspicuously;
- explicit render provenance using the same render ID as browser registration.

Extend real-browser acceptance with at least:

- a streaming page using explicit inclusion that registers and reloads across a Python restart;
- CSP-protected streaming HTML using explicit inclusion;
- an explicitly integrated streaming Jinja/render-provenance page whose unrelated template change does not reload it.

Do not add separate browser acceptance cases for every pass-through response form unless the browser-observable semantics differ.

### 10.7 Explicit non-goals

Do not:

- make arbitrary streaming HTML automatically injectable;
- buffer an entire stream to recover transparent injection;
- add a second control server or transport;
- require a framework-specific response type;
- add a general template-extension/plugin API;
- make explicit inclusion responsible for application state migration.

Phase 10 is complete when unsupported HTML can opt into the existing synchronization protocol with one explicit script inclusion and gains the same correctness/recovery semantics as transparently injected pages.

## Phase 11: finer conservative fallback scopes

**Status: planned; Phase 10 prerequisite is delivered.**

Replace the current binary choice between precise targeting and application-wide conservative reload with explicitly configured conservative scopes. Preserve application-wide reload as the default whenever no trusted scope rule applies.

The invariant is:

> Scope configuration may narrow uncertainty only when the user has explicitly asserted that a class of changed sources cannot affect views outside the configured URL scope. Missing scope information must never narrow the existing fallback.

### 11.1 Scope rule model

Introduce a small policy type such as:

`FallbackScopeRule(source_pattern, url_pattern)`

and repeated CLI configuration provisionally shaped as:

`--fallback-scope SOURCE_GLOB URL_GLOB`

Examples:

`--fallback-scope 'templates/admin/**' '/admin/**'`

`--fallback-scope 'content/docs/**' '/docs/**'`

Rules are completeness assertions, not heuristics. Document that an incorrect rule can suppress a reload for an actually affected view, just as incorrect explicit dependency metadata can be wrong.

Keep V1 rule semantics deliberately small:

- source patterns are POSIX-style globs matched against paths relative to configured development roots;
- for nested/multiple roots, evaluate every valid root-relative representation and union matching rules;
- URL patterns match the decoded normalized URL path only; ignore query and fragment;
- multiple matching rules for one source path union their URL scopes;
- repeated or overlapping rules are deterministic and idempotent;
- a matching rule whose URL pattern currently matches no active view is a valid scoped result, not an instruction to reload all.

Do not introduce named scope graphs or a configuration language until repetition demonstrates a need.

### 11.2 First refactor invalidation without changing behavior

Before enabling scoped behavior, remove the current early global-ambiguity shortcut from `decide_browser_updates` and represent uncertainty per changed path.

Preserve today's semantics exactly:

- known direct/render/data/resource dependencies remain precise;
- incomplete provenance/resource snapshots reload every uncertain active view;
- completely unknown browser-relevant paths reload every active view;
- action precedence remains `reload > narrow update`;
- generated-output deferral retains precedence where it does today.

Land this as an independently tested refactor. The refactored implementation should still produce application-wide fallback whenever no scope mapping is supplied.

### 11.3 Make scope-matched sources browser-relevant

A configured source rule is also an assertion that matching changes can affect browser output. Therefore matching scope sources must enter browser invalidation even when their suffix is not in the generic browser-suffix set and they are not yet known through render/manifest provenance.

Classification precedence should remain:

`server restart > external HMR ownership > configured fallback scope > generic browser suffix > other`

A Python/restart-worthy change therefore still follows restart semantics, and an externally owned frontend path remains outside Kyth browser action.

### 11.4 Scoped uncertainty resolution

For each browser-relevant changed path:

1. compute all known precise affected/current relationships first;
2. identify only the active views whose dependency relationship to that path remains uncertain;
3. if the path matches one or more fallback-scope rules, intersect that uncertain set with the union of active views whose URL paths match those rules;
4. reload those scoped uncertain views;
5. mark uncertain views outside the asserted scope current for that path;
6. if the path matches no scope rule, retain the existing fallback over the entire uncertain set.

Known affected views are never suppressed by a scope rule. A precise dependency outside a configured fallback scope still wins and receives its normal action.

For batches:

- union affected views across all paths;
- an unmatched ambiguous path may widen its uncertainty to all active views even when another path is scoped;
- full reload still dominates CSS/asset/data updates for the same view;
- scope rules do not narrow `SERVER_RESTART` browser reload semantics in this phase;
- generated-output readiness/deferral remains independent of fallback scoping.

### 11.5 Separate path/URL matching from invalidation policy

Keep glob/URL interpretation out of the invalidation core.

The supervisor should compute a mapping conceptually equivalent to:

`changed path -> scoped candidate view IDs`

and pass that explicit mapping into the pure browser-update decision function. Absence of a key means "no trusted scope; use ordinary conservative fallback." Presence with an empty view set means "the configured scope currently contains no active views."

This keeps `decide_browser_updates` deterministic and easy to property-test without knowing about watch roots, URL decoding, or CLI syntax.

### 11.6 Observability

Scoped fallback must remain explainable.

Verbose diagnostics should expose, for each ambiguous path:

- whether a fallback scope matched;
- the matching source/URL rule or rules;
- active views considered uncertain;
- views selected by the conservative scope;
- whether an unmatched path caused escalation to broader fallback.

Use a stable reason such as `scoped-conservative-fallback` for the final browser decision when scoping materially narrowed an otherwise broader reload. Do not add persistent diagnostic history solely for this feature.

### 11.7 Verification

Add pure policy/property tests for:

- no-rule behavior being identical to current application-wide fallback;
- one source rule targeting only matching URL views;
- several matching rules unioning views;
- overlapping/duplicate rules being idempotent;
- a matching scope with zero active views causing no reload;
- an unmatched ambiguous path retaining global fallback;
- mixed known precise and scoped-uncertain dependencies;
- known affected views outside the configured scope still receiving actions;
- incomplete render/resource provenance narrowing only its uncertain portion;
- mixed batches preserving reload dominance;
- query strings/fragments not changing URL-scope membership;
- nested watch roots producing conservative union behavior.

Add a small real-browser acceptance scenario with two independently scoped pages and an otherwise unknown source file. Changing a source in one configured scope should disturb only that scope; removing the scope configuration should restore application-wide conservative reload.

### 11.8 Explicit non-goals

Do not:

- infer scopes automatically from URL/source naming similarity;
- apply scoped fallback to server-restart paths in the first implementation;
- introduce route-framework awareness;
- build a general dependency graph/configuration DSL;
- weaken precise runtime/manifests/direct-resource provenance in favor of scope rules;
- silently treat a malformed rule as a global or empty scope.

Phase 11 is complete when an ambiguous browser-facing source can be deliberately constrained to a trusted set of active URL views while every unconfigured ambiguity retains today's conservative application-wide behavior.

### Sequencing between Phases 10 and 11

Implement Phase 10 first. It expands which browser documents can participate in the existing view/provenance protocol without changing invalidation policy.

Then implement Phase 11 in two commits/steps:

1. per-path uncertainty refactor with behavior unchanged;
2. scope-rule configuration and narrowing.

After both phases, repeat the normal static/test gates and the Chromium/Firefox browser matrix. Re-run the macOS/Linux lifecycle matrix only if process/socket/watcher code changes; neither phase should require such changes by design.

## Cross-cutting implementation constraints

### Keep the supervisor deterministic

Filesystem batches, classification, state transitions, generation changes, and emitted actions should be represented as explicit data and tested without real browsers or subprocesses where possible.

### Separate mechanism from policy

Watching, process management, dependency tracking, classification, and browser transport should have narrow interfaces. File-extension defaults belong in policy/configuration rather than in process lifecycle code.

### Prefer black-box lifecycle tests at boundaries

The critical integration tests are:

- inherited socket remains usable across child replacement;
- startup failure does not kill the supervisor;
- browser notification waits for readiness;
- duplicate file events collapse into one externally visible update;
- unrelated content changes do not disturb an unaffected active view;
- control connections survive application restarts.

### Avoid speculative generality

Do not introduce plugin frameworks, arbitrary graph engines, or frontend HMR abstractions before a concrete second implementation requires them. Use small protocols and plain data structures first.

## Initial implementation boundary

The first useful vertical slice ends after Phase 4. It should support:

- `kyth package.module:app`;
- supervisor-owned port;
- Python restart;
- startup failure recovery;
- injected browser client;
- readiness-gated full reload.

Phases 5-8 improve reload precision without changing that basic contract.
