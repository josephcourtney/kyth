(() => {
  if (window.__PY_DEVSERVER_INSTALLED__) return;
  window.__PY_DEVSERVER_INSTALLED__ = true;

  const WS_PATH = __KYTH_WS_PATH__;
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${WS_PATH}`;
  let ws = null;
  let reconnectTimer = null;
  let intentionallyClosed = false;
  const timers = new Map();
  let connectedOnce = false;
  let closedAfterSuccessfulConnection = false;

  function stringify(value) {
    try {
      if (typeof value === "string") return value;
      if (value instanceof Error) return value.stack || `${value.name}: ${value.message}`;
      return JSON.stringify(value);
    } catch {
      try {
        return String(value);
      } catch {
        return "[unprintable value]";
      }
    }
  }

  function send(type, payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    try {
      ws.send(JSON.stringify({ type, payload }));
    } catch {
    }
  }

  function normalizePath(value) {
    return String(value || "")
      .replaceAll("\\", "/")
      .replace(/[?#].*$/, "");
  }

  function cacheBustedUrl(href) {
    const url = new URL(href, location.href);
    url.searchParams.set("__kyth_reload", String(Date.now()));
    return url.pathname + url.search + url.hash;
  }

  function elementUrlPath(value) {
    try {
      return decodeURIComponent(new URL(value, location.href).pathname).replaceAll("\\", "/");
    } catch {
      return "";
    }
  }

  function urlMatchesChangedPath(urlPath, changedPath) {
    const normalizedUrlPath = normalizePath(urlPath);
    const normalizedChangedPath = normalizePath(changedPath);

    if (!normalizedUrlPath || !normalizedChangedPath) return false;

    return (
      normalizedUrlPath.endsWith(normalizedChangedPath) ||
      normalizedChangedPath.endsWith(normalizedUrlPath.replace(/^\/+/u, "")) ||
      normalizedUrlPath.split("/").pop() === normalizedChangedPath.split("/").pop()
    );
  }

  function stylesheetMatchesPath(link, changedPath) {
    const href = link.getAttribute("href");
    if (!href) return false;

    return urlMatchesChangedPath(elementUrlPath(href), changedPath);
  }

  function reloadStylesheets(paths) {
    const links = Array.from(document.querySelectorAll('link[rel~="stylesheet"][href]'));
    let updated = false;

    for (const link of links) {
      if (!paths.some((path) => stylesheetMatchesPath(link, path))) continue;

      const oldHref = link.getAttribute("href");
      if (!oldHref) continue;

      const clone = link.cloneNode();
      clone.setAttribute("href", cacheBustedUrl(oldHref));

      clone.addEventListener("load", () => {
        link.remove();
      });

      clone.addEventListener("error", () => {
        clone.remove();
        fullReload();
      });

      link.after(clone);
      updated = true;
    }

    if (!updated) {
      fullReload();
    }
  }

  function refreshUrlAttribute(element, attributeName) {
    const value = element.getAttribute(attributeName);
    if (!value) return false;

    element.setAttribute(attributeName, cacheBustedUrl(value));
    return true;
  }

  function refreshSrcsetAttribute(element) {
    const value = element.getAttribute("srcset");
    if (!value) return false;

    const refreshed = value
      .split(",")
      .map((candidate) => {
        const parts = candidate.trim().split(/\s+/u);
        if (parts.length === 0 || !parts[0]) return candidate;

        const url = cacheBustedUrl(parts[0]);
        return [url, ...parts.slice(1)].join(" ");
      })
      .join(", ");

    element.setAttribute("srcset", refreshed);
    return true;
  }

  function assetElementMatchesPath(element, changedPath) {
    for (const attributeName of ["src", "href", "poster"]) {
      const value = element.getAttribute(attributeName);
      if (value && urlMatchesChangedPath(elementUrlPath(value), changedPath)) return true;
    }

    const srcset = element.getAttribute("srcset");
    if (srcset) {
      for (const candidate of srcset.split(",")) {
        const url = candidate.trim().split(/\s+/u)[0];
        if (urlMatchesChangedPath(elementUrlPath(url), changedPath)) return true;
      }
    }

    return false;
  }

  function reloadAssets(paths) {
    const selector = [
      "img[src]",
      "img[srcset]",
      "source[src]",
      "source[srcset]",
      "video[poster]",
      "link[rel~='icon'][href]",
      "link[rel='apple-touch-icon'][href]"
    ].join(",");

    const elements = Array.from(document.querySelectorAll(selector));
    let updated = false;

    for (const element of elements) {
      if (!paths.some((path) => assetElementMatchesPath(element, path))) continue;

      if (element.hasAttribute("src")) {
        updated = refreshUrlAttribute(element, "src") || updated;
      }

      if (element.hasAttribute("href")) {
        updated = refreshUrlAttribute(element, "href") || updated;
      }

      if (element.hasAttribute("poster")) {
        updated = refreshUrlAttribute(element, "poster") || updated;
      }

      if (element.hasAttribute("srcset")) {
        updated = refreshSrcsetAttribute(element) || updated;
      }
    }

    if (!updated) {
      fullReload();
    }
  }

  function saveReloadState() {
    const active = document.activeElement;
    const state = {
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      activeElementId: active && active.id ? active.id : null
    };

    try {
      sessionStorage.setItem("__kyth_reload_state", JSON.stringify(state));
    } catch {
    }
  }

  function restoreReloadState() {
    let state = null;

    try {
      const raw = sessionStorage.getItem("__kyth_reload_state");
      sessionStorage.removeItem("__kyth_reload_state");
      if (raw) state = JSON.parse(raw);
    } catch {
      return;
    }

    if (!state) return;

    if (state.activeElementId) {
      const element = document.getElementById(state.activeElementId);
      if (element && typeof element.focus === "function") {
        try {
          element.focus({ preventScroll: true });
        } catch {
          element.focus();
        }
      }
    }

    if (Number.isFinite(state.scrollX) && Number.isFinite(state.scrollY)) {
      window.scrollTo(state.scrollX, state.scrollY);
    }
  }

  function fullReload() {
    saveReloadState();
    location.reload();
  }

  function connect() {
    ws = new WebSocket(WS_URL);

    ws.addEventListener("open", () => {
      if (connectedOnce && closedAfterSuccessfulConnection) {
        fullReload();
        return;
      }

      connectedOnce = true;
      closedAfterSuccessfulConnection = false;

      send("hello", {
        url: location.href,
        title: document.title || "",
        userAgent: navigator.userAgent
      });
    });

    ws.addEventListener("message", (event) => {
      let msg;

      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }

      const paths = Array.isArray(msg.paths) ? msg.paths.map(String) : [];

      if (msg.type === "css-reload") {
        reloadStylesheets(paths);
        return;
      }

      if (msg.type === "asset-reload") {
        reloadAssets(paths);
        return;
      }

      if (msg.type === "reload") {
        fullReload();
      }
    });

    ws.addEventListener("close", () => {
      if (intentionallyClosed) return;

      closedAfterSuccessfulConnection = connectedOnce;

      if (reconnectTimer) return;

      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, 500);
    });
  }

  for (const level of ["log", "info", "warn", "error", "debug"]) {
    const original = console[level] ? console[level].bind(console) : null;

    console[level] = (...args) => {
      try {
        if (original) original(...args);
      } finally {
        send("console", {
          level,
          url: location.href,
          args: args.map(stringify)
        });
      }
    };
  }

  const originalTime = console.time ? console.time.bind(console) : null;
  const originalTimeLog = console.timeLog ? console.timeLog.bind(console) : null;
  const originalTimeEnd = console.timeEnd ? console.timeEnd.bind(console) : null;

  console.time = (label = "default") => {
    timers.set(String(label), performance.now());
    if (originalTime) originalTime(label);
  };

  console.timeLog = (label = "default", ...args) => {
    const key = String(label);
    const start = timers.get(key);

    if (start != null) {
      const ms = performance.now() - start;

      send("console", {
        level: "info",
        url: location.href,
        args: [`${key}: ${ms.toFixed(3)}ms`, ...args.map(stringify)]
      });
    }

    if (originalTimeLog) originalTimeLog(label, ...args);
  };

  console.timeEnd = (label = "default") => {
    const key = String(label);
    const start = timers.get(key);

    if (start != null) {
      const ms = performance.now() - start;

      send("console", {
        level: "info",
        url: location.href,
        args: [`${key}: ${ms.toFixed(3)}ms - timer ended`]
      });

      timers.delete(key);
    }

    if (originalTimeEnd) originalTimeEnd(label);
  };

  window.addEventListener("error", (event) => {
    send("console", {
      level: "error",
      url: location.href,
      args: [
        `window.onerror: ${event.message}`,
        event.filename ? `file: ${event.filename}` : "",
        Number.isFinite(event.lineno) ? `line: ${event.lineno}` : "",
        Number.isFinite(event.colno) ? `col: ${event.colno}` : ""
      ].filter(Boolean)
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    send("console", {
      level: "error",
      url: location.href,
      args: ["unhandledrejection", stringify(event.reason)]
    });
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restoreReloadState, { once: true });
  } else {
    restoreReloadState();
  }

  connect();
})();
