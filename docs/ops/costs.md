# OPS-11: Cost expectations and alert thresholds

All figures USD unless noted; LLM costs assume Gemini paid tier per D-4.

## Monthly cost per stage

| Stage | Web | DB | Extras | **Total** |
|---|---|---|---|---|
| **A (now–launch)** | Render free $0 | Neon free $0 | Cloudflare free $0, UptimeRobot free $0 | **$0** |
| **B (first users)** | Render Starter ~$7 | Neon free $0 (paid only if >0.5 GB) | Upstash/Render KV free→~$5, Sentry free $0 | **~$7–12** |
| **C (growth)** | 2× containers ~$14–25 | Neon scale ~$19+ or managed PG | R2 ~$0–5, Sentry team ~$26 | **~$60–100+** |

LLM spend is separate and usage-driven: budget per 1k resume analyses and set
the provider-side cap first (LLM-03). No-LLM mode (`LLM_MODE=off`) costs $0.

## Alert thresholds (set these on day one of each stage)

| Signal | Warning | Critical | Action |
|---|---|---|---|
| Neon storage | **80% of 0.5 GB** (400 MB) | 95% | prune/retention job (PRIV-01); plan upgrade |
| LLM spend (daily) | 70% of daily cap | 100% | auto-fallback to no-LLM mode; page maintainer |
| Render bandwidth | 70% of plan | 95% | CDN in front of static (PERF-03); upgrade |
| Error rate (5xx) | >1% over 15 min | >5% | incident response (S2/S1) |
| p95 latency (non-LLM) | >500 ms | >2 s | profile; scale threads/workers |
| Uptime (Stage B SLO) | <99.9% weekly | <99% monthly | error-budget freeze (see dr.md) |

## Notes

- Stage A has no paid bill to alert on — the alerts that matter are the
  **quota** ones (DB expiry, storage, bandwidth) because the failure mode is
  deletion/suspension, not a charge.
- Review this file quarterly or at every stage transition.
