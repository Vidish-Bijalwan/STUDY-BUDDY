# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0/).

## [1.0.0] - 2026-10-19

First stable release — Phases 0–4 of the world-class roadmap complete:
security hardening, foundation (CI/migrations/observability), trust & quality,
differentiation, and launch readiness.

### Added
- Privacy-first AI: No-LLM mode (`LLM_MODE=off`), BYOK (Fernet-encrypted keys,
  never logged), local mode via `LLM_BASE_URL` (Ollama), consent UX before
  first AI use, self-service data export/delete (GDPR/DPDP).
- Resume Readiness scoring (evidence-backed, not fake "ATS scores") with
  gold-set benchmarks.
- RAG evaluation harness: Recall@k, MRR, citation validity, abstention accuracy.
- Prompt-injection defense: hostile instructions in documents are sanitized.
- Security: CSP with per-request nonces, security headers, rate limiting,
  age gating on registration.
- Accessibility: skip links, focus states, reduced-motion, WCAG 2.2 AA target.
- Foundation: hash-pinned dependencies (`--require-hashes`), Alembic
  migrations, structured JSON logging with request IDs.
- Observability endpoints: `/healthz`, `/readyz`, `/version`.
- GitHub Actions CI: ruff lint, full test suite, Bandit security audit, mypy.
- Ops docs (Waves 5–6): hosting plan, containerization, incident-response and
  DR runbooks, deployment gating, memory discipline (`gunicorn.conf.py`),
  cost expectations, SLOs, Postgres pooling guide, cold-start splash page.
- Field-level encryption helpers (`studybuddy/field_encryption.py`, PRIV-04)
  and Sentry init with PII scrubbing (`studybuddy/sentry_init.py`, OPS-06).
- CI memory budget: app boot + core workloads must stay under 400 MB RSS
  (`scripts/check_memory.py`, PERF-09).
- Community: 20 good-first-issues, `FUNDING.yml`, social preview,
  branch-protection policy, Code of Conduct.

### Changed
- `Query.get()` → `db.session.get()` across the codebase (SQLAlchemy 2.0).
- Test suite runs with `-W error::DeprecationWarning`.
- Test passwords comply with the SEC-09 password policy.

### Fixed
- Prompt-injection vectors in document-grounded features.
- `pip install --require-hashes` reproducibility (locked requirements).
- Migration chain integrity (`flask db stamp head` procedure documented).

### Security
- See `SECURITY.md`. Report vulnerabilities privately per the policy there.

[1.0.0]: https://github.com/Vivek492005/AI-Career-Research-Assistant-Resume-Analysis-Job-Recommendation-Research-Paper-Intelligence-Platform/releases/tag/v1.0.0
