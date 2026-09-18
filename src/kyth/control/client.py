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

  function reloadForGeneration(generation) {
    if (
      reloading ||
      !Number.isFinite(generation) ||
      generation <= pageGeneration
    ) {
      return;
    }
    reloading = true;
    sessionSet(PENDING_GENERATION_KEY, String(generation));
    location.reload();
  }

  async function registerView() {
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
        }),
      });
    } catch {
      return;
    }
  }

  function connectEvents() {
    const eventsUrl = new URL("/events", control);
    eventsUrl.searchParams.set("token", token);
    eventsUrl.searchParams.set("view_id", viewId);

    const events = new EventSource(eventsUrl);

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
      reloadForGeneration(generationFromPayload(payloadFromEvent(event)));
    });
  }

  registerView().finally(connectEvents);
  addEventListener("pageshow", () => {
    void registerView();
  });
})();
""".strip()
    + "\n"
)
