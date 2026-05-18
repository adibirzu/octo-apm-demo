/**
 * Placeholder substitution for the OCTO APM Demo docs site.
 *
 * Pages render commands and config snippets with placeholder tokens like
 * `example.com`, `${DNS_DOMAIN}`, `<COMPARTMENT_OCID>`. Users typing real
 * deployment values into the config panel below get every <code> block on
 * the page rewritten with their values in place — so they can copy-paste
 * runnable commands instead of substituting tokens by hand.
 *
 * Values live in localStorage only — never sent to a server. The original
 * source markdown is untouched; substitution is purely visual.
 */

(function () {
  "use strict";

  // The placeholder catalog. Each entry: token -> { label, placeholder, default }.
  // Tokens are matched literally inside <code> and <pre> blocks.
  const PLACEHOLDERS = [
    {
      pattern: "${DNS_DOMAIN}",
      key: "dns_domain",
      label: "DNS domain",
      placeholder: "example.com",
      help: "Public DNS zone for shop/admin hostnames (e.g. demo.acme.io)",
    },
    {
      pattern: "example.com",
      key: "dns_domain",
      label: "DNS domain",
      placeholder: "example.com",
      help: "(same as DNS_DOMAIN above)",
      hidden: true,
    },
    {
      pattern: "example.test",
      key: "dns_domain",
      label: "DNS domain",
      placeholder: "example.com",
      help: "(same as DNS_DOMAIN above)",
      hidden: true,
    },
    {
      pattern: "example.tld",
      key: "dns_domain",
      label: "DNS domain",
      placeholder: "example.com",
      help: "(same as DNS_DOMAIN above)",
      hidden: true,
    },
    {
      pattern: "<COMPARTMENT_OCID>",
      key: "compartment_ocid",
      label: "Compartment OCID",
      placeholder: "ocid1.compartment.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      help: "Target compartment OCID for this deployment",
    },
    {
      pattern: "<TENANCY_NAMESPACE>",
      key: "tenancy_namespace",
      label: "Tenancy namespace",
      placeholder: "mytenancy",
      help: "OCI tenancy namespace (e.g. mytenancy)",
    },
    {
      pattern: "<OCIR_REGION>",
      key: "ocir_region",
      label: "OCIR region",
      placeholder: "eu-frankfurt-1",
      help: "OCIR region (e.g. eu-frankfurt-1, us-ashburn-1)",
    },
    {
      pattern: "<OCIR_TENANCY>",
      key: "ocir_tenancy",
      label: "OCIR tenancy namespace",
      placeholder: "mytenancy",
      help: "(usually same as tenancy namespace)",
    },
    {
      pattern: "<github-username>",
      key: "github_username",
      label: "GitHub username/org",
      placeholder: "your-org",
      help: "Where your fork lives (e.g. your-org)",
    },
    {
      pattern: "<DEPLOYMENT_PREFIX>",
      key: "deployment_prefix",
      label: "Deployment prefix",
      placeholder: "octo",
      help: "Short prefix for resources (e.g. octo, demo)",
    },
    {
      pattern: "<OCI_REGION>",
      key: "oci_region",
      label: "OCI region",
      placeholder: "eu-frankfurt-1",
      help: "(usually same as OCIR region)",
    },
  ];

  // Group placeholders by `key` so DNS_DOMAIN / example.com / example.test share one input.
  const KEYS = [];
  const KEY_MAP = {};
  for (const p of PLACEHOLDERS) {
    if (!KEY_MAP[p.key]) {
      KEY_MAP[p.key] = {
        key: p.key,
        label: p.label,
        placeholder: p.placeholder,
        help: p.help,
        patterns: [],
      };
      KEYS.push(KEY_MAP[p.key]);
    }
    KEY_MAP[p.key].patterns.push(p.pattern);
  }

  const STORAGE_KEY = "octo-apm-demo-placeholders";

  function loadValues() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function saveValues(values) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch (e) {
      // localStorage disabled — substitution still works for the current page
    }
  }

  // Build the config panel
  function buildPanel(values) {
    const panel = document.createElement("details");
    panel.className = "placeholder-config-panel";
    panel.id = "placeholder-config-panel";

    const summary = document.createElement("summary");
    summary.innerHTML =
      '<span class="placeholder-config-icon">⚙</span> ' +
      '<strong>Configure your deployment</strong> ' +
      '<span class="placeholder-config-hint">— enter your values to personalize every command on this page</span>';
    panel.appendChild(summary);

    const grid = document.createElement("div");
    grid.className = "placeholder-config-grid";

    KEYS.forEach(function (entry) {
      const row = document.createElement("div");
      row.className = "placeholder-config-row";

      const label = document.createElement("label");
      label.setAttribute("for", "placeholder-" + entry.key);
      label.textContent = entry.label;

      const input = document.createElement("input");
      input.type = "text";
      input.id = "placeholder-" + entry.key;
      input.placeholder = entry.placeholder;
      input.value = values[entry.key] || "";
      input.autocomplete = "off";
      input.spellcheck = false;
      input.addEventListener("input", function () {
        const v = loadValues();
        v[entry.key] = input.value;
        saveValues(v);
        applySubstitution();
      });

      const help = document.createElement("small");
      help.textContent = entry.help;

      row.appendChild(label);
      row.appendChild(input);
      row.appendChild(help);
      grid.appendChild(row);
    });

    const footer = document.createElement("div");
    footer.className = "placeholder-config-footer";
    const resetBtn = document.createElement("button");
    resetBtn.type = "button";
    resetBtn.textContent = "Reset to placeholders";
    resetBtn.addEventListener("click", function () {
      saveValues({});
      KEYS.forEach(function (entry) {
        const el = document.getElementById("placeholder-" + entry.key);
        if (el) el.value = "";
      });
      applySubstitution();
    });
    footer.appendChild(resetBtn);
    const note = document.createElement("span");
    note.className = "placeholder-config-note";
    note.textContent = "Values stored in this browser only — never sent to a server.";
    footer.appendChild(note);

    panel.appendChild(grid);
    panel.appendChild(footer);
    return panel;
  }

  // Walk all <code> and <pre> blocks; replace tokens with current values.
  // We preserve the original text via a data attribute so reset works.
  function applySubstitution() {
    const values = loadValues();
    const blocks = document.querySelectorAll(
      "article code, article pre, .md-typeset code, .md-typeset pre"
    );

    blocks.forEach(function (el) {
      // Skip nested <code> inside <pre> — we'll process the <pre> as a whole
      if (el.tagName === "CODE" && el.parentElement && el.parentElement.tagName === "PRE") {
        return;
      }

      // Cache original on first visit
      if (!el.dataset.placeholderOriginal) {
        el.dataset.placeholderOriginal = el.innerHTML;
      }
      let html = el.dataset.placeholderOriginal;

      KEYS.forEach(function (entry) {
        const replacement = values[entry.key];
        if (!replacement) return;
        entry.patterns.forEach(function (token) {
          // Word-boundary safe literal replace
          html = html.split(escapeHtml(token)).join(highlightReplacement(escapeHtml(replacement)));
        });
      });

      el.innerHTML = html;
    });
  }

  function escapeHtml(s) {
    return s
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function highlightReplacement(s) {
    // Wrap user-provided values in a span so they're visually distinct.
    return '<span class="placeholder-substituted">' + s + "</span>";
  }

  // Inject panel into the page when DOM is ready.
  function init() {
    // Only mount on workshop and getting-started pages (where commands matter most)
    const path = window.location.pathname;
    const isTargetPage =
      path.includes("/workshop/") ||
      path.includes("/getting-started/") ||
      path.includes("/operations/") ||
      path.includes("/observability-v2/") ||
      document.body.classList.contains("placeholder-config-enabled");

    if (!isTargetPage) {
      return;
    }

    // Idempotent: if a panel already exists in the current DOM, reuse it.
    // Both the DOMContentLoaded handler AND Material's document$.subscribe
    // can fire on the same page load — without this guard we'd render
    // two panels stacked on top of each other.
    if (document.getElementById("placeholder-config-panel")) {
      applySubstitution();
      return;
    }

    // Insert panel after the H1 if present, otherwise at the top of <article>
    const article = document.querySelector("article.md-content__inner, article.md-typeset, article");
    if (!article) return;

    const values = loadValues();
    const panel = buildPanel(values);

    const firstHeader = article.querySelector("h1");
    if (firstHeader && firstHeader.nextSibling) {
      firstHeader.parentNode.insertBefore(panel, firstHeader.nextSibling);
    } else {
      article.insertBefore(panel, article.firstChild);
    }

    applySubstitution();
  }

  // Material for MkDocs uses instant navigation. When document$ is
  // available, use it as the SOLE init trigger (it fires on every page
  // change, including the first load). Otherwise fall back to the
  // standard DOM lifecycle.
  if (typeof document$ !== "undefined" && document$.subscribe) {
    document$.subscribe(function () {
      // Remove any existing panel so the new page gets a freshly built one
      const old = document.getElementById("placeholder-config-panel");
      if (old) old.remove();
      init();
    });
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
