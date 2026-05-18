(function () {
  "use strict";

  const config = window.OCTO_RUM_CONTEXT || {};

  function syntheticUserDomain() {
    try {
      const raw = String(window.localStorage.getItem("octoSyntheticUserEmail") || "").toLowerCase();
      if (!/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(raw)) return "";
      return raw.split("@").pop() || "";
    } catch (_) {
      return "";
    }
  }

  function cleanValue(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "number" || typeof value === "boolean") return value;
    return String(value).replace(/[^\w .:/-]/g, "").slice(0, 120);
  }

  function cleanAttrs(attrs) {
    const out = {
      app_name: cleanValue(config.appName || "enterprise-crm-portal"),
      page_path: cleanValue(window.location.pathname),
      admin_lab_enabled: Boolean(config.adminLabEnabled),
      synthetic_user_enabled: Boolean(syntheticUserDomain()),
      synthetic_user_domain: cleanValue(syntheticUserDomain()),
    };
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (/email|phone|name|address|token|secret|password|card/i.test(key)) return;
      out[key] = cleanValue(value);
    });
    return out;
  }

  function emit(name, attrs) {
    const payload = cleanAttrs(attrs);
    payload.event_name = cleanValue(name);
    payload.timestamp = Date.now();
    try {
      if (window.apmrum && window.apmrum.api && typeof window.apmrum.api.addAction === "function") {
        window.apmrum.api.addAction(name, payload);
      }
      if (window.performance && typeof window.performance.mark === "function") {
        window.performance.mark(`octo-rum:${name}`, { detail: payload });
      }
      window.dispatchEvent(new CustomEvent("octo:rum-event", { detail: payload }));
    } catch (_) {
      // RUM is optional and must never block the admin lab controls.
    }
  }

  window.octoRumEvent = emit;

  document.addEventListener(
    "click",
    (event) => {
      const target = event.target && event.target.closest && event.target.closest("a,button,[data-rum-action]");
      if (!target) return;
      const action = target.getAttribute("data-rum-action") || target.getAttribute("data-journey") || target.id || target.textContent || target.tagName.toLowerCase();
      emit("ui.click", {
        action,
        control: target.tagName.toLowerCase(),
        admin_lab_card: target.closest(".card")?.id || "",
      });
    },
    { capture: true }
  );

  window.addEventListener("load", () => {
    emit("page.ready", {
      navigation_type: performance.getEntriesByType("navigation")[0]?.type || "unknown",
    });
  });
})();
