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

### Changed

### Deprecated

### Removed

### Fixed

- fix spawned-child socket transfer so socket subclasses do not need to be pickled and narrow multiprocessing context typing to the spawn context actually used

### Security

## [0.0.0] - 2026-04-15

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security
