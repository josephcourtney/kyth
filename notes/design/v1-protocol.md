# V1 Runtime and Reload Protocol

This note specifies the concrete V1 behavior implied by `DESIGN.md`. It is subordinate to `DESIGN.md`; if they disagree, `DESIGN.md` governs.

## 1. Runtime topology

A development session contains:

- one supervisor process;
- zero or one active ASGI child process;
- one supervisor-owned application listening socket;
- one supervisor-owned browser control service;
- zero or more active browser views.

The supervisor remains alive across child replacement.

## 2. Application child states

The supervisor models the child explicitly as one of:

- `ABSENT`: no child is running;
- `STARTING`: process exists but application startup has not completed;
- `READY`: startup completed and requests may be served;
- `STOPPING`: graceful shutdown has been requested;
- `FAILED`: the most recent startup attempt failed and no ready child exists.

Only `READY` may be advertised to browsers as an active application generation.

A child transitions to `READY` only after the ASGI lifespan startup sequence has completed successfully. Process creation, successful module import, or an open listening socket alone are insufficient.

Applications may register synchronous or asynchronous checks with `kyth.injection.register_readiness_check`. These checks run in the child only after ASGI lifespan startup succeeds. Every registered check must complete without exception and may not return `False`; otherwise startup is reported as failed, the failed generation is not committed, and the supervisor remains available for a later retry.

## 3. Listening socket ownership

The supervisor creates, binds, and listens on the public application socket before starting the child.

The child receives that socket through an operating-system-supported descriptor inheritance/passing mechanism. The child must not call `bind()` for the public application address.

The supervisor retains ownership for the entire development session. Child shutdown therefore does not close the last reference to the public listening socket.

The implementation must take care not to leak extra descriptor copies into unrelated descendants.

## 4. Restart transaction

A restart is a coordinated transaction over one or more filesystem change batches.

The nominal sequence is:

1. classify the accumulated changes;
2. mark all derived outputs affected by those changes stale;
3. if a child is `READY`, request graceful shutdown;
4. wait up to the configured development grace period;
5. escalate termination if the child does not exit;
6. start a replacement child using the persistent listening socket;
7. wait for explicit readiness or startup failure;
8. if ready, commit a new observable generation;
9. compute browser actions for active views;
10. emit those actions once for the committed generation.

If additional restart-requiring changes arrive while shutdown or startup is in progress, they are accumulated. If the replacement child did not include those changes, exactly one additional restart follows. The implementation should avoid restart storms.

If startup fails, step 8 does not occur. Browser views remain on their previous rendered documents. The supervisor records the failure and waits for another relevant edit.

## 5. Filesystem batches

Filesystem events are normalized into a set of changed paths with operations such as create, modify, and delete. Rename may be represented directly or as delete/create depending on the watcher.

A batch represents one editing/build burst, not necessarily one kernel notification.

The classifier consumes the normalized batch and produces a `ChangeSet` containing at least:

- changed paths;
- whether server restart is required;
- invalidated source/output identities;
- candidate browser update kinds;
- diagnostic reasons.

Order of raw watcher events must not affect the resulting `ChangeSet`.

## 6. Generations

The supervisor maintains a monotonically increasing integer `generation`.

A new generation is created only when the externally observable development state is coherent. Examples include:

- a replacement child has reached `READY` after Python changes;
- a generated HTML artifact has finished changing and is now the served version;
- a CSS asset has reached a stable changed state suitable for browser replacement.

Raw filesystem notifications do not themselves create generations.

Browser events always carry the generation they describe. A browser that reconnects after missing events can compare its last observed generation with the current generation and request or receive the appropriate conservative synchronization action.

Duplicate delivery of the same generation must not cause repeated reloads.

## 7. Browser views

A browser view corresponds to one document context, normally a tab.

The injected client creates a random opaque `view_id` and retains it for the lifetime of the tab/document session using browser storage appropriate to tab scoping.

The supervisor records at least:

- `view_id`;
- current URL;
- current render/output identity when known;
- current generation;
- active dependency identities when known;
- last-seen timestamp.

Views expire after a configurable inactivity interval.

Navigation updates the view registration. Two tabs at the same URL remain distinct views.

## 8. Render identities

A render identity names one server-rendered or generated document representation.

A render record may contain:

- route or served URL;
- direct output file, if any;
- source dependencies;
- source versions observed during rendering;
- generation produced;
- cache state.

The browser does not need to understand dependency details. It receives an opaque render identifier injected into or associated with the response and reports that identity to the supervisor.

## 9. Dependency graph

The core graph is directional:

`source -> output/render -> view`

A source may be:

- Python-side runtime input;
- template;
- content file;
- generated-source input;
- direct static asset;
- browser-consumed data.

An output/render may be:

- a server-rendered HTML response;
- a generated HTML file;
- a CSS asset;
- a JavaScript bundle;
- another directly served asset.

When a source changes, Kyth invalidates reachable derived outputs. It then intersects those outputs with active views.

Unknown edges are represented as uncertainty, not silently omitted. Without an explicit scope rule, each ambiguous changed path conservatively treats every otherwise-unaccounted-for active view as potentially affected.

Repeated `--fallback-scope SOURCE_GLOB URL_GLOB` rules may narrow that uncertain set. Source globs are matched against every valid path representation relative to configured development roots; nested roots therefore union matching rules. URL globs are matched against decoded, normalized active-view URL paths with query and fragment ignored. Multiple source-matching rules union their URL scopes.

A fallback rule is a trusted completeness assertion: it states that an otherwise-unknown matching source cannot affect views outside the declared URL scope. It is not inferred from source/URL naming. A matching source rule whose URL scope contains no active view is therefore a valid no-reload result for uncertainty. If an active view URL cannot be normalized, Kyth retains it conservatively inside a matched source scope.

Precise relationships always dominate the fallback scope. A view known affected through direct output mapping, browser resource tracking, render provenance, semantic data provenance, or generated-output metadata receives its normal action even when it lies outside the configured fallback URL pattern. Conversely, a source path with no matching fallback rule retains the application-wide conservative fallback for uncertain views.

Scope-matched sources are browser-relevant even when their suffix would otherwise classify as `OTHER`. Classification precedence is server restart, external HMR ownership, configured fallback scope, generic browser-facing suffix, then other. Phase 11 does not narrow server-restart browser synchronization.

## 10. Source versions and invalidation

Each tracked source may have an internal monotonically increasing version.

A render records the source versions from which it was produced. A render is stale when any recorded dependency version is older than the current source version.

Stale output need not be rebuilt immediately. Inactive outputs may remain stale until requested.

This allows a shared template change to invalidate many generated/rendered pages while only updating the pages currently displayed.

## 11. Control transport

The default control transport is SSE from supervisor to browser plus ordinary HTTP registration requests from browser to supervisor.

The SSE stream supports automatic browser reconnection and is intentionally not tied to the application child.

Phase 3 defines the control HTTP surface as:

- `GET /events?token=<session-token>&view_id=<view-id>` opens the SSE stream and immediately emits a `sync` event for the current generation;
- `POST /views?token=<session-token>` registers or updates one browser view using a JSON object containing `view_id`, `url`, `generation`, optional `render_id`, and Phase 6 resource snapshot fields `resources`/`resources_complete`;
- `POST /renders?token=<session-token>` accepts child-process render provenance records without browser CORS access;
- `OPTIONS /views?token=<session-token>` supports the cross-origin registration preflight;
- `GET /client.js?token=<session-token>` serves the external browser client with no-store caching;
- `GET /health?token=<session-token>` exposes minimal development diagnostics for the current generation and active-view count.

The control service binds to loopback only. Each development session has an unguessable token. Browser requests with an `Origin` header are accepted only for loopback HTTP(S) origins and the accepted origin is reflected explicitly in CORS responses; wildcard CORS is not used. Requests without an `Origin` header remain available to local development tooling when the token is valid.

On SSE reconnection Kyth does not need to replay Phase 3 events. It emits a fresh `sync` event containing the current generation, which is sufficient for the later browser client to determine whether conservative synchronization is required.

The protocol should use structured event names rather than one undifferentiated reload message.

V1 event kinds are:

- `sync`: establish current generation after connection/reconnection;
- `reload`: full document reload required;
- `css-update`: one or more stylesheet resources changed;
- `asset-update`: one or more directly replaceable assets changed;
- `data-update`: browser-consumed data changed and an optional application handler may act;
- `server-error`: optional diagnostic state for failed startup; this must not itself navigate the page.

Every externally actionable event includes a generation.

## 12. Full reload behavior

The client performs a full reload when:

- the supervisor emits `reload` for the active view;
- a narrow update fails and conservative recovery requires reload;
- reconnection discovers that the browser is stale and no narrower replay is safe.

Before invoking reload, the client records the generation so delivery/reconnection cannot cause an immediate reload loop.

Arbitrary application state is preserved only by explicit opt-in. Immediately before a full reload the client dispatches `kyth:before-reload` with `detail.generation` and `detail.preserve(value)`. If a handler calls `preserve`, Kyth JSON-serializes that value into tab-scoped session storage. The replacement document dispatches `kyth:restore-state` after deferred/module scripts have had an opportunity to register listeners, with `detail.generation` and the preserved `detail.state`. Missing handlers, unserializable values, or restore failures leave normal full-reload behavior unchanged.

## 13. CSS update behavior

Phase 6 registers same-origin browser resource usage with each view. The client combines direct DOM references with Resource Timing entries. Direct references identify resources that may be mutated safely; timing entries broaden dependency detection for resources such as imports or dynamically loaded files.

The client treats the resource snapshot as complete only while the Resource Timing buffer is known not to have filled and the bounded registration payload contains the full observed set. A view with an incomplete snapshot remains conservative for resource changes.

For an affected external stylesheet directly represented by an enabled `<link rel="stylesheet">`, the supervisor emits one targeted `css-update` event containing all changed stylesheet URLs for that view. The client:

1. clones each affected link;
2. gives the replacement a generation-specific cache-busting URL;
3. inserts the replacement adjacent to the old link;
4. waits for every replacement stylesheet to load successfully;
5. removes the old links only after all replacements load;
6. advances its generation and re-registers the view.

If mapping is ambiguous, the stylesheet was only observed rather than directly replaceable, the snapshot is incomplete, or any replacement fails to load, the affected view falls back to full reload.

A CSS update does not reset document, JavaScript, form, focus, or scroll state.

## 14. Asset update behavior

Phase 6 directly cache-busts only image resources for which replacement is generic and observable. The zero-touch client currently treats ordinary `<img src>` elements without `srcset` or a `<picture>` parent as safely replaceable. SVG files loaded through such image elements use the same path.

For an affected directly replaceable image, the supervisor emits one targeted `asset-update` event. The client assigns generation-specific URLs, waits for all affected images to load, and then advances/re-registers the view.

Resource Timing may show that a view consumes an image through CSS, `srcset`, or another mechanism even when it is not safely replaceable. Such an observed-only dependency receives a targeted full reload rather than a narrow asset update.

Fonts are tracked when visible through direct preload/resource observation, but V1 does not attempt to mutate an already-applied font face generically; a relevant font change reloads the affected view. The same conservative rule applies to unsupported asset forms.

A failed narrow update always falls back to full reload. Narrow replacement is an optimization and never marks the view current until the browser confirms success by re-registering at the new generation.

## 15. JavaScript behavior

Phase 6 records directly loaded same-origin scripts and Resource Timing script entries for dependency targeting, but JavaScript remains outside Kyth's narrow-update mechanism.

If relevant plain/generated JavaScript changes and no external HMR owner is configured, affected views receive a full reload.

Kyth does not track JavaScript module acceptance boundaries, dispose hooks, component state, or module dependency propagation.

When an external frontend development server owns HMR, repeated `--external-hmr-on PATTERN` options classify matching browser-facing paths as externally owned. Kyth continues to observe and diagnose those paths but emits no redundant browser action for them. Restart-worthy Python or process-configuration semantics still take precedence.

## 16. HTML injection

The child-side ASGI wrapper injects the external Kyth browser client only into supported HTML responses. The application does not import Kyth and templates do not need development-only markup.

For ordinary HTTP requests the wrapper removes `Accept-Encoding` before invoking the application so common compression middleware produces an injectable representation. If the application nevertheless emits a non-identity `Content-Encoding`, Kyth passes the response through unchanged rather than decompressing arbitrary bytes.

V1 injection applies only to a complete, non-streaming `text/html` response. HEAD responses, informational/no-content/not-modified responses, byte-range responses, explicitly compressed responses, and responses that begin streaming with `more_body=True` are passed through unchanged.

For an injected response Kyth:

- inserts one external `<script>` before `</body>`, before `</html>`, or at the end as a final fallback;
- embeds the control URL, session token, committed/candidate generation, and an opaque render identifier as script data attributes;
- recalculates `Content-Length`;
- removes content-derived cache validators such as ETag/digest and Last-Modified;
- replaces application cache metadata such as `Cache-Control` and `Expires` with development `Cache-Control: no-store` semantics so a full reload cannot be masked by an immutable same-origin response;
- augments an existing CSP narrowly enough to permit the nonce-bearing Kyth script and the exact loopback control origin for script/connect traffic.

The browser client creates a tab-scoped opaque `view_id`, registers `view_id`, current URL, generation, and render ID with `POST /views`, then opens `GET /events`.

A live `sync` event does not itself reload an already connected page because a more specific event for that generation may immediately follow. On initial connection or SSE reconnection, however, `sync` is compared with the page generation and triggers conservative reload if the page is stale. When the browser reports that it is offline, the client closes the active EventSource immediately; connectivity restoration therefore begins from a fresh `sync` rather than applying narrow events that may have been buffered on the old connection.

A `reload` event reloads only when its generation is newer than the document generation. Before navigation, the client stores the target generation in tab-scoped session storage so duplicate delivery or reconnection cannot create a reload loop.

When browser-facing files change without a Python restart, the supervisor first updates the live child generation over process IPC and waits for acknowledgement. Only then does it commit the new generation and publish reload. If that update cannot be confirmed, Kyth falls back to replacing the child before notifying browsers.

Streaming or otherwise non-injectable HTML may opt into the same synchronization protocol explicitly with `kyth.injection.client_script()`. The middleware creates request-local bootstrap metadata before calling the application, including the control URL/token, generation, render ID, and CSP nonce. The helper returns the corresponding external `<script>` element once for the active request and marks the response as explicitly integrated; outside a managed request it returns an empty string.

Explicit inclusion must occur before Kyth has committed response headers. Once the application declares explicit inclusion, the eventual response must be an HTML document rather than HEAD, range, no-content, or non-HTML output. Misuse fails conspicuously in development.

For a valid explicitly integrated document, Kyth does not rewrite body bytes or streaming boundaries. It applies the same development `no-store` policy and augments existing CSP with the request's bootstrap nonce/control origin before forwarding the response start. Because body rewriting is unnecessary, streaming and explicitly encoded HTML are supported. The application is responsible for placing the returned script markup into the document before any application-level compression.

Automatic and explicit inclusion are mutually exclusive for one response. Both use the same render ID, browser client, per-tab identity, registration sequence, resource snapshots, SSE connection, reconnect synchronization, narrow-update handling, data updates, state preservation, and reload fallback. Captured render provenance is reported for either integration path, so explicit streaming pages retain normal selective invalidation.

## 17. Static and generated HTML

Phase 5 adds a narrow direct-output provenance index. A browser URL is eligible for zero-touch direct mapping only when its path names an explicit `.html`/`.htm` document or a trailing-slash `index.html` document. Kyth resolves that relative path against the configured watch roots and accepts the relationship only when exactly one matching file currently exists. Extensionless routes and ambiguous matches remain unknown.

The index records `view -> output file` relationships for active views and retains the identities of outputs that were previously observed even after their views disappear. This permits a known inactive output to change without forcing eager browser work.

Browser invalidation and presentation are separate decisions:

- if every changed browser-facing path is a previously known direct HTML output, only views mapped to those outputs are reloaded;
- other active views with known direct outputs are marked valid through the new generation without navigation;
- active views whose document relationship is unknown are still reloaded conservatively;
- if a changed path is not a known direct output, Kyth falls back to the Phase 4 application-wide reload;
- if a known direct output changes while no active view depends on it and all active views have known unrelated direct outputs, no browser reload occurs.

Targeted events are delivered by view identity through the persistent SSE broker. The global development generation still advances for a coherent browser-facing change, but a generation advance alone does not imply that every view is stale. The control registry records views requiring no browser-side action as valid through that generation. Views receiving reload or narrow resource updates remain stale until navigation or successful resource mutation re-registers them. On SSE reconnect, `sync` therefore carries a per-view `reload_required` decision so a missed/failed action recovers conservatively while an unrelated prior change does not cause a delayed reload.

For generated sites, browser synchronization waits for the generated output to change rather than reacting immediately to its source input.

Phase 8 accepts explicit generated-site dependency manifests via repeated `--manifest PATH` options. Manifest directories are added to the effective development roots automatically, so their sources, outputs, and manifest file remain observable without a separate `--watch`.

The stable V1 manifest schema is JSON:

```json
{
  "version": 1,
  "outputs": [
    {
      "output": "public/index.html",
      "url": "/",
      "sources": [
        "content/index.md",
        "templates/base.html"
      ]
    }
  ]
}
```

Manifest source/output paths are normalized relative paths beneath the manifest directory. V1 manifest outputs are HTML documents. Paths may not be absolute or escape the manifest directory, output entries are unique, and each output declares at least one source. An optional `url` declares the browser path that serves that output; this is useful when a publish directory such as `public/` is mounted as the site root. Explicit URLs are path-only, normalized, and unique across configured manifests.

A source change marks every dependent generated output stale but does not itself disturb the browser. When the generated output later receives an add/modify event, Kyth clears that stale state and applies the normal direct-output/view invalidation rules. A deletion-only output event is not considered ready and therefore does not reload the browser into a transiently missing build artifact.

Inactive stale outputs remain stale without eager browser work. If the output is rebuilt while no dependent view is active, no navigation is required.

## 18. Template provenance

Phase 7 introduces an adapter-neutral render provenance record:

- opaque `render_id`;
- development generation;
- adapter name;
- source dependency set;
- per-source version metadata (`mtime_ns` and size where available);
- a completeness flag.

The injected HTML client already carries the opaque `render_id`; browser registration therefore associates an active view with the exact server render that produced it. Recent render records are kept in a bounded supervisor-owned registry.

The first adapter is zero-touch Jinja tracing. When Jinja is installed in the application environment, the child patches Jinja's normal template lookup/render entry points once and uses a request-scoped context variable to record concrete templates actually used by the request. This captures the root template and runtime template lookups used by inheritance, includes, imports, and runtime-selected names through Jinja's normal environment lookup path.

Every concrete filesystem-backed template is recorded with its source version. Templates without a stable filesystem filename mark the render incomplete instead of pretending the dependency is absent.

After an injectable HTML response completes, the child posts the generic render record to the supervisor-owned `/renders` endpoint. Provenance reporting is development metadata: a reporting transport failure does not fail the application response.

For a changed source known to render provenance, Kyth first compares each recorded source version with the current file. A view already rendered from the current version is not invalidated again.

Then:

- active views whose complete render records include a stale version of that source reload;
- complete render views that do not include the source are marked current without navigation;
- views lacking complete render provenance remain conservative and reload;
- if a source also feeds generated outputs through a Phase 8 manifest, those generated views wait for output regeneration rather than reloading from the source change alone.

This interface is independent of Jinja; later adapters can emit the same render record without changing supervisor invalidation policy.

Application code may also call `kyth.injection.depend_on(path)` during an active injectable render. The path is versioned and added to the same render record as automatic template dependencies, so explicit integration does not create a parallel invalidation mechanism. The call returns `False` outside an active Kyth-managed render, keeping the integration optional for application correctness.

## 19. Browser-consumed data

Application code may call `kyth.injection.depend_on_data(identity, path)` during an active injectable render. Kyth records the path with normal source-version metadata plus the semantic data identity.

When such a source becomes stale, affected views receive a targeted `data-update` event instead of an immediate document reload unless the same change also requires a stronger action. The injected client converts this to a `kyth:data-update` browser event. Its detail contains the semantic `identity`, the committed `generation`, and a `handle(value)` method.

A page handler claims the update by calling `event.detail.handle(...)`; the supplied value may be a promise. Kyth waits for all claimed work before advancing the browser generation and re-registering the view. If any identity is unclaimed, claimed work rejects, or the update is otherwise invalid, the client falls back to a full reload. Kyth does not infer semantic data-to-widget update logic.

Failed child startup emits a structured `server-error` control event at the last committed generation. The injected client exposes this as `kyth:server-error` with `detail.generation` and `detail.message`; receiving the diagnostic does not navigate the page.

## 20. Security boundary

The control service is local-development infrastructure.

Default requirements:

- loopback binding;
- non-permissive origin checks;
- per-session unguessable identifier/token where appropriate;
- no exposure of arbitrary filesystem contents through diagnostic endpoints;
- no trust in browser-supplied paths as filesystem authority.

The development client must not weaken production application behavior outside the Kyth-managed development session.

## 21. Logging contract

At normal verbosity, a logical change cycle should be understandable in one compact sequence, for example:

`templates/about.html changed -> /about invalidated -> 0 active views -> no browser action`

or:

`src/app.py changed -> restart -> child ready -> generation 18 -> 2 views reloaded`

The supervisor retains a structured change-cycle report for the most recent processed batch, including changed paths, classifications, restart request/result, invalidated generated outputs, affected views, browser actions, reason, and resulting generation. Normal logging remains compact; `--verbose` emits the full decision chain.

## 22. V1 acceptance behavior

V1 is behaviorally complete when it can demonstrate all of the following:

1. repeated Python edits replace the child without rebinding the public port;
2. a syntax/import/startup failure leaves the supervisor alive and recoverable;
3. browser reload caused by Python changes occurs only after successful readiness;
4. multiple raw file events from one editing burst produce one externally visible update;
5. directly served HTML that is not displayed can change without reloading unrelated views;
6. a displayed HTML dependency causes only affected views to reload;
7. a shared dependency causes all affected views to reload;
8. CSS changes update active stylesheets without full reload where safe;
9. unknown dependency relationships use conservative reload rather than silently stale content;
10. browser control connections survive application child replacement;
11. generated output is synchronized after the output becomes ready, not merely when its inputs first change;
12. every browser action can be traced to a change batch, dependency decision, and committed generation.
