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

### Fixed

- bypass Radon 6.0.1's faulty CLI configuration loader with a small wrapper around its public Python API, and stop masking complexity-tool failures as successful strict checks
- run the Hypothesis property layer in a separate plain-assert pytest invocation with an in-memory example database so lazy Hypothesis imports do not violate small-test filesystem isolation while ordinary tests retain assertion rewriting
- remove an artificial zero-duration sleep from the render-reporting transport-failure test

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
