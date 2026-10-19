# LEG-05: Name and trademark check — "Study Buddy"

## The risk

"Study Buddy" is a **generic, widely-used name**. A quick mental inventory:
multiple ed-tech products, tutoring services, browser extensions, and mobile
apps already use "Study Buddy" / "StudyBuddy". Consequences:

- **Trademark:** near-impossible to register or defend; high likelihood of an
  existing mark in ed-tech classes (USPTO class 41, India class 41).
- **Search/discoverability:** the name is un-ownable on Google — SEO will
  always fight incumbents.
- **App stores / registries:** likely squatted or colliding.
- **Domain:** studybuddy.com and obvious variants are taken (verify live).

**Recommendation: pick a distinctive name before investing in branding**
(logo, landing copy, social handles). The roadmap ties this to OSS-01. A
distinctive name is cheaper to change *now* than after launch.

## Search checklist (run before finalizing any name)

- [ ] **USPTO** TESS / trademarksearch.uspto.gov — classes 9 (software) and 41 (education)
- [ ] **India:** ipindiaservices.gov.in public trademark search — class 41 (and 9)
- [ ] **WIPO** Global Brand Database (international coverage)
- [ ] **Domains:** exact-match `.com` + `.in` + `.ai` (use a registrar search, don't rely on memory)
- [ ] **GitHub:** org and repo name availability
- [ ] **PyPI:** `pip index` / pypi.org search
- [ ] **npm:** npmjs.com search
- [ ] **Docker Hub:** hub.docker.com search
- [ ] **App stores:** Google Play + Apple App Store search
- [ ] **Social handles:** X/Twitter, Instagram, LinkedIn, YouTube
- [ ] **Google:** `"Name" + app/software` — check for confusingly similar products

## Naming guidance

- Prefer **coined or suggestive** over descriptive: "Study Buddy" describes;
  something like "Sunday" (the org's existing brand) + a distinctive product
  word is defensible.
- Check OSS-01 for the project's naming decision record; record the final pick
  and the date each checklist item was cleared.
- **Get a qualified legal review before public launch** (per LEG-03) — this
  checklist is diligence, not legal advice.

## Status (2026-10-19)

Checklist **not yet run** — flagged as a pre-branding blocker. The product
ships as "Study Buddy" in v1.0.0 UI copy; renaming later is a find-replace
plus asset updates, but trademark exposure grows with every public release.
