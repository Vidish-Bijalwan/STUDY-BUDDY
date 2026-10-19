# Privacy-friendly metrics plan (OSS-11)

Measure what matters without surveillance. No cookies for tracking, no
fingerprinting, no per-user analytics on the hosted instance.

## What we track (aggregates only)

| Metric | Source | Why |
|---|---|---|
| Stars / forks / contributors per week | GitHub API | OSS health |
| WAU (weekly active users) | Plausible/Umami, cookie-less | adoption |
| Resumes analyzed (count only) | server counter | core-loop usage |
| Time-to-first-report | anonymized timing histogram | UX-02 goal |
| 7-day return rate | hashed-day cohorts, no identity | retention |
| Error rates per endpoint | server logs (no PII) | reliability |

## Tooling

- **Plausible** or **Umami**, self-hosted, cookie-less — no Google Analytics.
- **Self-hosted instances**: telemetry is **opt-in** (env flag, default off);
  when on, it sends only the aggregate counters above, never content.
- In-app feedback widget: thumbs up/down + free-text comment (explicit
  action = consent); comments are not linked to accounts in exports.

## What we never collect

Resume text, names, emails, or any file content leaves the user's session
only when the user explicitly exports/shares it. Analytics payloads are
reviewed in PRs like code.

## Public learning

A monthly "What we learned" post in Discussions: the numbers above, what
changed, what we're trying next. Transparency is the growth strategy.
