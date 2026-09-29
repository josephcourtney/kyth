# Review Issues

This file records actionable problems identified by the September 2026 third-party-style review of Kyth 1.0.0 and their disposition. It is a review-hardening record, not a second general backlog.

## Correctness

### 1. AVIF and BMP resource changes could be ignored — resolved

**Severity:** medium

`invalidation.py` treated `.avif` and `.bmp` as hot-updatable image resources, but `changes.py` did not classify those suffixes as browser-facing changes. A directly observed AVIF/BMP resource could therefore be known to provenance while its filesystem change was classified `OTHER` and never reached browser invalidation.

**Resolution:** `.avif` and `.bmp` are now part of browser-facing change classification, with regression coverage tying the classifier to these supported image types.

### 2. A view connecting during generation commit could miss invalidation — resolved

**Severity:** medium

Browser invalidation snapshots active views before the supervisor commits the next control generation. A document that established its control connection in the interval between that snapshot and generation commit could previously miss a targeted action.

**Resolution:** after committing and publishing a generation, the supervisor now takes a second view snapshot and conservatively reconciles any view that appeared during the decision/commit interval. Such late views receive a reload unless generated-output deferral proves the new output is not ready. A view connecting after that reconciliation point receives the authoritative generation in its initial SSE sync, so correctness no longer depends on receiving an event during the transition. Dedicated regression coverage exercises the late-view case.

### 3. Render source identity was weaker than watcher identity — resolved

**Severity:** medium

Watcher duplicate suppression already used modification time, change time, size, device, and inode, while `SourceVersion` recorded only modification time and size. A same-size atomic replacement with a preserved modification timestamp could therefore be observed by the watcher but judged current by render/data provenance.

**Resolution:** `SourceVersion` now carries change time, device, and inode in addition to modification time and size. Jinja/explicit dependency capture, child-to-control render reporting, control parsing, and stale-source comparison preserve the stronger identity. A regression replaces a source atomically with the same size and preserved mtime and verifies that the render is still detected as stale.

## Compatibility and transparency

### 4. Optional Jinja tracing could become a startup dependency — resolved

Kyth monkey-patches selected Jinja class methods to obtain zero-touch provenance. An incompatible Jinja class shape could previously fail while constructing the child even though Jinja provenance is intended to be an optional precision optimization.

**Resolution:** tracing now validates the required class/method shape before patching and fails soft when that shape is unsupported. Generic conservative synchronization remains available. A regression covers an unsupported future-style Jinja shape.

### 5. Injection middleware changed request content negotiation globally — resolved

The middleware previously stripped `Accept-Encoding` before every HTTP request reached the application so ordinary HTML would tend to remain injectable. That changed application-observable request semantics even for non-HTML routes.

**Resolution:** Kyth now preserves the incoming ASGI request scope, including `Accept-Encoding`. Content-encoded HTML remains untouched and can opt into synchronization with `client_script()` or by disabling application compression during development. Tests and README documentation reflect that contract.

### 6. Browser acceptance was not part of a persistent release gate — resolved

The 1.0 implementation had been validated with Chromium/Firefox acceptance and temporary GitHub Actions workflows, but the repository no longer contained a persistent workflow.

**Resolution:** `.github/workflows/ci.yml` now continuously runs `just check`, `just complexity --strict`, and the Chromium/Firefox browser acceptance suite on pushes and pull requests. Tag release preflight depends on both the canonical/complexity job and the browser job before running `just release-check`. Browser installation remains explicit within the browser CI job and the local development workflow.

## Documentation and maintenance

### 7. Contributor/release documentation had drift — resolved

The review found several inconsistencies:

- `AGENTS.md` was substantially stale workspace-template material and referred to a nonexistent `VISION.md`;
- `STATUS.md` still described tagging 1.0.0 as future work even though `v1.0.0` is already tagged;
- `pyproject.toml` listed `pytest-asyncio` twice in development dependencies;
- binding the application server to a non-loopback host could suggest remote-device synchronization even though the browser control plane intentionally remains loopback-only.

**Resolution:** `AGENTS.md` has been rewritten specifically for Kyth and its actual architecture/tooling; the duplicate dependency was removed; the README now states the loopback-only browser-control limitation; and `STATUS.md`/`TESTING.md` are reconciled with the post-1.0 hardening and persistent CI state.

## Additional observations

The review also noted that the browser client remains embedded as a Python string and therefore relies heavily on the real-browser suite rather than a standalone JavaScript lint/syntax gate. This is a maintainability observation, not a demonstrated correctness defect, and does not justify extracting the client without a concrete need.

The repository is young and has limited independent adoption evidence. That is not directly fixable in code; release claims should continue to distinguish extensive internal validation from broad field experience.
