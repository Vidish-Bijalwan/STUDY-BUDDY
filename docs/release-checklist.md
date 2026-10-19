# Release checklist (OPS-10)

Run through this list for every release. Tag format: `vX.Y.Z` (annotated).

## 1. Pre-freeze

- [ ] Roadmap items for the milestone are done and merged to `main`.
- [ ] `CHANGELOG.md` updated under `[Unreleased]` → new version section with date.
- [ ] Migration review: `flask db migrate` output inspected; upgrade + downgrade
      tested on a scratch DB; `flask db stamp head` procedure still valid (ARC-03).

## 2. Quality gates

- [ ] CI fully green on the release commit: ruff, pytest
      (`-W error::DeprecationWarning`), Bandit, mypy.
- [ ] `scripts/check_memory.py` passes (peak RSS ≤ 400 MB, PERF-09).
- [ ] Query budgets pass (`tests/test_ws6_ops.py` — PERF-02).
- [ ] Manual smoke on a local build: register → upload resume → readiness
      report → one AI feature with consent → delete/export data.

## 3. Backup & safety

- [ ] Production `pg_dump` taken and stored off-Render (OPS-02/DR runbook).
- [ ] Rollback target identified: previous tag + previous green Render deploy id
      (write them here before promoting).

## 4. Staging

- [ ] Release candidate deployed to the staging service (Neon branch DB).
- [ ] `curl /readyz` → 200; `curl /version` SHA matches the candidate commit.
- [ ] Smoke test passes on staging.

## 5. Tag & publish

- [ ] `git tag -a vX.Y.Z -m "Release vX.Y.Z"` and `git push origin vX.Y.Z`.
- [ ] GitHub Release created from the tag; notes pasted from `CHANGELOG.md`.
- [ ] Production deploy promoted (CI-gated auto-deploy or manual promote).

## 6. Post-deploy verification

- [ ] `curl /version` on production — SHA matches the tag.
- [ ] `curl /readyz` → 200.
- [ ] Uptime monitor shows no new alerts for 30 min.
- [ ] Sentry shows no new error groups (if enabled).
- [ ] Announce per the launch plan (launch-posts-draft.md).

## 7. If anything fails

Follow `docs/runbooks/incident-response.md`; rollback per
`docs/ops/deployments.md` — the rollback target from step 3 is the plan.
