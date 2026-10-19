# STUDY-BUDDY Governance (OSS-12)

## Decision process

- **Day-to-day**: maintainers decide; lazy consensus on PRs (silence after
  72h with a review request = consent for non-breaking changes).
- **Breaking / strategic** (API changes, license, governance itself): an
  issue labelled `decision` is open for at least 7 days; decision recorded
  in the issue and in `docs/decisions/ADR-*.md`.
- **Veto**: the project lead (Vivek Bartwal) may veto; vetoes are explained
  in writing in the decision issue.

## Maintainers

| Role | Who | Scope |
|---|---|---|
| Project lead | Vivek Bartwal | final decisions, releases, secrets |
| Maintainers | (TBD — see "becoming a maintainer") | merge rights, triage |

## Becoming a maintainer

Sustained, quality contributions over ~3 months (code or data), good
citizenship in reviews, and a nomination by an existing maintainer
(seconded by one more). No corporate affiliation required.

## Bus factor plan

- Runbooks live in `docs/` (deploy, backup, incident) — not in anyone's head.
- Secrets: handover process via the project's password manager shared
  vault; no secrets in chat/email. The lead documents vault location with
  the co-maintainer offline.
- Target: **at least two people** hold deploy access and know the recovery
  steps at all times.

## Release cadence

- Monthly minor releases; patch releases as needed for security.
- Every release: changelog, benchmark numbers refreshed, `CITATION.cff`
  version bumped, Zenodo DOI minted (OSS-06).

## Money

- Optional: GitHub Sponsors / Open Collective for infrastructure costs.
- Funds are reported publicly per release; no paywalled features in the
  open-source core.
