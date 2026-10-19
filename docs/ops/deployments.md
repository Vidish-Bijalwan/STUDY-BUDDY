# OPS-07: Gated, reversible deployments

## CI-gated deploys

- Render **auto-deploy must only fire after CI passes.** In the Render dashboard: service → Settings → Build & Deploy → set auto-deploy to "on commit" **and** verify the "Wait for CI to pass" / required-checks option is enabled so a red `ci.yml` blocks the deploy. (Dashboard step — do this once, then record the date here.)
- Required checks: lint (ruff), full test suite, security audit (`ci.yml` — do not weaken these gates to unblock a deploy).

## Staging

- **Staging service:** separate Render web service (`study-buddy-staging`) + a **Neon branch** as its database (Neon free includes branching — zero extra cost).
- Every release candidate deploys to staging first. Promote to production only after:
  1. `curl /readyz` → 200 on staging,
  2. `curl /version` SHA matches the release tag,
  3. smoke test: upload sample resume → readiness report renders,
  4. `scripts/check_memory.py` passes against staging.

## Release tags (OPS-10)

- Semantic versioning. Annotated tags: `git tag -a vX.Y.Z -m "..."`, pushed to GitHub.
- GitHub Release per tag with notes generated from `CHANGELOG.md`.
- Production deploys always reference a tag, never a bare branch head.

## Rollback procedure

**Fastest (Render dashboard, ~1 min):**
1. Render dashboard → service → Deploys → find the previous green deploy → **Rollback**.
2. `curl /version` on production — confirm the SHA matches the previous tag.
3. `curl /readyz` → 200.

**Via git (if dashboard is unreachable):**
```bash
git tag -a vX.Y.Z-rollback -m "rollback to vX.Y.(Z-1)"
git push origin <previous-tag>   # re-point deploy, or redeploy tag in Render
```

**Database rollback:** migrations are forward-only. If a deploy shipped a migration:
1. Do NOT roll the schema back by hand — write a down-migration or a fix-forward migration.
2. If data was corrupted, restore from the latest automated backup (see `docs/runbooks/dr.md`).

## Deploy checklist (short form — full list in docs/release-checklist.md)

- [ ] CI green on the release commit
- [ ] CHANGELOG.md updated, tag pushed, GitHub Release drafted
- [ ] Backup taken (`pg_dump`, OPS-02/DR)
- [ ] Staging verified (`/readyz`, `/version`, smoke test)
- [ ] Rollback target identified (previous tag + deploy id) *before* promoting
