# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and synchronizes browser views with coherent development generations.

The ground-up V1 implementation now includes Phases 1 through 8: supervisor-owned application and control sockets, restartable ASGI lifecycle, filesystem watching, transparent HTML client injection, generation-aware reload, direct output/resource awareness, narrow CSS/image updates, server-render provenance with zero-touch Jinja tracing, and generated-site dependency manifests.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root, repeated `--ignore PATH` options to add ignored paths, and `--control-port PORT` when a fixed loopback control port is required. By default Kyth chooses an available control port.

For generated sites, pass one or more dependency manifests:

```console
kyth package.module:app --manifest path/to/kyth-manifest.json
```

A V1 manifest is versioned JSON mapping relative HTML outputs to the relative source files that generate them. Outputs may also declare the browser URL that serves them (for example `public/index.html` → `/`). Its directory becomes a development watch root automatically.

For supported ordinary HTML responses, no application or template changes are required. When Jinja is present, Kyth records the actual filesystem-backed templates used by each rendered response and uses that provenance to avoid disturbing views whose complete render did not depend on a changed template.

Direct stylesheet links and safe `<img src>` resources can update in place; JavaScript, fonts, ambiguous resources, incomplete provenance, and failed narrow updates retain full reload as the correctness fallback.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work.
