# ADR-0001: Separate application interpreter

- Date: 2026-11-20
- Status: Accepted

## Context

A globally installed Kyth executable could not import a local `src/`-layout
application when Kyth's interpreter lacked the project's packages. Requiring
Kyth inside every application environment coupled the development supervisor to
unrelated client dependency graphs.

## Decision

The CLI launches an application worker using the project's `.venv/bin/python`
by default, with `--python` and `--app-dir` overrides. The supervisor remains
in its own interpreter. The worker receives the stable listening socket and a
private lifecycle channel through inherited file descriptors, and imports the
Kyth runtime from Kyth's own installation without installing a project
dependency. Project-installed server dependencies are preferred; Kyth's
pure-Python Uvicorn dependencies are a fallback. The programmatic supervisor
continues to support the original multiprocessing worker.

## Consequences

- A project's dependency manifest and environment need not include Kyth.
- Cross-interpreter execution works for supported Python versions and POSIX
  socket descriptor passing; it requires explicit end-to-end qualification.
- Kyth's child-side Python code still runs in the application process to
  preserve ASGI response injection, template provenance, and readiness hooks.
- The fallback import path exposes the Kyth installation's runtime packages at
  lower priority than the project's packages. This is pragmatic import
  isolation, not a security sandbox or complete package namespace isolation.

## Dependency synchronization and failure recovery

Kyth does not manage dependency installations. Changes to `pyproject.toml` and `uv.lock` are coalesced over a bounded quiet interval before restarting, and transient startup failures associated with those changes are retried at most five times. Failure does not commit a new browser generation; the supervisor retains its control plane and the next successful worker start performs the normal readiness-gated browser synchronization. The retry budget is finite to avoid obscuring permanently broken environments.

Cross-interpreter tests exercise host and child Python versions 3.12–3.14 on Linux and macOS. Each isolated test environment deliberately excludes Kyth and Uvicorn, so the child runtime falls back to the standalone supervisor's installation.

## Alternatives

- Shared interpreter (`uv run --with-editable`): simpler, but couples
  supervisor execution to the application environment.
- HTTP reverse proxy: isolates processes more strictly, but loses the existing
  zero-touch ASGI/template integration and changes socket ownership semantics.
- Installing a dedicated runtime wheel in each project: creates environment
  mutations and an ongoing dependency-management burden.
