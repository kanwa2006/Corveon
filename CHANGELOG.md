# Changelog

All notable changes to Corveon are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Roadmap phases that map to future releases are tracked in [docs/ROADMAP.md](docs/ROADMAP.md).

## [Unreleased]

_Nothing yet — implementation begins at Roadmap Week 1 (auth + chat CRUD with per-chat isolation)._

## [0.0.0] — 2026-07-07

Engineering foundation. No application code; this release establishes the structure, standards,
documentation, and CI on which all features are built.

### Added
- Repository structure: `backend/`, `frontend/`, `infra/`, `data/`, `docs/`, `.github/`
  (per [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §9).
- Engineering contract [`CLAUDE.md`](CLAUDE.md) and the full documentation set under `docs/`
  (ARCHITECTURE, DEVELOPER, SETUP, API, ENVIRONMENT, DEPLOYMENT, DEBUGGING, SECURITY,
  CONTRIBUTING, ROADMAP).
- Eleven Architecture Decision Records under [docs/adr/](docs/adr/) capturing every resolved
  decision (pgvector, forward-only migrations, custom orchestrator, DDInter, dual renal equations,
  provider-agnostic registry, backend-served SSE, embedding-model versioning, the name, the
  license, and ARQ).
- Backend packaging and tooling standards (`backend/pyproject.toml`: ruff, mypy-strict, pytest);
  frontend packaging (`frontend/package.json`, `tsconfig.json`, Prettier).
- Continuous integration ([.github/workflows/ci.yml](.github/workflows/ci.yml)) with backend and
  frontend quality gates; the frontend gates self-activate once the Next app scaffold lands.
- Local development infrastructure: `infra/docker-compose.yml`, multi-stage
  `infra/docker/backend.Dockerfile`, `Makefile`, and a fully documented `.env.example`.
- Community health files: `CODE_OF_CONDUCT.md`, `CONTRIBUTING`, `SECURITY`, issue templates,
  `CODEOWNERS`, and Dependabot configuration.
- `Apache-2.0` license and `NOTICE`.

[Unreleased]: https://github.com/kanwa2006/Corveon/compare/v0.0.0...HEAD
[0.0.0]: https://github.com/kanwa2006/Corveon/releases/tag/v0.0.0
