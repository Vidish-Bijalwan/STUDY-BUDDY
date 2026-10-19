# ADR 0006: Privacy Modes — LLM_MODE off/byok/server

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

AI features send user text (resumes, PDFs, messages) to third-party LLM
providers. Users differ in what they accept: some want zero external calls,
some will bring their own key, most accept server-side calls with consent.
One hardcoded behavior cannot serve all three (PRIV-03/05).

## Decision

`LLM_MODE` env var selects the privacy posture; `studybuddy/ai_gateway.py`
enforces it centrally:

- **`off`** — no LLM calls at all; `generate()` raises `AIError("disabled")`
  and every AI feature renders its **rule-based fallback** with a clear
  banner (LLM-09). For the privacy-maximal user.
- **`byok`** — the caller must supply their own API key per request; it is
  used for that request only, never logged or stored. Server pays nothing;
  the provider sees the user directly.
- **`server`** (default) — the server's provider chain
  (local → Gemini → Groq → OpenRouter) serves requests. Requires the
  one-time LLM consent record (PRIV-03), PII redaction before sending
  (LLM-06/PRIV-08), per-user quotas and a monthly budget with automatic
  rule-based fallback (LLM-03), and no prompt/response content in logs
  (LLM-08).

## Consequences

- **Good:** one switch covers privacy-maximal, cost-shifting, and
  full-service postures; consent + redaction + quotas are enforced in one
  place instead of per feature.
- **Bad:** three modes triple the fallback-test matrix; `byok` UX depends on
  users obtaining keys (documented in Profile → AI Settings).
- **Revisit when:** a paid tier with a data-processing agreement changes the
  calculus, or usage data shows one mode dominates — then simplify.
