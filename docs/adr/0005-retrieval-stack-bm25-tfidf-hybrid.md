# ADR 0005: Retrieval Stack — BM25/TF-IDF Now, Hybrid Path Later

- **Status:** Accepted
- **Date:** 2026-10-19
- **Deciders:** Vivek Bartwal (maintainer), Meta Muse (AI agent)

## Context

Resume↔JD matching, PDF Q&A, paper recommendations, and skill search all need
retrieval. Dense embeddings (`sentence-transformers` + vector DB) give better
recall but need ~500 MB+ RAM and a vector store — incompatible with the
512 MB free-tier ceiling (ADR 0002) and the no-heavy-deps rule.

## Decision

- **Default retrieval is lexical: BM25 / TF-IDF** over the local corpus.
  It runs in-process, in milliseconds, with zero extra infrastructure, and
  its failure modes (vocabulary mismatch) are explainable to users.
- The codebase keeps a **hybrid path open**: retriever interfaces accept a
  scorer, so a dense/embedding scorer can be plugged in later (paid tier,
  API-based embeddings, or ONNX light models) and fused with BM25 scores.
- No feature may *claim* semantic/vector search while running lexical
  retrieval (honesty rule — labels must say "keyword" where it is keyword).

## Consequences

- **Good:** fits the free tier; fast; no new infra; honest about limits.
- **Bad:** weaker recall on paraphrase-heavy queries (e.g. "built dashboards"
  vs "data visualization") — mitigated partially by the skills-taxonomy alias
  expansion (ENG-06).
- **Revisit when:** on a paid tier with RAM headroom, or when an embedding
  API fits the LLM budget (LLM-03) — then add the dense scorer behind the
  hybrid interface and A/B the quality delta before switching defaults.
