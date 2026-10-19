# LLM Model Lifecycle (LLM-10)

> **Honesty note:** every provider below is consumed on a **free tier**.
> Free-tier model IDs, rate limits, and data-use terms change without notice —
> a model that works today can be deprecated, renamed, or paywalled tomorrow.
> This table is re-verified **quarterly**; the "Pinned date" column is the last
> date the entry was confirmed working, not a guarantee.

| Model | Provider | Use in STUDY-BUDDY | Pinned date | Replacement plan | Terms-review date |
|---|---|---|---|---|---|
| (Gemini default in `call_gemini_direct`) | Google Gemini (`GEMINI_API_KEY`) | Primary provider — first in the `ai_gateway` server chain | 2026-10-19 | If the default model is retired/renamed, pin the successor model ID explicitly in `unified_app.call_gemini_direct`; keep Groq as automatic fallback (chain already falls through) | 2027-01-19 |
| `llama-3.3-70b-versatile` | Groq (`GROQ_API_KEY`) | Second in chain — long-context reasoning fallback | 2026-10-19 | Groq retires dated models regularly: on deprecation notice, switch `_GROQ_MODEL` to the current `llama-3.x` versatile successor; verify with the LLM smoke test before deploy | 2027-01-19 |
| `google/gemma-4-31b-it:free` | OpenRouter (`OPENROUTER_API_KEY`) | Third in chain + BYOK target — free `:free` slug | 2026-10-19 (verified in `:free` list 2026-10-15) | `:free` slugs churn fastest: on removal, pick another `:free` instruct model from the OpenRouter free list, update `_OPENROUTER_MODEL`, re-run golden prompt tests | 2027-01-19 |
| `llama3.2` (default; override via `LLM_MODEL`) | Local / Ollama (`LLM_BASE_URL`) | Privacy-first option — prompts never leave the machine | 2026-10-19 | Operator's choice: any OpenAI-compatible local model; no vendor deprecation risk, only local upgrade discipline | 2027-01-19 |

## How the chain degrades

`studybuddy/ai_gateway.py` tries providers in order
local → Gemini → Groq → OpenRouter (when configured), with per-provider
circuit breakers and retries. If a model disappears:

1. That provider raises → the chain falls through to the next provider.
2. If **all** fail (or `LLM_MODE=off`, or the LLM-03 quota/budget is spent),
   callers must render the **rule-based fallback** with the banner
   "Showing rule-based suggestions; AI is temporarily unavailable" (LLM-09).
   A spinner that ends silently is a bug.

## Monitoring duties (quarterly, next: 2027-01-19)

- [ ] Re-run the AI smoke test against each configured provider.
- [ ] Check each provider's changelog/deprecation notices for our model IDs.
- [ ] Re-read data-use terms for the free tier of each provider in use
      (especially: whether free-tier prompts are used for training, and any
      regional restrictions on serving end users). Record findings here.
- [ ] Update "Pinned date" above and commit.

## Decision log pointer

Privacy modes (`LLM_MODE=off|byok|server`) are decided in
`docs/adr/0006-privacy-modes-llm-mode.md`. Cost control (quotas/budget
cutoff) lives in `studybuddy/llm_ledger.py` (LLM-03).
