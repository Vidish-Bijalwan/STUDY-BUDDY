# Job-source ToS verification checklist (ENG-11)

Every live job feed used by StudyBuddy must come from an **official API with
compatible terms**. Scraping job boards whose terms forbid it is not allowed —
there is deliberately no scraping code path in `studybuddy/eng_jobs.py`.

## Verification procedure (repeat per source)

For each candidate source, record the outcome in the table below before any
integration work:

1. **Official API confirmed** — link to the provider's developer docs (not a
   third-party scraper).
2. **Terms of service read** — quote or link the section that permits
   programmatic access / redistribution of listings.
3. **Rate limits noted** — requests/day, attribution requirements, caching rules.
4. **Data licensing** — can we store and display title/company/location/link?
   For how long? Is re-verification required (link-check cadence)?
5. **Geography fit** — does the source cover India / the user's target regions?
6. **Sign-off** — name + date of the person who verified.

## Sources under evaluation

| Source | API docs | ToS permits programmatic use? | Rate limits | Attribution required | Verified by / date |
|---|---|---|---|---|---|
| Adzuna (incl. Adzuna India) | https://developer.adzuna.com/ | _pending_ | _pending_ | _pending_ | — |
| Jooble | https://jooble.org/api/about | _pending_ | _pending_ | _pending_ | — |
| RemoteOK | https://remoteok.com/api | _pending_ | _pending_ | _pending_ | — |

## Explicitly out of scope (do not scrape)

- Major Indian job boards that prohibit scraping in their terms (e.g. Naukri,
  LinkedIn job listings). If a source's ToS is ambiguous, treat it as
  forbidden until legal/compliance review says otherwise.
- Any site behind a login wall or CAPTCHA — automating around those is a
  terms violation and a security risk.

## Notes

- Adapter stubs live in `studybuddy/eng_jobs.py` (`JobSourceAdapter`,
  `AdzunaAdapter`, `JoobleAdapter`, `RemoteOKAdapter`). Each raises
  `NotImplementedError` until an API credential is configured **and**
  `tos_verified` is set after this checklist is signed off.
- The paste-a-JD flow (`paste_jd_flow`) is the recommended primary path: it
  carries zero third-party ToS risk and works offline.
- Every card must carry `source` and `last_verified`; cards older than
  `MAX_CARD_AGE_DAYS` (30) are expired automatically (see `is_expired`).
