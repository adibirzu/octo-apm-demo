FROM mcr.microsoft.com/playwright:v1.55.1-jammy

# Non-root user. Playwright image ships `pwuser` (uid 1000) — reuse it.
# Any ownership fixups happen before USER so install works.

WORKDIR /app

COPY package.json tsconfig.json playwright.config.ts ./
COPY src ./src
COPY journeys ./journeys

RUN npm install --omit=dev && \
    mkdir -p /tmp/octo-browser-runner && \
    chown -R pwuser:pwuser /app /tmp/octo-browser-runner

ENV OCTO_BROWSER_HEADLESS=true \
    OCTO_BROWSER_ARTIFACTS_DIR=/tmp/octo-browser-runner \
    NODE_ENV=production

USER pwuser

VOLUME ["/tmp/octo-browser-runner"]

# Default: run one catalog-to-checkout iteration. Kubernetes Jobs
# override this with the desired journey name as argv.
CMD ["npx", "tsx", "src/run-journey.ts", "catalog-to-checkout"]
