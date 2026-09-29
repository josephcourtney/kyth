# Review Issues

This file records actionable problems identified by the September 2026 third-party-style review of Kyth 1.0.0. It is a short-lived hardening record rather than a general backlog; resolved items should be marked with their disposition and then folded into normal release history.

## Correctness

### 1. AVIF and BMP resource changes can be ignored

**Severity:** medium

`invalidation.py` treats `.avif` and `.bmp` as hot-updatable image resources, but `changes.py` does not classify those suffixes as browser-facing changes. A directly observed AVIF/BMP resource can therefore be known to provenance while a filesystem change is classified `OTHER` and never reaches browser invalidation.

**Required fix:** keep browser-resource suffix classification consistent with the invalidation resource policy and add regression coverage.

### 2. A view connecting during generation commit can miss invalidation

**Severity:** medium

Browser invalidation snapshots active views before the supervisor commits the next control generation. A document that establishes or refreshes its control registration in the interval between that snapshot and generation commit can miss a targeted action. `ControlService.set_generation()` does not itself reconcile the registering document with the authoritative generation.

**Required fix:** make view registration return authoritative control-generation state and make the browser client conservatively reload whenever registration proves the document is behind. Correctness must not depend on receiving every SSE event.

### 3. Render source identity is weaker than watcher identity

**Severity:** medium

Watcher duplicate suppression uses modification time, change time, size, device, and inode. `SourceVersion`, however, records only modification time and size. A same-size atomic replacement with a preserved modification timestamp can therefore be observed by the watcher but judged current by render/data provenance.

**Required fix:** strengthen `SourceVersion` with filesystem identity metadata and propagate it through render reporting, control-plane parsing, and stale-source comparison. Add an atomic-replacement regression.

## Compatibility and transparency

### 4. Optional Jinja tracing can become a startup dependency

Kyth monkey-patches selected Jinja class methods to obtain zero-touch provenance. If a future or unusual Jinja version changes those members, tracing setup can fail while constructing the child, even though Jinja provenance is intended to be an optional precision optimization.

**Required fix:** detect unsupported adapter shapes and fail soft, leaving conservative generic invalidation available. Preserve failures from the application itself rather than masking them.

### 5. Injection middleware changes request content negotiation globally

The middleware currently strips `Accept-Encoding` before every HTTP request reaches the application so that ordinary HTML tends to remain injectable. That changes application-observable request semantics even for non-HTML routes.

**Required fix:** preserve the incoming request scope. If an application returns content-encoded HTML, leave the response untouched and require explicit `client_script()` integration (or disabled development compression) for synchronization. Document the tradeoff.

### 6. Browser acceptance is not part of a persistent release gate

The 1.0 implementation was validated with Chromium/Firefox acceptance and temporary GitHub Actions workflows, but the repository no longer contains a persistent workflow, and `just release-check` does not include browser acceptance.

**Required fix:** restore persistent CI for the canonical check, strict complexity gate, and Chromium/Firefox browser suite. Make the full release preflight include browser acceptance, with browser installation remaining an explicit prerequisite.

## Documentation and maintenance

### 7. Contributor/release documentation has drift

- `AGENTS.md` refers to a normative `VISION.md`, but this repository has no `VISION.md`.
- `STATUS.md` still describes tagging 1.0.0 as future work although `v1.0.0` is already tagged.
- `pyproject.toml` lists `pytest-asyncio` twice in development dependencies.
- Binding the application server to a non-loopback host can suggest remote-device development even though the browser control service intentionally remains loopback-only.

**Required fix:** reconcile the documentation with the repository state, remove the duplicate dependency, and explicitly document the local-browser control-plane limitation.

## Additional observations

The review also noted that the browser client is embedded as a Python string and therefore relies heavily on the real-browser suite rather than a standalone JavaScript lint/syntax gate. This is a maintainability observation, not a demonstrated correctness defect, and does not require extraction of the client for the current hardening release.

The repository is young and has limited independent adoption evidence. That is not directly fixable in code; release claims should distinguish extensive internal validation from broad field experience.
