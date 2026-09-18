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

After the Phase 1-8 implementation is validated as v0.2.0, prioritize reliability and maintainability before expanding functionality.

Sequence hardening work as follows:

1. characterize the codebase with existing dead-code, complexity, duplication, coverage, and test-category tooling;
2. simplify code where findings identify real maintenance cost, preserving established architecture and invariants;
3. move policy/provenance behavior toward fast hermetic tests while keeping true filesystem, localhost-network, and subprocess behavior in integration/system tests;
4. strengthen failure, race, reconnect, cleanup, watcher-coalescing, and malformed-input coverage;
5. use mutation and property-based testing on pure state/policy layers to identify weak assertions and invariant gaps;
6. add a minimal real-browser acceptance layer for the injected client and narrow-update/fallback behavior;
7. rehearse lifecycle/socket behavior across the supported platform and Python-version matrix.

Do not optimize test-category percentages by relabeling genuinely I/O-bound tests. Improve the boundary between pure policy and I/O mechanisms instead.

## Phase 9: optional application hooks — deferred

Do not implement a general hook framework without a concrete use case that cannot be represented by direct provenance, render records, browser-resource observation, or generated dependency manifests.

If such a use case appears, add the smallest typed extension necessary and preserve the zero-touch fallback. Candidate capabilities remain explicit custom dependency registration, custom readiness, semantic browser data updates, state preservation, or coordination with an external frontend HMR owner.

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
