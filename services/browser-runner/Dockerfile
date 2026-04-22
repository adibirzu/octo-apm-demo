FROM mcr.microsoft.com/playwright:v1.55.1-jammy

WORKDIR /app

COPY package.json tsconfig.json playwright.config.ts ./
COPY src ./src
COPY journeys ./journeys

RUN npm install --omit=dev

ENV OCTO_BROWSER_HEADLESS=true \
    OCTO_BROWSER_ARTIFACTS_DIR=/tmp/octo-browser-runner \
    NODE_ENV=production

VOLUME ["/tmp/octo-browser-runner"]

# Default: run one catalog-to-checkout iteration. Kubernetes Jobs
# override this with the desired journey name as argv.
CMD ["npx", "tsx", "src/run-journey.ts", "catalog-to-checkout"]
