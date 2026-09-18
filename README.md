# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and synchronizes browser views with coherent development generations.

The ground-up V1 implementation now includes Phases 1 through 5: supervisor-owned application and control sockets, restartable ASGI lifecycle, filesystem watching, transparent HTML client injection, generation-aware browser reload, and direct static/generated HTML awareness for selective view reload.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root, repeated `--ignore PATH` options to add ignored paths, and `--control-port PORT` when a fixed loopback control port is required. By default Kyth chooses an available control port.

For supported ordinary HTML responses, no application or template changes are required. Streaming, byte-range, and explicitly compressed HTML responses are passed through without injection.

When an active view URL maps unambiguously to an HTML file beneath a watch root, Kyth records that direct output relationship. Later changes to known direct outputs reload only dependent views; unknown relationships still fall back to conservative full reload.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.
