# Incident response runbook (OPS-06)

## Severity levels

| Sev | Definition | Examples | Response |
|---|---|---|---|
| **S1 — Critical** | App down or data at risk; core loop broken for all users | 5xx on `/`, DB unreachable, auth bypass, data leak | Page immediately (maintainer phone/DM). Mitigate first, fix second. Status update within 30 min. |
| **S2 — Major** | Major feature broken for many users | Resume upload failing, LLM gateway down with no fallback, /readyz 503 for >10 min | Respond within 2 h. Workaround or rollback. |
| **S3 — Minor** | Degraded or single-feature issue | One tool page erroring, slow cold starts, stale opportunities feed | Fix in next deploy window. Track as GitHub issue. |
| **S4 — Cosmetic** | UI/text issues, no functional impact | Typo, misaligned card | Backlog. |

## Who is paged

This is currently a solo-maintainer project: **Vivek (maintainer) is the single on-call**. Uptime monitor (e.g. UptimeRobot free / Better Stack) alerts via email + push on `/readyz` non-200 for 2 consecutive checks. No escalation chain exists yet — define one before Stage B.

## Procedure

1. **Acknowledge** — reply to the alert; open a GitHub issue labeled `incident` + sev.
2. **Mitigate** — fastest path back to serving traffic: rollback to previous Render deploy (OPS-07) or previous release tag; disable the broken feature flag/env var. Do not debug in production.
3. **Communicate** — post using the template below (status page / pinned issue).
4. **Fix forward** — root-cause in a branch, CI green, deploy via staging (OPS-07).
5. **Postmortem** — within 48 h for S1/S2: timeline, root cause, action items. File under `docs/runbooks/postmortems/YYYY-MM-DD-<slug>.md`.

## Communication template

```markdown
**Status: Investigating / Mitigating / Resolved**
**Severity:** S1/S2/S3
**Started:** 2026-10-19 21:30 IST
**Impact:** <who is affected, what is broken>
**Workaround:** <what users can do meanwhile, or "none yet">
**Next update:** <time, max 60 min for S1/S2>

Updates:
- 21:35 IST — <what we know / what we did>
```

## Observability in place

- **Errors:** Sentry via `studybuddy/sentry_init.py` — opt-in with `SENTRY_DSN`; `before_send` scrubs PII/secrets (emails, tokens, request bodies, cookies, resume text). `send_default_pii=False`.
- **Logs:** JSON access logs with request IDs in production (`studybuddy/observability.py`, ARC-08). Never log payloads.
- **Metrics (minimum viable):** request rate, error rate, p95 latency from Render logs + uptime monitor; LLM fallback rate and quota hits from app logs. Full metrics dashboard is a Stage B item.
- **Status page:** Stage B item — for Stage A, a pinned GitHub issue serves as the status channel.
