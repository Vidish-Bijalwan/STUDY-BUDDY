# OPS-12: SLOs, error budget, and disaster recovery

## SLOs — honest to the tier

| Stage | Availability SLO | Latency SLO (non-LLM) | Notes |
|---|---|---|---|
| **A (free)** | *No SLO.* Best effort; sleeps after 15 min idle; ~1 min cold starts. | p95 < 2 s when warm | Do not promise uptime you don't pay for. |
| **B (paid)** | **99% monthly** (~7 h downtime budget) | p95 < 500 ms | Measured on `/readyz` + key pages, excluding LLM calls. |
| **C (growth)** | 99.5% monthly | p95 < 500 ms | Revisit when multi-instance. |

LLM-backed features are excluded from latency SLOs (provider variance); they
get their own fallback SLO: **no-LLM mode always available** (degraded but
functional — the privacy differentiator doubles as the reliability story).

## Error budget policy

- Budget = 100% − SLO (Stage B: 1% monthly ≈ 7 h 18 m).
- **Budget > 50% remaining:** normal feature velocity.
- **Budget < 50%:** feature freeze on risky changes; reliability work first.
- **Budget exhausted:** full deploy freeze except S1/S2 fixes until the next
  monthly window. Postmortem required (`docs/runbooks/postmortems/`).
- Track with the uptime monitor's monthly report; review on the 1st.

## DR runbook

**RPO:** ≤ 24 h (daily automated `pg_dump`; roadmap: 8 weekly + 3 monthly
retention, encrypted, off-Render storage — OPS-02 item 5).
**RTO:** ≤ 4 h (redeploy + restore + verify).

### 1. Restore the database

```bash
# newest backup from off-site storage -> local file
pg_restore --no-owner --no-acl --clean -d "$NEW_DATABASE_URL" backup.dump
# verify
psql "$NEW_DATABASE_URL" -c "SELECT count(*) FROM \"user\";"
# alembic state must match code
flask db stamp head   # only if the dump predates the migration tooling
```

Point `DATABASE_URL` at the restored DB (Render dashboard → Environment →
`DATABASE_URL`), keep the old DB for 7 days.

### 2. Redeploy the app

```bash
git tag -a vX.Y.Z -m "DR redeploy"   # tag the known-good commit
git push origin vX.Y.Z               # Render redeploys from the tag
```
Verify: `curl /readyz` → 200, `curl /version` SHA matches tag, smoke-test the
core loop (upload sample resume → readiness report).

### 3. Rotate secrets

After any suspected compromise (or post-restore hygiene):

1. `SECRET_KEY` — regenerate in Render dashboard (invalidates all sessions;
   users re-login).
2. `GEMINI_API_KEY` / provider keys — rotate at the provider console, update
   Render env, redeploy.
3. `FERNET_KEY` — generate a new key, prepend to `FERNET_KEYS` (newest first),
   run the rotation sweep over encrypted columns (`FieldCipher.rotate`),
   then retire the old key.
4. OAuth client secrets — rotate in Google Cloud Console.

### 4. Restore drill

Quarterly, on staging: restore the latest backup to a Neon branch, run the
smoke test, record RPO/RTO achieved in `docs/runbooks/postmortems/`.
A backup never tested is not a backup.
