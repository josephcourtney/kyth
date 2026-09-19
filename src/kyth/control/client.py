from __future__ import annotations

CLIENT_JAVASCRIPT = (
    r"""
(() => {
  const script = document.currentScript;
  if (!(script instanceof HTMLScriptElement)) {
    return;
  }

  const control = script.dataset.kythControl;
  const token = script.dataset.kythToken;
  const injectedGeneration = Number(script.dataset.kythGeneration || "0");
  const renderId = script.dataset.kythRenderId || null;

  if (!control || !token || !Number.isFinite(injectedGeneration)) {
    return;
  }

  const VIEW_KEY = "__kyth_view_id__";
  const PENDING_GENERATION_KEY = "__kyth_pending_generation__";
  const PRESERVED_STATE_KEY = "__kyth_preserved_state__";
  const DEFAULT_RESOURCE_TIMING_CAPACITY = 250;
  const RESOURCE_TIMING_CAPACITY = 5000;
  const MAX_REGISTERED_RESOURCES = 256;
  const CACHE_BUST_KEY = "__kyth_generation__";
  const RESOURCE_REGISTRATION_DELAY_MS = 50;

  let resourceSnapshotComplete =
    performance.getEntriesByType("resource").length < DEFAULT_RESOURCE_TIMING_CAPACITY;
  performance.setResourceTimingBufferSize(RESOURCE_TIMING_CAPACITY);
  performance.addEventListener("resourcetimingbufferfull", () => {
    resourceSnapshotComplete = false;
    void registerView();
  });

  function randomId() {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  }

  function sessionGet(key) {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  }

  function sessionSet(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      return;
    }
  }

  function sessionRemove(key) {
    try {
      sessionStorage.removeItem(key);
    } catch {
      return;
    }
  }

  function absoluteResourceUrl(value) {
    try {
      const url = new URL(value, location.href);
      if (url.origin !== location.origin) {
        return null;
      }
      url.hash = "";
      return url.href;
    } catch {
      return null;
    }
  }

  function resourceKey(value) {
    const absolute = absoluteResourceUrl(value);
    if (absolute === null) {
      return null;
    }
    const url = new URL(absolute);
    url.search = "";
    return url.href;
  }

  function addResource(resources, value, kind, direct = false) {
    const url = absoluteResourceUrl(value);
    const key = resourceKey(value);
    if (url === null || key === null) {
      return;
    }
    const current = resources.get(key);
    if (current === undefined || direct) {
      resources.set(key, {url, kind});
    }
  }

  function safeImageElements() {
    return Array.from(document.querySelectorAll("img[src]")).filter(
      (element) =>
        element instanceof HTMLImageElement &&
        !element.srcset &&
        element.closest("picture") === null
    );
  }

  function resourceSnapshot() {
    const resources = new Map();

    for (const entry of performance.getEntriesByType("resource")) {
      if (!(entry instanceof PerformanceResourceTiming)) {
        continue;
      }
      let kind = "observed";
      if (entry.initiatorType === "script") {
        kind = "javascript";
      } else if (entry.initiatorType === "img") {
        kind = "image";
      }
      addResource(resources, entry.name, kind);
    }

    for (const link of document.querySelectorAll('link[rel~="stylesheet"][href]')) {
      if (link instanceof HTMLLinkElement && !link.disabled) {
        addResource(resources, link.href, "stylesheet", true);
      }
    }

    for (const image of safeImageElements()) {
      addResource(resources, image.src, "image", true);
    }

    for (const preload of document.querySelectorAll('link[rel~="preload"][as="font"][href]')) {
      if (preload instanceof HTMLLinkElement) {
        addResource(resources, preload.href, "font", true);
      }
    }

    for (const source of document.querySelectorAll("script[src]")) {
      if (source instanceof HTMLScriptElement) {
        addResource(resources, source.src, "javascript", true);
      }
    }

    const values = Array.from(resources.values()).sort((left, right) =>
      left.url.localeCompare(right.url)
    );
    const complete =
      document.readyState === "complete" &&
      resourceSnapshotComplete &&
      values.length <= MAX_REGISTERED_RESOURCES;
    return {
      resources: values.slice(0, MAX_REGISTERED_RESOURCES),
      complete,
    };
  }

  let viewId = sessionGet(VIEW_KEY);
  if (!viewId) {
    viewId = randomId();
    sessionSet(VIEW_KEY, viewId);
  }

  const pendingGeneration = Number(sessionGet(PENDING_GENERATION_KEY) || "0");
  let pageGeneration = injectedGeneration;
  if (Number.isFinite(pendingGeneration) && pendingGeneration > pageGeneration) {
    pageGeneration = pendingGeneration;
  }
  sessionRemove(PENDING_GENERATION_KEY);

  let reloading = false;
  let awaitingSync = true;
  let actionChain = Promise.resolve();
  let registrationTimer = null;
  let eventSource = null;

  function payloadFromEvent(event) {
    try {
      return JSON.parse(event.data);
    } catch {
      return null;
    }
  }

  function generationFromPayload(payload) {
    return payload === null ? Number.NaN : Number(payload.generation);
  }

  function eventResources(payload) {
    const resources = payload?.data?.resources;
    return Array.isArray(resources) && resources.every((value) => typeof value === "string")
      ? resources
      : null;
  }

  function eventIdentities(payload) {
    const identities = payload?.data?.identities;
    return Array.isArray(identities) &&
      identities.every((value) => typeof value === "string" && value.length > 0)
      ? identities
      : null;
  }

  function cacheBust(value, generation) {
    const url = new URL(value, location.href);
    url.searchParams.set(CACHE_BUST_KEY, String(generation));
    return url.href;
  }

  function preserveStateForReload(generation) {
    let claimed = false;
    let state;
    const detail = {
      generation,
      preserve(value) {
        claimed = true;
        state = value;
      },
    };
    dispatchEvent(new CustomEvent("kyth:before-reload", {detail}));
    if (!claimed) {
      sessionRemove(PRESERVED_STATE_KEY);
      return;
    }
    try {
      sessionSet(PRESERVED_STATE_KEY, JSON.stringify({generation, state}));
    } catch {
      sessionRemove(PRESERVED_STATE_KEY);
    }
  }

  function restorePreservedState() {
    const raw = sessionGet(PRESERVED_STATE_KEY);
    sessionRemove(PRESERVED_STATE_KEY);
    if (raw === null) {
      return;
    }
    try {
      const preserved = JSON.parse(raw);
      const generation = Number(preserved?.generation);
      if (!Number.isFinite(generation) || generation > pageGeneration) {
        return;
      }
      dispatchEvent(
        new CustomEvent("kyth:restore-state", {
          detail: {generation, state: preserved.state},
        })
      );
    } catch {
      return;
    }
  }

  function reloadForGeneration(generation) {
    if (
      reloading ||
      !Number.isFinite(generation) ||
      generation <= pageGeneration
    ) {
      return;
    }
    reloading = true;
    preserveStateForReload(generation);
    sessionSet(PENDING_GENERATION_KEY, String(generation));
    location.reload();
  }

  async function registerView() {
    const snapshot = resourceSnapshot();
    const url = new URL("/views", control);
    url.searchParams.set("token", token);
    try {
      await fetch(url, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          view_id: viewId,
          url: location.href,
          generation: pageGeneration,
          render_id: renderId,
          resources: snapshot.resources,
          resources_complete: snapshot.complete,
        }),
      });
      return true;
    } catch {
      return false;
    }
  }

  function scheduleRegistration() {
    if (registrationTimer !== null) {
      clearTimeout(registrationTimer);
    }
    registrationTimer = setTimeout(() => {
      registrationTimer = null;
      void registerView();
    }, RESOURCE_REGISTRATION_DELAY_MS);
  }

  async function replaceStylesheets(resources, generation) {
    const targetKeys = new Set(resources.map(resourceKey).filter((value) => value !== null));
    if (targetKeys.size !== resources.length) {
      return false;
    }

    const links = Array.from(document.querySelectorAll('link[rel~="stylesheet"][href]')).filter(
      (link) =>
        link instanceof HTMLLinkElement &&
        !link.disabled &&
        targetKeys.has(resourceKey(link.href))
    );
    const matched = new Set(links.map((link) => resourceKey(link.href)));
    if (matched.size !== targetKeys.size) {
      return false;
    }

    const replacements = [];
    try {
      await Promise.all(
        links.map(
          (link) =>
            new Promise((resolve, reject) => {
              const replacement = link.cloneNode(false);
              replacement.href = cacheBust(link.href, generation);
              replacement.addEventListener("load", () => resolve(), {once: true});
              replacement.addEventListener("error", () => reject(new Error("stylesheet update failed")), {
                once: true,
              });
              replacements.push(replacement);
              link.after(replacement);
            })
        )
      );
    } catch {
      for (const replacement of replacements) {
        replacement.remove();
      }
      return false;
    }

    for (const link of links) {
      link.remove();
    }
    return true;
  }

  async function replaceImages(resources, generation) {
    const targetKeys = new Set(resources.map(resourceKey).filter((value) => value !== null));
    if (targetKeys.size !== resources.length) {
      return false;
    }

    const images = safeImageElements().filter((image) => targetKeys.has(resourceKey(image.src)));
    const matched = new Set(images.map((image) => resourceKey(image.src)));
    if (matched.size !== targetKeys.size) {
      return false;
    }

    const previous = new Map(images.map((image) => [image, image.src]));
    try {
      await Promise.all(
        images.map(
          (image) =>
            new Promise((resolve, reject) => {
              image.addEventListener("load", () => resolve(), {once: true});
              image.addEventListener("error", () => reject(new Error("image update failed")), {
                once: true,
              });
              image.src = cacheBust(image.src, generation);
            })
        )
      );
    } catch {
      for (const [image, source] of previous) {
        image.src = source;
      }
      return false;
    }
    return true;
  }

  async function applyDataUpdates(identities, generation) {
    const pending = [];
    for (const identity of identities) {
      let claimed = false;
      const detail = {
        identity,
        generation,
        handle(value) {
          claimed = true;
          pending.push(Promise.resolve(value));
        },
      };
      dispatchEvent(new CustomEvent("kyth:data-update", {detail}));
      if (!claimed) {
        return false;
      }
    }
    try {
      await Promise.all(pending);
      return true;
    } catch {
      return false;
    }
  }

  async function commitNarrowUpdate(generation) {
    if (generation > pageGeneration) {
      pageGeneration = generation;
    }
    await registerView();
  }

  function enqueue(action) {
    actionChain = actionChain.then(async () => {
      if (!reloading) {
        await action();
      }
    });
  }

  function connectEvents() {
    const eventsUrl = new URL("/events", control);
    eventsUrl.searchParams.set("token", token);
    eventsUrl.searchParams.set("view_id", viewId);

    awaitingSync = true;
    const events = new EventSource(eventsUrl);
    eventSource = events;

    events.addEventListener("open", () => {
      awaitingSync = true;
    });

    events.addEventListener("sync", (event) => {
      const payload = payloadFromEvent(event);
      const generation = generationFromPayload(payload);
      const reloadRequired = payload?.data?.reload_required;

      if (reloadRequired === false) {
        if (Number.isFinite(generation) && generation > pageGeneration) {
          pageGeneration = generation;
        }
        awaitingSync = false;
        return;
      }

      if (reloadRequired === true || awaitingSync) {
        awaitingSync = false;
        reloadForGeneration(generation);
      }
    });

    events.addEventListener("reload", (event) => {
      const payload = payloadFromEvent(event);
      enqueue(async () => reloadForGeneration(generationFromPayload(payload)));
    });

    events.addEventListener("css-update", (event) => {
      const payload = payloadFromEvent(event);
      enqueue(async () => {
        const generation = generationFromPayload(payload);
        const resources = eventResources(payload);
        if (
          resources === null ||
          !Number.isFinite(generation) ||
          generation <= pageGeneration ||
          !(await replaceStylesheets(resources, generation))
        ) {
          reloadForGeneration(generation);
          return;
        }
        await commitNarrowUpdate(generation);
      });
    });

    events.addEventListener("asset-update", (event) => {
      const payload = payloadFromEvent(event);
      enqueue(async () => {
        const generation = generationFromPayload(payload);
        const resources = eventResources(payload);
        if (
          resources === null ||
          !Number.isFinite(generation) ||
          generation <= pageGeneration ||
          !(await replaceImages(resources, generation))
        ) {
          reloadForGeneration(generation);
          return;
        }
        await commitNarrowUpdate(generation);
      });
    });

    events.addEventListener("data-update", (event) => {
      const payload = payloadFromEvent(event);
      enqueue(async () => {
        const generation = generationFromPayload(payload);
        const identities = eventIdentities(payload);
        if (
          identities === null ||
          !Number.isFinite(generation) ||
          generation <= pageGeneration ||
          !(await applyDataUpdates(identities, generation))
        ) {
          reloadForGeneration(generation);
          return;
        }
        await commitNarrowUpdate(generation);
      });
    });

    events.addEventListener("server-error", (event) => {
      const payload = payloadFromEvent(event);
      const generation = generationFromPayload(payload);
      const message = payload?.data?.message;
      if (Number.isFinite(generation) && typeof message === "string") {
        dispatchEvent(new CustomEvent("kyth:server-error", {detail: {generation, message}}));
      }
    });
  }

  function disconnectEvents() {
    awaitingSync = true;
    if (eventSource !== null) {
      eventSource.close();
      eventSource = null;
    }
  }

  function reconnectEvents() {
    disconnectEvents();
    connectEvents();
  }

  const mutationObserver = new MutationObserver(scheduleRegistration);
  mutationObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["href", "src", "srcset", "rel", "as", "disabled"],
  });

  if (typeof PerformanceObserver === "function") {
    const performanceObserver = new PerformanceObserver(scheduleRegistration);
    performanceObserver.observe({type: "resource", buffered: false});
  }

  registerView().finally(connectEvents);
  if (document.readyState === "loading") {
    addEventListener("DOMContentLoaded", restorePreservedState, {once: true});
  } else {
    queueMicrotask(restorePreservedState);
  }
  addEventListener("offline", disconnectEvents);
  addEventListener("online", reconnectEvents);
  addEventListener("load", scheduleRegistration, {once: true});
  addEventListener("pageshow", scheduleRegistration);
})();
""".strip()
    + "\n"
)
