# OPS-03: Hosting plan by stage

| Stage | Web | Database | Notes |
|---|---|---|---|
| **A — now to launch** | Render **free** web (512 MB RAM, sleeps after 15 min idle, cold start ~1 min) | Neon **free** (0.5 GB, no expiry, scale-to-zero after 5 min) | Landing/marketing page on GitHub Pages or Cloudflare Pages so first impression is instant; app on a subdomain. Cold-start splash page: `static/cold-start.html` (OPS-13). |
| **B — first real users** | Render **Starter** (~$7/mo, always-on, 512 MB→2 GB) or Fly.io / Koyeb equivalent | Neon (scale plan only if 0.5 GB fills) | Redis (Render Key Value or Upstash free) for rate limits + job queue; Sentry error tracking; uptime monitor with alerts. |
| **C — growth** | Docker on any container host; horizontal scaling; CDN (Cloudflare free) in front of static assets | Managed Postgres + read replica if needed | Dedicated worker service for background jobs (PDF indexing, embeddings); object storage for files (OPS-08). |

## Honest free-tier limits (Stage A)

- **Render free web sleeps after 15 min of no traffic.** First request after sleep takes ~30–60 s. This is a Render platform behavior, not a bug.
- **Render free Postgres expires 30 days after creation** (14-day grace before deletion) — see OPS-02: do not ship Stage A on Render Postgres; use Neon free (no expiry).
- **512 MB RAM cap** on Render free: one gthread worker only (`gunicorn.conf.py`, OPS-09); CI memory budget caps boot+workload at 400 MB (PERF-09).
- **Ephemeral filesystem**: uploads vanish on restart/redeploy — never persist originals (OPS-08, PRIV-01).
- **Do NOT rely on third-party "keep-alive pings"** to defeat sleeping — not officially supported and can violate ToS. If reliability matters, move to Stage B.
- Free bandwidth caps exist on every platform; monitor and move up a stage before hitting them (OPS-11).

## Decision log

- Stage A DB: **Neon free** over Supabase free (Supabase pauses after 1 week of inactivity; Neon resumes sub-second) and over Render free Postgres (expires). Recorded 2026-10-19.
- Static landing: GitHub Pages (already live per v1.0.0 docs site) — zero marginal cost.
