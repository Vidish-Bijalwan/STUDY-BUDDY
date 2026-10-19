# Notifications: sending checklist (UX-10)

Notifications are **opt-in only** (`studybuddy/ux_notify.py`). Per-category
preferences, verified-address requirement for marketing mail, and signed
one-click unsubscribe tokens are implemented. This doc covers the operational
side: the sending domain and provider setup.

## Provider

Use a reputable transactional provider (e.g. Amazon SES, Postmark, Resend,
Mailgun). No provider keys are stored in this repo. The `EmailProviderStub`
class is the integration seam — implement `.send()` on it with the chosen
provider's SDK.

## DNS checklist (run before the first send)

- [ ] **SPF**: `TXT` record on the sending domain, e.g.
      `v=spf1 include:<provider>.com ~all` (one SPF record per domain —
      merge includes if several services send).
- [ ] **DKIM**: publish the provider's DKIM `TXT` records (selector-based);
      verify "DKIM: pass" on a test message in Gmail.
- [ ] **DMARC**: start at `p=none` with `rua=` reporting, move to
      `p=quarantine` then `p=reject` after 2–4 clean weeks:
      `v=DMARC1; p=quarantine; rua=mailto:dmarc@example.com; fo=1`.
- [ ] **Reverse DNS / dedicated IP** (if self-sending): PTR record matches
      the HELO hostname.
- [ ] **List-Unsubscribe** headers (`mailto:` + HTTPS one-click) on every
      bulk/template send — required by Gmail/Yahoo bulk-sender rules.
- [ ] **Bounce/complaint handling**: wire provider webhooks; suppress hard
      bounces and spam complaints automatically.

## Sending rules (enforced in code)

1. Never send to an address that hasn't opted in to that category.
2. Marketing category (`announcements`) requires a **verified** address and
   explicit consent — enforced in `NotificationPrefs.set()`.
3. Every message carries a signed unsubscribe URL (no login required).
4. No PII in subjects; no resume text in notification bodies.
5. Rate-limit per recipient (e.g. max 1 streak nudge/day).
