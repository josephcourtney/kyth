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

- add the Phase 1 development supervisor with a persistent public socket, restartable ASGI child, explicit readiness reporting, bounded shutdown, failure recovery, generation state, and initial CLI
- add Phase 2 filesystem observation with `watchfiles`, configurable watch/ignore paths, deterministic change batches, default restart classification, restart coalescing, and concise change-decision logging
- add the Phase 3 supervisor-owned loopback control plane with token/origin restrictions, generation-aware SSE, browser-view registration, reconnect synchronization, inactive-view cleanup, and lifecycle-independent control state
- add Phase 4 transparent HTML injection, external browser client serving, per-tab registration, generation-aware reloads, CSP/header rewriting, and readiness-gated server-restart reload events
- add acknowledged live-child generation updates so browser-facing changes can reload current content without restarting Python
- add Phase 5 direct HTML output provenance, explicit invalidation decisions, targeted per-view SSE delivery, remembered inactive outputs, and per-view reconnect staleness

### Changed

- replace the unused `watchdog` development dependency with the runtime `watchfiles` dependency used by Kyth
- load the ASGI import target in the child before Uvicorn startup so Kyth can install the transparent development wrapper without application changes
- make control-plane generation commits silent by default; browser reload/sync actions are now emitted explicitly for the views affected by an invalidation decision
- use `http.HTTPStatus` constants consistently for HTTP response semantics

### Deprecated

### Removed

### Fixed

- isolate each spawned application child in a fresh bytecode-cache directory so rapid same-size Python edits cannot restart into stale timestamp/size-validated bytecode
- fix Phase 3 control-plane lint and typing issues around HTTP handler overrides, SSE stream setup, static logging policy, and watcher context-manager documentation
- fix spawned-child socket transfer so socket subclasses do not need to be pickled and narrow multiprocessing context typing to the spawn context actually used
- keep injection test token fixtures and URL expectations derived from the same value

### Security

- constrain the injected browser client to a nonce-bearing CSP allowance and the exact loopback control origin while retaining token and origin checks on the control service

## [0.0.0] - 2026-04-15

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security
