# Kyth Design

## Purpose

Kyth is a development supervisor for Python web applications and generated websites. It keeps a restartable server process and one or more browser views synchronized with filesystem changes while avoiding unnecessary restarts and page reloads.

Kyth is intended to be useful with no changes to application source code or page content. Optional integrations may improve precision or enable narrower updates, but correctness must not depend on application cooperation.

## Goals

Kyth must:

- run an ASGI application from an import target;
- restart executing Python when server code or runtime configuration changes;
- keep the public application socket bound across normal server restarts;
- reload affected browser views only after replacement server state or generated output is ready;
- distinguish invalidation from browser disturbance;
- avoid reloading views whose displayed content is known not to depend on changed inputs;
- hot-update simple browser resources where doing so is safe and generic;
- remain useful without framework-specific application changes;
- degrade conservatively when dependency information is incomplete;
- keep reload decisions observable and explainable.

## Non-goals

Kyth is not:

- a production process manager;
- a generic JavaScript module HMR implementation;
- an in-process Python module reloader;
- a frontend build system;
- an application state migration system;
- a substitute for Vite or equivalent framework-aware frontend tooling;
- a distributed development coordinator.

Kyth may integrate with such systems but does not reproduce their domain-specific behavior.

## Core architecture

Kyth has one long-lived supervisor and one restartable application child.

The supervisor owns:

- filesystem watching and change batching;
- change classification;
- the public application listening socket;
- application child lifecycle;
- application readiness state;
- the browser control service;
- generation numbers;
- active browser-view state;
- dependency and invalidation state.

The application child owns only application execution. It receives the already-bound application socket, imports the configured ASGI application, runs normal ASGI lifespan startup and shutdown, and reports readiness to the supervisor.

The browser receives a small development client by transparent HTML-response injection where possible. That client maintains a control connection to the supervisor and applies typed update events.

The child process must not independently watch files, bind the public application port, or own the browser control plane.

## Architectural invariants

### One reload authority

Exactly one subsystem decides whether a filesystem change requires process restart, resource invalidation, browser update, or no action. Kyth must not layer an independent Uvicorn reload loop underneath its own watcher.

### Stable public socket

The supervisor binds the application address once for the lifetime of the development session. Application children inherit or receive that socket. Normal child replacement therefore does not require releasing and rebinding the public port.

### Readiness before reload

Starting a process is not equivalent to application readiness. A browser update caused by server replacement may be emitted only after the new child has completed startup and is able to serve the new generation.

### Supervisor survives child failure

Import errors, syntax errors, lifespan failures, and application crashes must not terminate the supervisor or browser control service. A subsequent relevant filesystem change must be able to trigger another startup attempt.

### Invalidation is separate from presentation

A changed source invalidates outputs derived from it. Browser disturbance is a second decision based on whether any invalidated output contributes to a currently active view.

Known unrelated changes must not reload a view merely because they share a file type with displayed content.

### Conservative uncertainty

Dependency precision is optional; stale output is not. When Kyth cannot determine whether a changed source affects a current view, it must use the configured conservative fallback, normally a full reload of the affected scope.

### Completed-state generations

Externally observable development states are identified by monotonically increasing generations. A generation advances only when Kyth has reached a coherent state browsers may safely observe. Duplicate filesystem notifications must not imply duplicate browser-visible generations.

## Change model

Filesystem events are batched into logical change sets. Each relevant path is classified by effect rather than only by extension.

The core effects are:

- `SERVER_RESTART`: executing Python or process-loaded configuration may have changed;
- `FULL_RELOAD`: a displayed resource changed and no narrower generic update is safe;
- `CSS_UPDATE`: an active stylesheet can be replaced without reloading the document;
- `ASSET_UPDATE`: a directly referenced browser asset can be invalidated or cache-busted;
- `DATA_UPDATE`: browser-consumed data changed and may be handled by an optional application hook;
- `INVALIDATE_ONLY`: derived output became stale but no active view currently uses it;
- `IGNORE`: no development action is required.

A single change batch may imply multiple effects. Server restart dominates browser timing: any browser update attributable to the same batch waits for successful replacement-server readiness.

## Restart semantics

When a restart is required, Kyth requests graceful shutdown of the old child, waits only for a bounded development-oriented grace period, and then escalates termination if necessary. The replacement child starts using the supervisor-owned listening socket.

If startup succeeds, the supervisor activates the new generation and then evaluates affected views.

If startup fails, the failed generation is never advertised as ready. Existing browser documents remain in place, the supervisor reports the failure, and the next relevant edit may retry startup.

Connections already owned by the old child are not migrated. New connections may remain queued on the supervisor-owned listening socket during a short restart, subject to normal operating-system backlog limits.

## Browser control plane

The browser control plane is independent of the restartable application child and survives child replacement.

The default supervisor-to-browser transport is Server-Sent Events because the generic protocol is predominantly one-way. A small HTTP registration/update endpoint may be used for browser-to-supervisor view state. A future bidirectional transport may be introduced only if it materially simplifies richer runtime interaction.

The control plane is development-only. It binds to loopback by default and must not use permissive cross-origin behavior. Per-session unguessable state should be used where needed to prevent unrelated local pages from controlling or subscribing to a session.

## Transparent browser integration

Where an ASGI response is ordinary HTML, Kyth wraps the application and injects a small external development client. The application need not import Kyth or modify templates.

The injected client is responsible for:

- assigning and retaining a per-tab view identity;
- connecting and reconnecting to the control service;
- tracking the most recently observed generation;
- registering the active render/document identity;
- applying typed update events;
- performing full reload as the correctness fallback.

Kyth should avoid changing application semantics beyond development synchronization. Unsupported response forms, such as streaming or explicitly encoded HTML, may opt into the same browser protocol through explicit client inclusion rather than fragile response rewriting. Kyth must leave such bodies untouched while preserving the same generation, view, provenance, CSP, reconnect, and reload semantics.

## Views, renders, and provenance

A view represents one open browser document, normally one tab.

A render represents the output currently displayed by a view. A render may record the source files and generated artifacts that contributed to it.

Kyth maintains a dependency path conceptually equivalent to:

`source -> derived/rendered output -> active view`

When a source changes, dependent outputs become stale. Kyth then determines whether those stale outputs are mounted in active views.

Dependency information may come from, in descending order of precision:

1. runtime render provenance;
2. build/generator dependency manifests;
3. static template analysis;
4. direct static-file serving relationships;
5. explicit integration APIs;
6. conservative configured scopes.

Runtime provenance is preferred when dynamic template selection makes static dependency analysis incomplete.

## Zero-touch capability levels

### Generic mode

With no application changes, Kyth must provide:

- process restart;
- persistent application socket ownership;
- readiness-gated browser reload;
- transparent browser-client injection for supported HTML responses;
- per-tab tracking;
- generation tracking;
- full reload;
- CSS replacement;
- direct static/generated-file invalidation;
- conservative handling of unknown server-rendered dependencies.

### Automatic adapters

Framework/template adapters may add precise provenance without requiring application source modifications. Such adapters are optional optimizations and must not become correctness dependencies.

### Explicit integration

Applications may optionally include the Kyth client explicitly for non-injectable HTML, register custom dependencies, data-refresh behavior, richer state-preservation hooks, or custom readiness checks. Explicit client inclusion reuses the normal browser-control protocol rather than defining a second synchronization path. Failure to opt in must still leave generic reload behavior correct for automatically injectable pages.

## Resource update policy

### HTML and templates

HTML/template changes first invalidate dependent renders. Only active views using stale renders should reload when provenance is known. Unknown relationships use conservative scope reload.

### CSS

A relevant external stylesheet should be replaced or cache-busted without a full document reload. Failure to perform a safe stylesheet update falls back to full reload.

### JavaScript

Plain or generated JavaScript without an external HMR owner causes a full reload when relevant. Kyth does not implement a JavaScript module graph.

If a dedicated frontend dev server owns JavaScript HMR, Kyth should coexist with it rather than duplicate its behavior.

### Images, SVG, fonts, and similar assets

Kyth may cache-bust directly referenced resources when the mapping is clear. Full reload remains the fallback.

### Browser-consumed data

Kyth may emit typed data-change events. An application-specific handler may refresh data in place; otherwise relevant changes fall back to a full reload.

## Generated output

When frontend or static-site source is transformed before serving, the generated/served artifact is normally the browser synchronization boundary. Kyth must not reload merely because an input changed if the output consumed by the browser has not yet been updated.

Generators may provide dependency manifests so Kyth can invalidate generated pages from source changes before or without rebuilding all outputs. Such manifests are optional integrations.

## Caching

Kyth must prevent stale development caches from masking known changes. Cache invalidation/versioning and browser reload are distinct operations.

A resource may become stale without any currently open view requiring immediate action. Kyth may retain stale cached entries and regenerate them lazily when requested.

## Error handling

The supervisor must remain recoverable across:

- syntax and import errors;
- ASGI startup failures;
- child crashes;
- duplicate filesystem events;
- transient file disappearance during atomic saves;
- browser control-channel disconnection;
- malformed or temporarily incomplete generated outputs;
- failed narrow browser updates.

Where a narrow browser update fails, the client should fall back to a full reload when possible.

## Observability

Reload decisions must be explainable. For each meaningful change batch, Kyth should be able to report:

- changed paths;
- classifications;
- whether a server restart occurred;
- whether replacement startup succeeded;
- invalidated outputs;
- affected views;
- browser actions;
- resulting generation.

Default output should remain concise; verbose diagnostics may expose the full decision chain.

## Compatibility boundary

The primary server boundary is ASGI rather than FastAPI or Starlette specifically. Framework-specific integrations may exist above that boundary, but the supervisor, socket lifecycle, generation model, control plane, and generic injection behavior must remain framework-independent.

V1 targets local development on operating systems where a supervisor can pass or inherit a listening socket to the child process. Platform-specific details belong in implementation notes rather than changing these invariants.
