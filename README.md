# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and will update only browser views affected by changed content when dependency information is available.

The ground-up V1 implementation is in progress. Phases 1 and 2 now provide the supervisor-owned application socket, restartable ASGI child lifecycle, explicit readiness reporting, bounded shutdown, failure recovery, filesystem watching, deterministic change batches, default restart classification, and restart coalescing. Browser synchronization begins in Phase 3.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root and repeated `--ignore PATH` options to add ignored paths.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.
