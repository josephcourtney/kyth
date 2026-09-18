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

Unknown edges are represented as uncertainty, not silently omitted. The conservative fallback for uncertainty is configured at a scope such as application, template root, or route group.

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
- `POST /views?token=<session-token>` registers or updates one browser view using a JSON object containing `view_id`, `url`, `generation`, and optional `render_id`;
- `OPTIONS /views?token=<session-token>` supports the cross-origin registration preflight;
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

V1 may preserve scroll position and focus as a generic convenience, but it must not preserve arbitrary application state or form data unless the application explicitly opts in.

## 13. CSS update behavior

For an affected external stylesheet currently linked by the document, the browser client creates a generation-specific replacement request, waits for successful load, and then removes or supersedes the previous stylesheet reference.

If the affected stylesheet cannot be mapped unambiguously, is inline, or fails to load, the client falls back to full reload.

A CSS update should not reset document, JavaScript, or form state.

## 14. Asset update behavior

V1 may directly cache-bust images, SVG resources, fonts, or similar assets only when the active DOM/resource relationship is clear and replacement is safe.

Otherwise the supervisor/client falls back to full reload for affected views.

Narrow asset replacement is an optimization; it must never reduce correctness.

## 15. JavaScript behavior

If relevant plain/generated JavaScript changes and no external HMR owner is configured, affected views receive a full reload.

Kyth does not track JavaScript module acceptance boundaries, dispose hooks, component state, or module dependency propagation.

When an external frontend development server owns HMR, Kyth should avoid issuing redundant reloads for changes demonstrably handled by that owner.

## 16. HTML injection

The child-side ASGI wrapper injects the external Kyth browser client only into supported HTML responses.

Injection occurs at the response boundary rather than through application templates. The wrapper is responsible for keeping headers consistent with the modified body, including content length and validators where applicable.

The wrapper should ensure it sees an injectable representation rather than attempting ad hoc mutation of compressed bytes.

Streaming responses that cannot be safely rewritten are passed through and receive reduced zero-touch functionality. Explicit client inclusion may be offered later for such cases.

## 17. Static and generated HTML

When a URL maps directly to a served HTML file, that file is the direct render/output dependency for the view.

Changing another HTML file does not reload the view unless a build manifest or other dependency provider says the current output depends on it.

For generated sites, browser synchronization normally waits for the generated output to change rather than reacting immediately to its source input.

A generator may optionally provide source-to-output dependencies so Kyth can mark outputs stale before or independently of regeneration.

## 18. Template provenance

Template-engine support is provided through dependency providers rather than hard-coded into the supervisor.

A Jinja provider should capture actual runtime template participation where feasible and supplement it with static inheritance/include/import analysis.

Dynamic template names that cannot be determined statically must not be treated as absent dependencies. Runtime capture or conservative fallback applies.

Adapter failure must degrade to conservative page reload rather than stale output.

## 19. Browser-consumed data

A tracked data resource may emit `data-update` for affected views.

If the page has registered an explicit handler for the data identity, that handler may refresh the application state without navigation. Otherwise the generic behavior is full reload.

Kyth does not infer semantic data-to-widget update logic.

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

Verbose diagnostics may include dependency edges, source versions, raw watcher operations, child exit status, and per-view reasoning.

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
