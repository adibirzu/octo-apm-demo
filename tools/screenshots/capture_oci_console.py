#!/usr/bin/env python3
"""
OCI Console screenshot capture for octo-apm-demo workshop docs.

Two ways to run:

  A) Interactive (run in Terminal.app, not through Claude):
       python3 tools/screenshots/capture_oci_console.py

  B) Sentinel-file mode (works from any shell, no TTY needed):
       python3 tools/screenshots/capture_oci_console.py --sentinel

     Between each step, create the next sentinel file from another
     terminal:
       touch /tmp/oci-capture-go

Before each screenshot the script injects a DOM scrub step that replaces
visible tenancy-specific text with neutral placeholders.
"""

from pathlib import Path
import argparse
import os
import sys
import time
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "site" / "assets" / "screenshots" / "oci"
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1440, "height": 900}
SENTINEL = Path("/tmp/oci-capture-go")

SCRUB_JS = r"""
() => {
  const REPLACEMENTS = [
    [/ocid1\.[a-z]+\.oc1\.[a-z0-9-]*\.[a-z0-9]{40,}/g, '<ocid>'],
    [/ocid1\.[a-z]+\.oc1\.\.[a-z0-9]+/g, '<ocid>'],
    [/ocid1\.[a-z]+\.[a-z0-9.-]+/g, '<ocid>'],
    [/emdemo/gi, '<env-prefix>'],
    [/octoatp_(low|medium|high)/g, '<atp-connection>'],
    [/octodemo\.cloud/g, 'example.com'],
    [/${OCIR_TENANCY}/g, '<tenancy-namespace>'],
    [/attack-851e80f8751b/g, '<demo-attack-id>'],
    [/octo-[a-z-]+-[a-f0-9]{6,12}-[a-z0-9]{5}/g, 'octo-pod-<id>'],
    [/\b(?!10\.|127\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|0\.0\.0\.0)([0-9]{1,3}\.){3}[0-9]{1,3}\b/g, '<ip>'],
  ];
  function scrubText(s) {
    let v = s;
    for (const [re, to] of REPLACEMENTS) v = v.replace(re, to);
    return v;
  }
  function walk(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const v = scrubText(node.nodeValue);
      if (v !== node.nodeValue) node.nodeValue = v;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      for (const attr of ['title','aria-label','placeholder','alt','value']) {
        if (node.hasAttribute(attr)) {
          node.setAttribute(attr, scrubText(node.getAttribute(attr)));
        }
      }
      const tag = node.tagName ? node.tagName.toLowerCase() : '';
      if (tag !== 'script' && tag !== 'style' && tag !== 'noscript') {
        for (const child of Array.from(node.childNodes)) walk(child);
      }
    }
  }
  walk(document.documentElement);
  const hideSelectors = ['[class*="tenancy"]', '[class*="user-info"]', '[class*="account-menu"]'];
  for (const sel of hideSelectors) {
    document.querySelectorAll(sel).forEach(el => {
      if (el.textContent && el.textContent.length < 120) el.style.visibility = 'hidden';
    });
  }
};
"""

TARGETS = [
    {"name": "apm-01-trace-explorer-result",
     "instruction": "Observability & Management → APM → Trace Explorer. Run a query showing >=1 trace."},
    {"name": "apm-02-flame-chart",
     "instruction": "Click a trace from the list → flame chart view visible."},
    {"name": "apm-03-span-attributes",
     "instruction": "Click a span in the flame chart → right-hand attributes panel open."},
    {"name": "apm-04-dependency-map",
     "instruction": "APM → Dependency Map → topology graph visible."},
    {"name": "apm-05-rum-overview",
     "instruction": "APM → RUM → Web Applications → click your Web App → RUM overview dashboard."},
    {"name": "apm-06-rum-session",
     "instruction": "RUM → drill into a single user session timeline."},
    {"name": "loganalytics-01-search",
     "instruction": "Logging Analytics → Log Explorer. Run a search with stats. Results visible."},
    {"name": "loganalytics-02-saved-search",
     "instruction": "Logging Analytics → Saved Searches list."},
    {"name": "loganalytics-03-dashboard",
     "instruction": "Open a Logging Analytics dashboard (e.g. attack-lab-command-center). Widgets loaded."},
    {"name": "loganalytics-04-detection-rules",
     "instruction": "Logging Analytics → Detection Rules list."},
    {"name": "loganalytics-05-parser",
     "instruction": "Logging Analytics → Parsers → click one of the project parsers (e.g. octo-shop-v2)."},
    {"name": "monitoring-01-metrics-explorer",
     "instruction": "Monitoring → Metric Explorer → plot a metric from octo_apm_demo namespace."},
    {"name": "monitoring-02-alarm",
     "instruction": "Monitoring → Alarms list."},
    {"name": "stackmonitoring-01-overview",
     "instruction": "Stack Monitoring → Hosts list."},
    {"name": "stackmonitoring-02-atp",
     "instruction": "Stack Monitoring → Autonomous Database → click the demo ATP."},
]


def wait_interactive(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        print()
        print("(no TTY — switch to sentinel-file mode: rerun with --sentinel)")
        sys.exit(2)


def wait_sentinel(prompt):
    print(prompt)
    print(f"  → create {SENTINEL} to continue (touch {SENTINEL})")
    print(f"  → create {SENTINEL}.skip to skip")
    print(f"  → create {SENTINEL}.quit to stop")
    if SENTINEL.exists(): SENTINEL.unlink()
    sk = SENTINEL.with_suffix(".skip");  qt = SENTINEL.with_suffix(".quit")
    if sk.exists(): sk.unlink()
    if qt.exists(): qt.unlink()
    while True:
        if SENTINEL.exists():
            SENTINEL.unlink()
            return ""
        if sk.exists():
            sk.unlink()
            return "skip"
        if qt.exists():
            qt.unlink()
            return "quit"
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sentinel", action="store_true",
                        help="Use sentinel files instead of stdin (for non-TTY shells)")
    args = parser.parse_args()
    wait = wait_sentinel if args.sentinel else wait_interactive

    print()
    print("=" * 72)
    print("OCI Console screenshot capture")
    print("=" * 72)
    print()
    print(f"Output directory: {OUT_DIR}")
    print(f"Targets: {len(TARGETS)}")
    if args.sentinel:
        print(f"Mode: sentinel-file (uses {SENTINEL})")
    else:
        print("Mode: interactive (needs a real TTY — run in Terminal.app)")
    print()

    wait("Press Enter to launch the browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport=VIEWPORT, ignore_https_errors=True)
        page = context.new_page()
        page.goto("https://cloud.oracle.com", wait_until="domcontentloaded", timeout=30000)

        print()
        print("Browser open. Log in to OCI Console.")
        wait("Once you see the OCI dashboard, continue...")

        for i, target in enumerate(TARGETS, 1):
            out_path = OUT_DIR / f"{target['name']}.png"
            print()
            print(f"[{i}/{len(TARGETS)}] {target['name']}")
            print(f"  → {target['instruction']}")
            resp = wait("  Action [Enter=capture / skip / quit]: ")
            if resp == "quit":
                print("  Stopping.")
                break
            if resp == "skip":
                print("  Skipped.")
                continue
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            try:
                page.evaluate(SCRUB_JS)
            except Exception as e:
                print(f"  WARN: scrub failed: {e}")
            time.sleep(0.5)
            try:
                page.screenshot(path=str(out_path), full_page=False)
                size_kb = out_path.stat().st_size // 1024
                print(f"  ✓ saved {out_path.name} ({size_kb} KB)")
            except Exception as e:
                print(f"  ✗ capture failed: {e}")

        print()
        print("Done. Browser closes in 5 seconds.")
        print(f"Screenshots: {OUT_DIR}")
        time.sleep(5)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
