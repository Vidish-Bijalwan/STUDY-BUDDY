# Browser extension spec: JD capture (PROD-11)

Status: **spec only, no code**. A privacy review must pass before any
implementation.

## Purpose

An optional extension that sends the **visible job description** to the
user's STUDY-BUDDY instance (local or hosted) for JD matching — **only on
explicit click** of the extension button. No background scraping, no
always-on content scripts.

## Permissions (minimum viable)

- `activeTab` — read the current tab's DOM only when the user clicks.
- `storage` — remember the instance URL and API key locally.
- Host permission limited to the configured instance origin (user-set).
- **No** `<all_urls>`, **no** background page polling, **no** history/bookmarks.

## Privacy review gates (must pass before build)

1. Data minimization: only the user-selected JD text is sent; never the
   full page DOM, never credentials, never other tabs.
2. The extension **never** sends resume text anywhere; matching happens on
   the instance the user already trusts.
3. API key stored in `chrome.storage.local` (not synced), shown once on
   creation, revocable from the instance.
4. Content Security Policy: no remote code, no analytics SDKs in the
   extension bundle.
5. Permissions justification published in the repo (this doc) and in the
   store listing.
6. Self-host friendly: default instance URL points at `http://localhost:5000`
   so users can keep everything on their own machine.

## UX

- Click extension icon → "Send this job description to STUDY-BUDDY" →
  confirmation with character count → match report opens in a new tab.
- Clear state when the page has no detectable JD text ("No job description
  found on this page").
