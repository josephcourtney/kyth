# CHANGELOG.md

Curated, user-facing record, following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

All notable changes to this project will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/)

Items should be categorized under these headings:

- **Added** - new features
- **Changed** - changes in existing functionality
- **Deprecated** - soon-to-be removed features
- **Removed** - now removed features
- **Fixed** - any bug fixes
- **Security** - in case of vulnerabilities

## Unreleased

### Added

- add property-based tests for deterministic batches, conservative invalidation, generation monotonicity, protocol serialization, and direct-path safety
- add hermetic fault-injection tests for render reporting and child readiness/control/shutdown policy
- add a dedicated real-browser acceptance harness running the same contract against Chromium and Firefox
- add browser fixture applications covering direct resources, pass-through responses, real Jinja provenance, generated manifests, multi-view targeting, CSP, reconnect recovery, and readiness-gated restart behavior
- add explicit `browser-install` and `browser-test` development recipes
- add repeated `--restart-on PATTERN` configuration for application-specific process-loaded runtime inputs
- add repeated `--external-hmr-on PATTERN` configuration so an external frontend server can own selected browser changes
- add structured change-cycle reports plus `--verbose` decision-chain diagnostics
- add explicit `depend_on(path)` render dependencies and `depend_on_data(identity, path)` semantic browser-data dependencies
- add targeted `data-update` and non-navigating `server-error` control events
- add `kyth:data-update`, `kyth:server-error`, `kyth:before-reload`, and `kyth:restore-state` browser integration events
- add synchronous/asynchronous `register_readiness_check` application readiness hooks
- add `kyth.injection.client_script()` for explicit synchronization of streaming or otherwise non-injectable HTML through the existing browser-control protocol
- add repeated `--fallback-scope SOURCE_GLOB URL_GLOB` configuration for trusted narrowing of otherwise-conservative browser reload scopes
- add pure fallback-scope matching/validation plus property and real-browser coverage for scoped versus application-wide conservative invalidation
- add hardening coverage for registration ordering, duplicate tabs, reconnect/restart races, generated-output deletion and partial rebuilds, and atomic-save watcher behavior
- add a macOS/Linux lifecycle rehearsal matrix across Python 3.12-3.14
- add a narrow `just mutation` diagnostic for change-classification and protocol policy

### Changed

- suppress duplicate filesystem notifications across logical batches when the observed file state has not changed
- apply development `Cache-Control: no-store` semantics to Kyth-managed ASGI responses so reloads cannot be masked by immutable caches
- narrow generated-source deferral to the outputs that actually depend on each source
- close the browser EventSource while offline and require a fresh sync after connectivity returns
- make browser registrations monotonic by generation and registration sequence so delayed asynchronous registrations cannot replace newer view snapshots
- rekey duplicated-tab view identities when two live documents inherit the same tab-scoped identifier
- strengthen filesystem duplicate detection with change-time and file-identity metadata so atomic replacements are not suppressed solely because size and modification time match
- bound per-browser SSE queues and disconnect slow subscribers on overflow so reconnect synchronization replaces unbounded pending-event growth
- use request-local bootstrap metadata so automatic and explicit client inclusion share generation, render identity, CSP nonce, provenance, registration, reconnect, and reload semantics without rewriting explicit response bodies
- resolve browser invalidation uncertainty per changed path so configured scopes can narrow only uncertain views while precise dependency relationships retain precedence
- classify fallback-scoped sources as browser-relevant regardless of ordinary browser suffix, while preserving server-restart and external-HMR precedence
- expose scoped-fallback rule, uncertain-view, and selected-view details in verbose decision diagnostics

### Fixed

- keep generated views deferred across restart-requiring source changes until their rebuilt generated output is ready
- give generated-output deferral precedence over render-provenance and semantic-data actions for the same view
- bypass Radon 6.0.1's faulty CLI configuration loader with a small wrapper around its public Python API, and stop masking complexity-tool failures as successful strict checks
- run the Hypothesis property layer in a separate plain-assert pytest invocation with an in-memory example database so lazy Hypothesis imports do not violate small-test filesystem isolation while ordinary tests retain assertion rewriting
- remove an artificial zero-duration sleep from the render-reporting transport-failure test
- explicitly reopen the browser EventSource when connectivity returns so stale views always receive a fresh generation sync instead of depending on browser-specific automatic reconnect timing
- open the browser control EventSource before publishing the first view registration so an edit cannot land in the registration-before-SSE gap and force a conservative reload
- keep unreconstructed generated sibling outputs stale when a shared source changes and only one output has rebuilt
- make the hardening test harness local-machine-safe by using an ephemeral supervisor port and disabling pytest/Hypothesis bytecode writes during test execution

## [0.2.0] - 2026-09-18

### Added

- add the Phase 1 development supervisor with a persistent public socket, restartable ASGI child, explicit readiness reporting, bounded shutdown, failure recovery, generation state, and initial CLI
- add Phase 2 filesystem observation with `watchfiles`, configurable watch/ignore paths, deterministic change batches, default restart classification, restart coalescing, and concise change-decision logging
- add the Phase 3 supervisor-owned loopback control plane with token/origin restrictions, generation-aware SSE, browser-view registration, reconnect synchronization, inactive-view cleanup, and lifecycle-independent control state
- add Phase 4 transparent HTML injection, external browser client serving, per-tab registration, generation-aware reloads, CSP/header rewriting, and readiness-gated server-restart reload events
- add Phase 5 direct HTML output provenance, explicit invalidation decisions, targeted per-view SSE delivery, remembered inactive outputs, and per-view reconnect staleness
- add Phase 6 browser resource snapshots, targeted stylesheet replacement, and safe direct image/SVG cache busting
- add Phase 7 adapter-neutral render provenance records with source versions, bounded supervisor storage, and per-view render invalidation
- add zero-touch request-scoped Jinja tracing for filesystem-backed runtime template dependencies
- add render source-version comparison so watcher batches do not reload views that already rendered the current template version
- add Phase 8 stable version-1 generated dependency manifests with source-to-output staleness tracking
- add repeated `--manifest` CLI configuration, optional generated-output browser URLs, and automatic manifest-directory watch roots
- add generated-output readiness handling that waits for add/modify after transient deletion

### Changed

- factor generated-manifest loading, output parsing, indexing, and URL validation into smaller single-purpose validators without changing the version-1 manifest format

- make control-plane generation commits explicit per affected view rather than treating every global generation as universally stale
- keep narrow-update targets stale until browser success is confirmed by re-registration
- treat generated source changes as output invalidation rather than immediate browser synchronization
- keep Jinja and generated-site support optional: applications without either retain the Phase 1-6 zero-touch fallback

### Deprecated

### Removed

### Fixed

- resolve Phase 6 request-handler lint failures by factoring registration parsing and using `TypeError` for invalid JSON value types
- preserve the Phase 5 `known-direct-output` diagnostic reason for direct HTML invalidation
- isolate each spawned application child in a fresh bytecode-cache directory so rapid same-size Python edits cannot restart into stale timestamp/size-validated bytecode
- fix spawned-child socket transfer so socket subclasses do not need to be pickled
- keep injection test token fixtures and URL expectations derived from the same value

### Security

- keep render provenance registration child-only by rejecting browser-Origin requests to `/renders`
- constrain the injected browser client to a nonce-bearing CSP allowance and the exact loopback control origin while retaining token and origin checks on the control service

## [0.0.0] - 2026-04-15

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security
