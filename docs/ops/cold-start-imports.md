# PERF-06: Cold-start / import-time notes

Cold start on Render free ≈ **~9 s app boot** (measured 2026-10-19 on a 2-vCPU
VM; Render free is slower — budget ~15–25 s) **plus** ~30–60 s platform wake.
Import time dominates the app portion. Rules:

## Rules

1. **Measure first:** `python -X importtime -c "import unified_app"` — sort by
   cumulative time; anything >200 ms at import is a suspect.
2. **Lazy-import heavy modules.** ML/NLP libs (transformers, torch, sklearn),
   PDF tooling, and provider SDKs must be imported **inside the function that
   uses them**, never at module top level — unless the module is only imported
   from that function anyway.
3. **No network I/O at import time.** No API calls, no DNS, no DB connects in
   module scope or `create_app` before the first request needs it. (The
   opportunities auto-refresh is already gated by `OPP_NO_AUTO_REFRESH=1` in
   tests; ensure the same discipline in production boot.)
4. **No `subprocess`/git at import.** `/version` shells out to `git` per
   request today — acceptable (cached would be nicer), but it must never run
   at import.
5. **Defer data loads.** Large JSON (skills taxonomy, question banks) should
   load lazily on first use with a module-level cache, not at import.

## Current known import costs (2026-10-19)

- Full `create_app()` boot: ~9 s wall, 127 MB peak RSS (see docs/ops/memory.md).
- The bulk is the ~70 `studybuddy/*` modules + Flask extension setup. The
  single biggest win available is lazy-loading the heaviest feature modules
  (ultimate_reg_*, pdf_qa, arxiv_import) — they are imported eagerly today.

## CI guard

`scripts/check_memory.py` (PERF-09) fails the build if boot + core workloads
exceed 400 MB RSS; a future iteration should also assert boot time < 20 s on
the CI runner to catch import-time regressions.
