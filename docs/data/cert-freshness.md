# Certifications data freshness (DATA-06)

## Field spec

Every entry in `data/certifications.json` must carry:

| Field | Type | Meaning |
|---|---|---|
| `official_url` | string (URL) | The provider's canonical certification page. This is the link shown to users. |
| `exam_fee` | object or null | `{ "amount": 15000, "currency": "INR" }`. `null` when the provider doesn't publish a fee. Never guess. |
| `fee_verified_at` | string (YYYY-MM-DD) or null | Date the fee was last confirmed on the official page. `null` iff `exam_fee` is null. |
| `last_verified` | string (YYYY-MM-DD) | Date the whole entry (URL + fee + syllabus link) was last checked. |

## Freshness SLA

- `last_verified` older than **180 days** → entry flagged `stale` in CI
  (warning; dataset still builds).
- `fee_verified_at` older than **180 days** → fee shown with "verify on the
  provider's site" emphasis in the UI.
- Link-check: `scripts/check_links.py` runs **nightly** (CI cron) and opens
  an issue / fails the job when `official_url` returns 4xx/5xx twice in a row.

## UI rule

Always render: "**Verify on the provider's site**" with the `official_url`
link. Never present our cached fee as authoritative.
