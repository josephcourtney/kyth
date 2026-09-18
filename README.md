# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and synchronizes browser views with coherent development generations.

The ground-up V1 vertical slice through Phase 4 is now implemented. Kyth provides the supervisor-owned application socket, restartable ASGI child lifecycle, filesystem watching and restart classification, a persistent loopback browser control plane, transparent HTML client injection, per-tab registration, and generation-aware full-page reload.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root, repeated `--ignore PATH` options to add ignored paths, and `--control-port PORT` when a fixed loopback control port is required. By default Kyth chooses an available control port.

For supported ordinary HTML responses, no application or template changes are required. Streaming, byte-range, and explicitly compressed HTML responses are passed through without injection.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.
