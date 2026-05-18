# Contributing to OCTO APM Demo

Thanks for your interest in contributing to **OCTO APM Demo** — a unified observability reference platform that combines a drone-shop storefront, an enterprise CRM portal, full MELTS instrumentation, and a shared Oracle ATP backend. We welcome contributions from the community.

## A. Welcome & Scope

### What we welcome

- **New observability scenarios** — additional load profiles, failure simulations, latency injectors, or cross-service correlation demos.
- **Bug fixes** — both in application code (`shop/`, `crm/`) and in deployment substrates (`deploy/`).
- **Documentation improvements** — clearer explanations, missing diagrams, updated screenshots, fixes to typos.
- **Deployment substrate additions** — new ways to run the stack (additional Helm chart options, alternate clouds, local-stack variants).
- **New detection rules** — Log Analytics queries, dashboard widgets, or SOAR/auto-remediation playbooks.
- **Workshop labs** — new self-paced exercises under `site/workshop/`.
- **Test coverage** — additional unit, integration, or contract tests, especially around the signal-contract surface.

### What's out of scope

- Changes that hard-code tenancy-specific assumptions (tenancy OCIDs, namespace strings, compartment paths) into committed code.
- Breaking changes to the trace/log/metric correlation contract without an accompanying ADR explaining the rationale and migration path.
- New dependencies on private or paid services that lock out community contributors.
- Wholesale rewrites without a prior discussion issue.

## B. Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/) version 2.1. By participating, you agree to uphold its standards: be respectful, be welcoming, and assume good faith. Harassment of any kind is not tolerated.

If you experience or witness unacceptable behavior, please contact the maintainers via a private message on GitHub.

## C. Setup

Local development setup is documented in detail elsewhere. The short version:

1. **Fork** the repository on GitHub.
2. **Clone** your fork: `git clone git@github.com:<your-user>/octo-apm-demo.git`.
3. **Create a branch** using one of the following prefixes:
   - `feature/<short-name>` — new functionality
   - `fix/<short-name>` — bug fixes
   - `docs/<short-name>` — documentation-only changes
   - `chore/<short-name>` — tooling, CI, dependency bumps
4. **Install local dependencies** as described in the development guide (`DEVELOPMENT.md` if present, otherwise see the per-service `README.md` files in `shop/` and `crm/`).
5. **Run the local stack** following `deploy/local-stack/README.md`.

For prerequisites, environment variables, and first-run instructions, see also [docs/CONFIGURATION.md](docs/CONFIGURATION.md) and the root [README.md](README.md).

## D. Making a Change

Before opening a pull request, please follow these steps.

### 1. Open an issue first (for non-trivial work)

For anything larger than a typo fix or a small bug, **open an issue first** so we can discuss the approach. This avoids wasted effort and ensures alignment with the project direction.

### 2. Write tests before code

We practice test-driven development. Add tests that fail before your change, then write the minimum code needed to make them pass. The test suites under `tests/` (Python contract tests) and the per-service test directories must continue to pass.

### 3. Add structured logging with the standard fields

When you add new code paths that emit logs, use the project's structured-logging helpers in `shop/server/observability/` and `crm/server/observability/`. Every log line should include the standard correlation fields (trace_id, span_id, service.name, deployment.environment).

### 4. Add APM span attributes for new HTTP routes

New HTTP routes must be instrumented with OpenTelemetry. Add semantic span attributes for any business-meaningful values (order id, customer id, simulation id) so the route shows up correctly in the APM trace explorer.

### 5. Update affected docs

If your change affects user-facing behavior or architecture, update the relevant docs in the same PR:

- [README.md](README.md) — top-level project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) — system architecture, component boundaries
- [docs/CONFIGURATION.md](docs/CONFIGURATION.md) — environment variables, config knobs
- `site/getting-started/` — onboarding flow
- `site/workshop/` — workshop labs, if affected

### 6. Run the local validation gate before opening a PR

At minimum, run:

```bash
# Python tests (contract + architecture)
pytest tests/ -q

# Per-service unit tests
pytest shop/tests/ -q
pytest crm/tests/ -q

# Static analysis (same tools CI runs)
bandit -q -r shop/server crm/server -ll -iii
ruff check --select S shop/server crm/server
```

If any of these fail locally, CI will fail too.

## E. Pull Request Process

### One PR per feature or fix

Keep PRs focused. Mixing an unrelated cleanup into a feature PR makes review harder and increases the chance of revert if something goes wrong.

### PR title follows Conventional Commits

Use one of these prefixes in the PR title:

- `feat:` — new functionality
- `fix:` — bug fix
- `docs:` — documentation-only change
- `chore:` — tooling, CI, dependency bumps
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `perf:` — performance improvement
- `test:` — test-only change
- `ci:` — CI/CD change

Examples:

- `feat: add order-sync latency injector to shop service`
- `fix: correct trace context propagation between CRM and ATP`
- `docs: clarify Helm values for ingress configuration`

### PR description must include

- **What changed** — a short summary of the diff.
- **Why** — the motivation or linked issue.
- **How tested** — commands run, test output, or screenshots.
- **Screenshots** — required for any UI change (drone-shop frontend, CRM portal, observability dashboards).

### Required reviewers

At least **one maintainer** must approve before merge. Maintainers may request changes; please address feedback in new commits rather than force-pushing (we squash on merge).

### All CI checks must pass

The following CI workflows must pass before merge:

- `security-gates` — Bandit, pip-audit, Ruff security rules, Gitleaks secret scan
- `mkdocs-deploy` (build step) — documentation site builds without errors

## F. Coding Standards

Coding standards (formatting, linting, naming, file size limits) are documented in the development guide. Briefly:

- Python code is checked with **Ruff** and **Bandit**; secrets are scanned by **Gitleaks**.
- Files should stay under ~800 lines; functions under ~50 lines.
- Prefer immutable data and explicit error handling.
- Validate all user input at system boundaries.

See the development guide for the full set of rules and the relevant section on coding standards.

## G. Security Disclosure

**Do not open a public issue for security vulnerabilities.**

If you discover a security issue:

1. **Use GitHub's private vulnerability reporting** via the repository's *Security* tab → *Report a vulnerability*, or
2. Email the maintainers at the address listed in `SECURITY.md` (when published).

Please include:

- A description of the issue and its impact.
- Steps to reproduce.
- Suggested fix, if you have one.

We will acknowledge within a reasonable timeframe and coordinate disclosure with you.

## H. Public Documentation Guard

The published documentation site (everything under `site/**/*.md` and `docs/**/*.md`) is rendered to the public web via MkDocs and **must not** contain:

- Real OCI tenancy strings (tenancy OCIDs, compartment OCIDs, user OCIDs)
- Public IP addresses or live hostnames
- Internal slugs, team names, or environment-specific identifiers
- Secrets, API keys, tokens, wallet passwords, or DSNs with credentials

Use placeholders instead:

| Real value (DO NOT COMMIT) | Placeholder to use |
|----------------------------|--------------------|
| Production DNS name | `${DNS_DOMAIN}` |
| Compartment OCID | `<COMPARTMENT_OCID>` |
| Tenancy namespace | `<TENANCY_NAMESPACE>` |
| Tenancy OCID | `<TENANCY_OCID>` |
| User OCID | `<USER_OCID>` |
| Public IP | `<PUBLIC_IP>` |
| API key | `<API_KEY>` |

CI enforces this via `tests/test_documentation_architecture_closure.py`, which scans documentation for a forbidden-token list and fails the build if any are found.

## I. Releasing

Releases are coordinated by maintainers.

- Maintainers tag releases via **GitHub Releases** (semantic versioning).
- Container images are pushed to **OCIR** tagged with both a timestamp and `latest`.
- The MkDocs site auto-publishes on push to `main` via [.github/workflows/mkdocs-deploy.yml](.github/workflows/mkdocs-deploy.yml).
- Helm chart releases are published from `deploy/helm/octo-apm-demo/`.

Contributors do not need to do anything special to trigger a release — your merged PR will be included in the next tagged version.

## J. Getting Help

Stuck or have a question? Try these in order:

1. **Read the docs** — start with the root [README.md](README.md), then the [architecture overview](ARCHITECTURE.md), then the [workshop labs](site/workshop/).
2. **Search existing issues** — your question may already be answered.
3. **GitHub Discussions** — if enabled on the repository, use Discussions for open-ended questions.
4. **File an issue** with the `question` label.

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for the full text. By contributing, you agree that your contributions will be licensed under the same terms.

---

Thanks again for contributing — every bug report, doc fix, and feature PR makes this demo a better learning resource for the observability community.
