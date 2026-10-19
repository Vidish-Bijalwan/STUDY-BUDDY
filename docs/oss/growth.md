# Growth loops (OSS-09)

Growth without dark patterns: no referral spam, no fake urgency, no
growth-hacked metrics.

## Privacy-safe score cards

`studybuddy/oss_share.py` — `build_score_card(report, opt_in=True)`:

- Contains **only** pillar name/score/max + project name/link.
- **Never** resume text, names, contact fields, or evidence spans.
- Generation raises `PermissionError` unless the user explicitly opts in.
- `assert_no_pii(card, report)` is a test helper CI can run to prove no
  finding text leaks into the card.

Render target: a shareable image (server-side render of the card payload)
with "Scored with STUDY-BUDDY" and the project link.

## "Scored with STUDY-BUDDY" badge

An embeddable badge for portfolios:

```html
<a href="https://studybuddy.example">
  <img src="https://studybuddy.example/badge.svg" alt="Scored with STUDY-BUDDY">
</a>
```

Static SVG, no tracking pixels.

## Campus ambassador kit (outline)

- `docs/oss/ambassador/slides.md` — 10-slide workshop deck outline
  (problem, live demo of the Core Loop, honesty story).
- `docs/oss/ambassador/poster.md` — printable poster copy (A3).
- `docs/oss/ambassador/workshop-script.md` — 60-minute workshop script
  (setup, guided resume analysis, Q&A).
- `docs/oss/ambassador/sample-data.md` — synthetic sample resumes for
  demos (never real user data).

## Placement-cell widget (outline)

An embeddable, self-host-friendly widget for college placement pages:

- `<iframe src="https://<instance>/embed/readiness" ...>` — the try-it-now
  demo (PROD-03) in a sandboxed frame.
- Instance admin opts in explicitly; widget sends no analytics back.
- Documented CSP requirements for the embedding page.
