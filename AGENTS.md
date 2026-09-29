# AGENTS.md

## Purpose

This file defines how coding agents must operate when contributing to Kyth.

## Project authority

Read the repository documentation before making changes that depend on architecture or project state:

- `DESIGN.md` is normative for Kyth's intended architecture and invariants.
- `PLAN.md` records implementation sequencing and non-obvious execution strategy.
- `STATUS.md` records the current implementation state and handoff context.
- `TODO.md` contains only immediate unfinished work.
- `CHANGELOG.md` records notable completed user-facing changes.
- `POLICY.md` defines documentation and history responsibilities.
- `TESTING.md` defines the intended validation layers and release evidence.
- `ISSUES.md`, when present, records explicitly identified review/hardening issues.

There is no separate `VISION.md` for this repository.

## Repository layout

- Python package source: `src/kyth/`
- Tests: `tests/`
- Browser acceptance harness: `tests/browser/`
- Repository scripts: `scripts/`
- Architecture contracts: `import-linter.toml`
- Canonical development commands: `justfile`

Do not invent workspace/package boundaries that are not present in this repository.

## Architectural constraints

Preserve the ownership model in `DESIGN.md` and `import-linter.toml`:

- `supervisor` is the runtime orchestration boundary.
- `watcher`, `process`, and `control` are independent mechanisms coordinated by the supervisor.
- `changes`, `invalidation`, `fallback`, and `provenance` are independent policy/domain services.
- `injection` is child-side infrastructure and must not reach back into supervisor-side orchestration.
- `protocol` and `model` remain low-level shared contracts/value objects.

Keep one reload authority. Do not introduce a second watcher/reloader underneath Kyth.

Prefer conservative correctness when dependency information is incomplete. Narrow behavior only from explicit provenance or trusted scope assertions.

Do not introduce speculative plugin frameworks, graph engines, shared utility layers, or frontend-HMR abstractions without a concrete requirement.

## Tooling

Use the root `justfile` as the canonical interface.

### Package management

- Use `uv` for dependency changes, syncing, and execution.
- Add runtime dependencies only when Kyth itself requires them.
- Add development-only tooling to the root development dependency group.

### Validation

Before considering repository changes complete, run the relevant gates:

- `just syntax`
- `just format --check`
- `just lint --no-fix`
- `just typecheck`
- `just lint-imports`
- `just test`
- `just cov`
- `just complexity --strict`

`just check` is the canonical ordinary repository-wide gate.

Browser behavior is a separate required validation surface for changes affecting injection, control synchronization, provenance-driven browser actions, or release readiness:

- install pinned browsers once with `just browser-install`
- run `just browser-test`

Use `just release-check` for source/build/installed-wheel release smoke. The persistent CI release gate additionally requires the browser job to pass.

Mutation testing is diagnostic hardening input rather than a headline release score. Expand its scope only when a concrete policy risk makes additional mutants useful.

### Tests

Use the narrowest truthful categories already defined in `pyproject.toml`.

- `small`: hermetic; no filesystem, network, subprocess, database, or sleep
- `medium`: filesystem, localhost networking, and subprocesses are allowed
- keep policy/property tests pure where practical
- add focused regression tests for fixed correctness defects
- do not relabel I/O-bound tests merely to improve size distribution

## Implementation rules

- Keep domain and invalidation policy out of CLI and transport code.
- Keep filesystem observation separate from classification policy.
- Keep browser transport separate from invalidation decisions.
- Preserve deterministic ordering in paths, actions, and serialized values.
- Use POSIX-style paths in user-visible/configuration formats where specified by the design.
- Preserve the documented 1.x compatibility surface in `README.md` unless an intentional breaking release is being prepared.
- Internal `kyth.*` modules may evolve, but avoid accidental expansion of the public API.
- Prefer deleting obsolete compatibility machinery over layering new behavior onto it when the compatibility surface does not require preservation.
- Prefer established libraries for non-core generic functionality rather than implementing substitutes.

## Documentation and history

Follow `POLICY.md`.

- Keep `STATUS.md` compact and current.
- Keep only immediate unfinished work in `TODO.md`.
- Record notable completed behavior in `CHANGELOG.md`.
- Keep `ISSUES.md` synchronized with any active review-hardening effort; once all items are resolved and captured in release history, it may be removed rather than becoming a permanent second backlog.

Use conventional commit messages for normal commits, for example:

- `fix: reconcile late browser views after generation commit`
- `test: cover atomic render source replacement`
- `docs: clarify loopback control-plane limitation`

Do not claim validation was run unless it actually ran. If the configured toolchain cannot be executed, state that limitation explicitly.
