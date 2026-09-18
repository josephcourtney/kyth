# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and will update only browser views affected by changed content when dependency information is available.

The ground-up V1 implementation is in progress. Phases 1 through 3 now provide the supervisor-owned application socket, restartable ASGI child lifecycle, filesystem watching and restart classification, and a persistent loopback browser control plane with generation-aware SSE and browser-view registration. Transparent browser-client injection begins in Phase 4.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root, repeated `--ignore PATH` options to add ignored paths, and `--control-port PORT` when a fixed loopback control port is required. By default Kyth chooses an available control port.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.
