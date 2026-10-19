# ADR 0007: SSRF Protection via safe_fetch Allowlist

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

Several features fetch user-supplied URLs (paper PDFs from arXiv/DOI,
opportunity links, profile imports). A naive `requests.get(user_url)` is a
server-side request forgery (SSRF) hole: an attacker can probe internal
hosts (`169.254.169.254`, localhost services) through our server (SEC-08).

## Decision

All server-side fetches of user-influenced URLs go through
`studybuddy/safe_fetch.py`:

- **Allowlist by default**: only hosts needed for the feature
  (arxiv.org, export.arxiv.org, doi.org, api.openalex.org, …) are permitted;
  everything else is refused.
- **No private targets ever**: DNS is resolved first and the fetch is
  refused if it resolves to loopback, link-local, or RFC-1918 ranges —
  even for allowlisted names (defeats DNS rebinding).
- **Hardening**: redirects are followed only within the allowlist,
  response size and timeouts are capped, and content-type is checked before
  parsing.
- Direct `requests.get` on user-supplied URLs elsewhere in the codebase is
  treated as a security bug.

## Consequences

- **Good:** SSRF class of bugs is structurally closed, not per-call; new
  features get the protection by using the one helper.
- **Bad:** legitimate new sources need an allowlist addition + review (small
  friction, intentional); DNS-resolution-before-fetch adds a lookup per call.
- **Revisit when:** a feature needs broad web fetching (e.g. general
  link unfurling) — then move to a dedicated egress proxy with filtering
  instead of widening the allowlist.
