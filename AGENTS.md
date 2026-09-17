# AGENTS.md

## Purpose

This file defines repository-specific guidance for coding agents working on Kyth.

## Canonical project context

Before implementation work, read:

1. `POLICY.md` for documentation/history rules;
2. `DESIGN.md` for architectural requirements and invariants;
3. `notes/design/v1-protocol.md` for concrete V1 subsystem behavior;
4. `PLAN.md` for sequencing;
5. `STATUS.md` for current state;
6. `TODO.md` for immediate work.

Lower-authority documents must not override higher-authority ones.

## Development rules

- preserve the zero-touch generic mode described in `DESIGN.md`;
- keep supervisor lifecycle, browser control, dependency tracking, and policy/classification separable;
- do not introduce Uvicorn/FastAPI self-reload beneath the Kyth supervisor;
- do not implement Python in-process hot module reloading;
- do not implement a custom JavaScript module HMR system;
- prefer explicit state and deterministic transformations over hidden global coordination;
- use established libraries for non-core functionality where they fit the design;
- add dependencies only when they are needed by the current plan phase;
- add tests at the same time as externally observable behavior;
- keep documentation consistent with `POLICY.md` when architectural intent, plan, state, or immediate work changes.

## Tooling

The ground-up branch intentionally begins without an established Python toolchain configuration. Create the minimal toolchain as part of the initial implementation scaffold rather than restoring obsolete configuration wholesale.

Once project commands exist, use the repository-defined commands rather than bypassing them with ad hoc alternatives.

## Scope discipline

Implement the smallest current plan boundary. Avoid speculative plugin systems, generalized graph frameworks, or framework-specific HMR until a concrete requirement in `PLAN.md` calls for them.
