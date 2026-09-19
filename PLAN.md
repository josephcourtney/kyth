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
