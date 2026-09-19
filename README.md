# Kyth

Kyth is a local development supervisor for Python web applications and generated websites. It restarts server code safely, keeps the public listening socket stable across restarts, and synchronizes browser views with coherent development generations.

The current baseline is **v0.2.0**.

The ground-up V1 implementation now covers the complete design surface: supervisor-owned application and control sockets, restartable ASGI lifecycle, filesystem watching, transparent HTML client injection, generation-aware reload, direct output/resource awareness, narrow CSS/image updates, server-render provenance with zero-touch Jinja tracing, generated-site dependency manifests, configurable runtime restart inputs, explicit render/data dependencies, custom readiness, opt-in browser state preservation, semantic data updates, external-HMR coexistence, and structured decision diagnostics.

Basic usage:

```console
kyth package.module:app
```

Use repeated `--watch PATH` options to override the default current-directory watch root, repeated `--ignore PATH` options to add ignored paths, `--restart-on PATTERN` for additional process-loaded configuration, and `--external-hmr-on PATTERN` for browser assets owned by another development server. `--verbose` exposes the full change-decision chain. Use `--control-port PORT` only when a fixed loopback control port is required; otherwise Kyth chooses one automatically.

For generated sites, pass one or more dependency manifests:

```console
kyth package.module:app --manifest path/to/kyth-manifest.json
```

A V1 manifest is versioned JSON mapping relative HTML outputs to the relative source files that generate them. Outputs may also declare the browser URL that serves them (for example `public/index.html` → `/`). Its directory becomes a development watch root automatically.

For supported ordinary HTML responses, no application or template changes are required. When Jinja is present, Kyth records the actual filesystem-backed templates used by each rendered response and uses that provenance to avoid disturbing views whose complete render did not depend on a changed template.

Direct stylesheet links and safe `<img src>` resources can update in place; JavaScript, fonts, ambiguous resources, incomplete provenance, and failed narrow updates retain full reload as the correctness fallback. Kyth disables stale development response caching so full reload remains a reliable recovery mechanism.

Applications that need more precision may opt in narrowly: `kyth.injection.depend_on(path)` records an explicit render dependency, `depend_on_data(identity, path)` enables targeted `kyth:data-update` events, and `register_readiness_check` delays READY until an application-specific synchronous or asynchronous check succeeds. Browser code can claim data updates with `event.detail.handle(...)`, preserve JSON-serializable state through `kyth:before-reload`, restore it from `kyth:restore-state`, and observe non-navigating `kyth:server-error` diagnostics.

See:

- `DESIGN.md` for project architecture and invariants;
- `notes/design/v1-protocol.md` for concrete V1 runtime and reload behavior;
- `PLAN.md` for implementation sequencing;
- `STATUS.md` for current project state;
- `TODO.md` for immediate work;
- `TESTING.md` for test layers, property-based testing, browser acceptance, and quality tooling.
