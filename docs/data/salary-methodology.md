# Salary data methodology (DATA-02)

`data/salary_ranges.json` (144 entries, 12 roles, tiers × experience bands,
INR LPA) ships with an honest disclaimer but no documented methodology. This
doc is the methodology.

## Sources used

1. **Company-published campus offers** — offer letters / placement reports
   published by companies and college placement cells (primary for entry
   bands). Each entry records the company or cell as `source_note`.
2. **Government macro context** — PLFS (Periodic Labour Force Survey) and
   AISHE reports for sanity bounds only (they are not role-level).
3. **Verified user contributions** — accepted only with k-anonymity ≥ 20
   (no band is published from fewer than 20 independent reports) and only
   with consent; contributor identities are never stored.

What we do **not** do: scrape job boards or salary sites whose terms forbid
it. Ranges are built from public, licensed, or consented sources only.

## How ranges are derived

1. Collect data points per (role, tier, experience band).
2. Drop the top/bottom 5% (outlier trim), then take the interquartile range
   (P25–P75) as the published band.
3. Round to the nearest ₹0.5 LPA. **Ranges, never point estimates.**
4. Bands with < 20 points are marked `confidence: "low"` and shown with a
   "limited data" note; bands with ≥ 100 points are `confidence: "high"`.

## Tier definitions

| Tier | Meaning |
|------|---------|
| Tier 1 | Product companies / top consulting / high-paying startups (e.g. FAANG-equivalent, unicorns) |
| Tier 2 | Established IT services majors, mid-size product firms, funded startups |
| Tier 3 | Small services firms, early startups, non-metro employers |

Tiers describe **pay bands, not prestige** — stated in the UI next to every
range display.

## Experience bands

Fresher (0–1 yr), 1–3 yrs, 3–5 yrs, 5–8 yrs, 8+ yrs. CTC in INR LPA, includes
variable pay where reported as such.

## Limitations

- India-only; metro vs non-metro is not yet split (planned).
- Campus offers skew toward Tier 1/2 colleges; off-campus reality may be lower.
- Ranges lag the market by ~6 months (refresh SLA: 180 days — see DATA-01).
- Equity/ESOP value is excluded (too variable to compare honestly).

## Confidence levels

- `high`: ≥ 100 points, multi-source, verified within 180 days.
- `medium`: 20–99 points or single strong source.
- `low`: < 20 points or older than 180 days — shown with a warning, never
  used as the headline number.
