import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const root = path.resolve(new URL("../..", import.meta.url).pathname);
const require = createRequire(import.meta.url);

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  ({ chromium } = require(path.join(root, "services/browser-runner/node_modules/playwright")));
}

const outDir = path.join(root, "site/assets/demo/private-oci-console");
const cdpUrl = process.env.OCI_CONSOLE_CDP_URL || "http://127.0.0.1:9223";
const screenshotName = process.argv[2] || process.env.OCI_CONSOLE_SCREENSHOT_NAME || "oci-console-current";
const targetUrl = process.env.OCI_CONSOLE_TARGET_URL || "";
const redactTerms = (process.env.OCI_CONSOLE_REDACT_TERMS || "")
  .split(",")
  .map((term) => term.trim())
  .filter(Boolean);

function safeName(value) {
  return value.replace(/[^a-z0-9_.-]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase();
}

async function redactFrame(frame) {
  await frame.evaluate((terms) => {
    const patterns = [
      /ocid1\.[a-z0-9_.-]+/gi,
      /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,
      /[A-Z0-9._%+-]+@[A-Z0-9.-]+/gi,
      /[A-Z0-9._%+-]+@ORACLE(?:\.[A-Z0-9.-]*)?/gi,
    ];
    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const redactText = (text) => {
      let next = text;
      for (const pattern of patterns) {
        next = next.replace(pattern, "redacted");
      }
      for (const term of terms) {
        next = next.replace(new RegExp(escapeRegExp(term), "gi"), "redacted");
      }
      return next;
    };

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
      textNodes.push(walker.currentNode);
    }
    for (const node of textNodes) {
      const original = node.nodeValue || "";
      const redacted = redactText(original);
      if (redacted !== original) node.nodeValue = redacted;
    }

    for (const element of Array.from(document.querySelectorAll("[title], [aria-label], [href], [value], [placeholder]"))) {
      for (const attr of ["title", "aria-label", "href", "value", "placeholder"]) {
        const value = element.getAttribute(attr);
        if (!value) continue;
        const redacted = redactText(value);
        if (redacted !== value) element.setAttribute(attr, redacted);
      }
    }

    for (const element of Array.from(document.querySelectorAll("input, textarea, option"))) {
      const original = "value" in element ? element.value : element.textContent || "";
      const redacted = redactText(original);
      if (redacted !== original) {
        if ("value" in element) element.value = redacted;
        else element.textContent = redacted;
      }
    }

    for (const element of Array.from(document.querySelectorAll("*"))) {
      const text = element.textContent || "";
      if (!text.includes("@")) continue;
      if (element.children.length > 0 && text.length > 80) continue;
      element.textContent = "redacted";
    }

    const headerSelectors = [
      "header",
      "[data-test-id='console-header']",
      "[data-testid='console-header']",
      ".console-header",
      ".oui-navbar",
    ];
    for (const selector of headerSelectors) {
      for (const element of Array.from(document.querySelectorAll(selector))) {
        element.style.filter = "blur(10px)";
      }
    }
  }, redactTerms).catch(() => {});
}

async function redactPage(page) {
  for (const frame of page.frames()) {
    await redactFrame(frame);
  }
}

async function main() {
  await fs.mkdir(outDir, { recursive: true });
  const browser = await chromium.connectOverCDP(cdpUrl);
  try {
    const pages = browser.contexts().flatMap((context) => context.pages());
    const page = pages.find((candidate) => candidate.url().includes("cloud.oracle.com")) || pages[0];
    if (!page) {
      throw new Error("No browser page is available through the OCI Console CDP session.");
    }

    if (targetUrl) {
      await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    }
    await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
    await redactPage(page);

    const output = path.join(outDir, `${safeName(screenshotName)}.png`);
    await page.screenshot({
      path: output,
      fullPage: false,
      animations: "disabled",
    });
    console.log(`wrote ${path.relative(root, output)}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
