"""WS1-RAG tests: chunking (RAG-02), hybrid fusion (RAG-03), doc_chunks
migration (RAG-05), research etiquette (RAG-06), honesty labels (RAG-08).

Run with the repo venv: ~/workspace/acra/.venv/bin/python -m pytest
tests/test_ws1_rag.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]

from studybuddy import rag_chunking as rc
from studybuddy import rag_etiquette as ret
from studybuddy import rag_honesty as rh
from studybuddy import rag_hybrid as rhy
from studybuddy.rag_hybrid import Embedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _para(i: int) -> str:
    return (
        "Paragraph %d discusses retrieval augmented generation for study "
        "documents. Chunking quality determines how well the retriever can "
        "find the supporting passage for a student question about dense "
        "embeddings and hybrid ranking methods." % i
    )


def _long_pages(n_paras: int = 26) -> list[dict]:
    body = "\n\n".join(_para(i) for i in range(n_paras))
    return [
        {"page": 1, "text": "# Introduction\n\n" + body},
        {"page": 2, "text": "## Methods\n\n" + "\n\n".join(_para(100 + i)
                                                      for i in range(n_paras))},
    ]


def _full_text(pages: list[dict]) -> str:
    return "\n".join(p["text"] for p in pages)


# ---------------------------------------------------------------------------
# RAG-02: structure-aware chunking
# ---------------------------------------------------------------------------

class TestChunking:
    def test_chunk_schema_keys(self):
        chunks = rc.chunk_document(7, [{"page": 1, "text": _para(0)}])
        assert chunks, "expected at least one chunk"
        for c in chunks:
            for key in ("doc_id", "page", "section", "char_start",
                        "char_end", "text", "embedding_id"):
                assert key in c, f"missing key {key}"
            assert c["doc_id"] == 7

    def test_chunk_overlap(self):
        pages = _long_pages()
        chunks = rc.chunk_document("doc-1", pages)
        assert len(chunks) >= 3, "long doc should produce several chunks"
        for prev, nxt in zip(chunks, chunks[1:], strict=False):
            # Ranges overlap (continuity, nothing lost at the boundary)...
            assert nxt["char_start"] < prev["char_end"]
            assert nxt["char_start"] > prev["char_start"]
            # ...and the next chunk starts with carried-over text.
            assert nxt["text"][:80] in prev["text"]
            # Overlap is ~15% (whole trailing blocks): between 5% and 35%.
            overlap_chars = prev["char_end"] - nxt["char_start"]
            ratio = overlap_chars / max(len(prev["text"]), 1)
            assert 0.05 <= ratio <= 0.35, f"overlap ratio {ratio}"

    def test_chunk_metadata_sections_and_pages(self):
        pages = _long_pages()
        full = _full_text(pages)
        chunks = rc.chunk_document(1, pages)
        # char offsets always slice the exact chunk text.
        for c in chunks:
            assert full[c["char_start"]:c["char_end"]] == c["text"]
            assert c["char_start"] < c["char_end"]
        sections = {c["section"] for c in chunks}
        assert "Introduction" in sections
        assert "Methods" in sections
        pages_seen = [c["page"] for c in chunks]
        assert pages_seen == sorted(pages_seen), "reading order preserved"
        assert set(pages_seen) == {1, 2}

    def test_embedding_id_deterministic(self):
        pages = _long_pages(8)
        a = rc.chunk_document(3, pages)
        b = rc.chunk_document(3, pages)
        assert [c["embedding_id"] for c in a] == [c["embedding_id"] for c in b]
        for c in a:
            assert re.fullmatch(r"emb-[0-9a-f]{16}", c["embedding_id"])

    def test_tables_are_separate_chunks(self):
        table = ("| Method | Accuracy |\n| ------ | -------- |\n"
                 "| A | 0.91 |\n| B | 0.87 |\n| C | 0.83 |")
        pages = [{"page": 1, "text":
                  "# Results\n\n" + _para(0) + "\n\n" + table + "\n\n" + _para(1)}]
        chunks = rc.chunk_document(9, pages)
        table_chunks = [c for c in chunks if c["kind"] == "table"]
        assert len(table_chunks) == 1, "table must be its own chunk"
        tc = table_chunks[0]
        assert "Accuracy" in tc["text"]
        assert "Paragraph 0" not in tc["text"], "no prose merged into table"
        assert tc["section"] == "Results"

    def test_chunk_sizes_in_range(self):
        chunks = rc.chunk_document(1, _long_pages())
        for c in chunks[:-1]:  # last chunk may be a short tail
            tokens = rc.estimate_tokens(c["text"])
            assert tokens <= rc.MAX_TOKENS, f"chunk too big: {tokens}"

    def test_detect_heading_and_table(self):
        assert rc.detect_heading("# Hello World") == "Hello World"
        assert rc.detect_heading("2.3 Methods") == "Methods"
        assert rc.detect_heading("INTRODUCTION") == "Introduction"
        assert rc.detect_heading("just a normal sentence here.") is None
        assert rc.detect_table_kind(["| a | b |", "| - | - |",
                                     "| 1 | 2 |"]) == "pipe"
        assert rc.detect_table_kind(["a\tb", "1\t2", "3\t4"]) == "tsv"
        assert rc.detect_table_kind(["plain", "paragraph"]) is None

    def test_chunk_document_bad_input(self):
        assert rc.chunk_document(1, []) == []
        assert rc.chunk_document(1, None) == []
        assert rc.chunk_document(1, [{"page": 1, "text": "   \n  "}]) == []


# ---------------------------------------------------------------------------
# RAG-03: RRF fusion math + fallback
# ---------------------------------------------------------------------------

class TestRRF:
    def test_rrf_math(self):
        scores = rhy.reciprocal_rank_fusion([["a", "b"], ["b", "a", "c"]],
                                            k=60)
        assert scores["a"] == pytest.approx(1 / 61 + 1 / 62)
        assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
        assert scores["a"] == pytest.approx(scores["b"])
        assert scores["c"] == pytest.approx(1 / 63)
        assert scores["c"] < scores["a"]

    def test_rrf_single_list_and_empty(self):
        scores = rhy.reciprocal_rank_fusion([["x", "y"]])
        assert scores == {"x": pytest.approx(1 / 61),
                          "y": pytest.approx(1 / 62)}
        assert rhy.reciprocal_rank_fusion([]) == {}
        assert rhy.reciprocal_rank_fusion(None) == {}

    def test_cosine_sim(self):
        assert rhy.cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
        assert rhy.cosine_sim([1.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)
        assert rhy.cosine_sim([0.0, 0.0], [1.0, 0.0]) == 0.0


class _FakeEmbedder(Embedder):
    model_name = "fake-test"
    dims = 2

    def __init__(self, vecs: dict[str, list[float]]):
        self._vecs = vecs

    def embed(self, texts):
        return [self._vecs[t] for t in texts]

    def embed_query(self, text):
        return [0.0, 1.0]


class TestHybridRetrieve:
    def _chunks(self):
        return [
            {"text": "apple banana orange", "index": 0},
            {"text": "quantum physics entanglement", "index": 1},
            {"text": "apple pie recipe", "index": 2},
        ]

    def test_fallback_no_embedder(self):
        """RAG-03 acceptance: pure-Python lexical path works with zero config."""
        res = rhy.hybrid_retrieve(self._chunks(), "apple", top_k=3,
                                  embedder=None)
        assert len(res) >= 2
        top = res[0]
        assert top["dense_rank"] is None
        assert top["embedding_model"] is None
        assert top["embedding_dims"] is None
        assert top["lexical_rank"] == 1
        assert top["rrf_score"] == pytest.approx(1 / 61)
        assert "apple" in top["text"]

    def test_fusion_combines_both_signals(self):
        chunks = self._chunks()
        texts = [c["text"] for c in chunks]
        emb = _FakeEmbedder({
            texts[0]: [1.0, 0.0],    # cosine 0.0 with query
            texts[1]: [0.0, 1.0],    # cosine 1.0 (dense rank 1)
            texts[2]: [0.5, 0.866],  # cosine ~0.866 (dense rank 2)
        })
        res = rhy.hybrid_retrieve(chunks, "apple", top_k=3, embedder=emb)
        assert len(res) == 3
        # chunk 2 appears in BOTH lists -> wins the fusion.
        assert res[0]["text"] == "apple pie recipe"
        lr, dr = res[0]["lexical_rank"], res[0]["dense_rank"]
        assert lr is not None and dr is not None
        assert res[0]["rrf_score"] == pytest.approx(
            1 / (60 + lr) + 1 / (60 + dr))
        assert res[0]["embedding_model"] == "fake-test"
        assert res[0]["embedding_dims"] == 2
        # Fused order differs from pure lexical order (fusion did something).
        lex_only = rhy.hybrid_retrieve(chunks, "apple", top_k=3,
                                       embedder=None)
        assert [r["text"] for r in res] != [r["text"] for r in lex_only]

    def test_dense_failure_degrades_to_lexical(self):
        class Boom(Embedder):
            model_name = "boom"
            dims = 2

            def embed(self, texts):
                raise RuntimeError("embedding API down")

        res = rhy.hybrid_retrieve(self._chunks(), "apple", top_k=3,
                                  embedder=Boom())
        assert len(res) >= 2  # lexical fallback, no raise
        assert all(r["dense_rank"] is None for r in res)

    def test_select_embedder(self, monkeypatch):
        assert rhy.select_embedder("none") is None
        assert isinstance(rhy.select_embedder("local"), rhy.LocalEmbedder)
        assert isinstance(rhy.select_embedder("gemini"), rhy.GeminiEmbedder)
        with pytest.raises(ValueError):
            rhy.select_embedder("bogus")
        monkeypatch.setenv("RAG_EMBEDDER", "none")
        assert rhy.select_embedder() is None

    def test_local_stub_raises_with_guidance(self):
        with pytest.raises(RuntimeError, match="fastembed"):
            rhy.LocalEmbedder().embed(["hello"])

    def test_gemini_missing_key_raises_clear_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            rhy.GeminiEmbedder().embed(["hello"])


# ---------------------------------------------------------------------------
# RAG-06: research etiquette
# ---------------------------------------------------------------------------

class TestEtiquette:
    def test_user_agent_has_contact(self, monkeypatch):
        monkeypatch.setattr(ret, "CONTACT_EMAIL", "vivek@example.com")
        ua = ret.user_agent()
        assert "mailto:vivek@example.com" in ua
        assert "StudyBuddy" in ua

    def test_arxiv_rate_limit_interval(self):
        rl = ret.RateLimiter()
        assert rl.interval_for("export.arxiv.org") == 3.0
        assert rl.interval_for("EXPORT.ARXIV.ORG") == 3.0  # case-insensitive

    def test_rate_limiter_waits(self, monkeypatch):
        rl = ret.RateLimiter()
        now = [1000.0]
        slept: list[float] = []
        monkeypatch.setattr(time, "monotonic", lambda: now[0])
        monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
        assert rl.wait("https://export.arxiv.org/api/query") == 0.0
        assert rl.wait("https://export.arxiv.org/api/query") == \
            pytest.approx(3.0)
        assert slept == [pytest.approx(3.0)]
        # A different host is not throttled by arXiv's clock.
        assert rl.wait("https://api.openalex.org/works") == 0.0

    def _fake_session(self, monkeypatch, behavior):
        class FakeSession:
            def get(self, url, params=None, headers=None, timeout=None):
                return behavior(url, params, headers, timeout)
        monkeypatch.setattr(ret, "get_session", lambda: FakeSession())

    def test_polite_get_network_failure_graceful(self, monkeypatch):
        import requests as rq

        def boom(url, params, headers, timeout):
            raise rq.ConnectionError("dns down")
        self._fake_session(monkeypatch, boom)
        res = ret.polite_get("https://export.arxiv.org/api/query",
                             use_cache=False)
        assert res["ok"] is False
        assert "hint" in res and res["hint"]
        assert res["retryable"] is True

    def test_polite_get_429_graceful(self, monkeypatch):
        class FakeResp:
            status_code = 429
            headers = {}
            text = ""

        self._fake_session(monkeypatch,
                           lambda u, p, h, t: FakeResp())
        res = ret.polite_get("https://export.arxiv.org/api/query",
                             use_cache=False)
        assert res["ok"] is False
        assert "429" in res["error"]
        assert res["retryable"] is True

    def test_fetch_xml_uses_defusedxml(self, monkeypatch):
        class FakeResp:
            status_code = 200
            headers = {}
            text = '<feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'

        self._fake_session(monkeypatch, lambda u, p, h, t: FakeResp())
        res = ret.fetch_xml("https://export.arxiv.org/api/query",
                            params={"id_list": "1706.03762"})
        assert res["ok"] is True
        assert res["root"].tag.endswith("feed")

    def test_fetch_xml_bomb_graceful(self, monkeypatch):
        bomb = ('<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "x">'
                '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
                '<feed>&b;</feed>')

        class FakeResp:
            status_code = 200
            headers = {}
            text = bomb

        self._fake_session(monkeypatch, lambda u, p, h, t: FakeResp())
        res = ret.fetch_xml("https://export.arxiv.org/api/query")
        assert res["ok"] is False  # entity expansion blocked, no raise

    def test_stamp_record(self):
        rec = {"title": "T"}
        out = ret.stamp_record(rec, "arxiv")
        assert out["source"] == "arxiv"
        assert "retrieved_at" in out
        assert "retrieved_at" not in rec  # input not mutated

    def test_etag_cache_304(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ret, "_CACHE_DIR", str(tmp_path))
        calls: list[dict] = []

        class FakeResp:
            status_code = 200
            headers = {"ETag": '"abc123"'}
            text = "<feed/>"

        class FakeResp304:
            status_code = 304
            headers = {}
            text = ""

        def behavior(url, params, headers, timeout):
            calls.append(dict(headers or {}))
            if headers and headers.get("If-None-Match") == '"abc123"':
                return FakeResp304()
            return FakeResp()

        self._fake_session(monkeypatch, behavior)
        first = ret.polite_get("https://export.arxiv.org/api/query",
                               params={"a": "1"})
        assert first["ok"] is True and first["from_cache"] is False
        second = ret.polite_get("https://export.arxiv.org/api/query",
                                params={"a": "1"})
        assert second["ok"] is True and second["from_cache"] is True
        assert second["text"] == "<feed/>"
        assert calls[1].get("If-None-Match") == '"abc123"'


# ---------------------------------------------------------------------------
# RAG-08: honesty labels
# ---------------------------------------------------------------------------

def _fake_doc(doc_id, title, chunk_texts):
    return SimpleNamespace(
        id=doc_id, user_id=1, title=title,
        data={"chunks": [
            {"page": 1, "index": i, "text": t}
            for i, t in enumerate(chunk_texts)]})


class TestHonesty:
    def _report(self):
        from studybuddy import gap_finder
        photo = ("Photosynthesis converts light into chemical energy. "
                 "Chlorophyll absorbs photons in the thylakoid membrane. "
                 "Photosynthesis efficiency depends on light intensity.")
        docs = [
            _fake_doc(1, "Paper A", [photo, photo, photo]),
            _fake_doc(2, "Paper B", [
                "However, some studies contradict the efficiency claims. "
                "In contrast to earlier results, shade plants differ."]),
        ]
        return gap_finder.generate_gap_report(docs)

    def test_label_gap_report(self):
        labeled = rh.label_gap_report(self._report())
        assert labeled["method"] == "heuristic"
        assert labeled["method_label"] == "heuristic suggestions"
        assert "heuristic" in labeled["disclaimer"].lower()
        assert isinstance(labeled["evidence_summary"], list)
        assert labeled["evidence_summary"], "expected at least one gap"
        first = labeled["evidence_summary"][0]
        assert first["papers"], "evidence must name papers"
        assert first["terms"], "evidence must name terms"

    def test_label_gap_report_error_shape(self):
        labeled = rh.label_gap_report(
            {"gaps": [], "next_papers": [],
             "note": "Add at least 2 documents..."})
        assert rh.is_labeled(labeled)
        assert labeled["evidence_summary"] == []

    def test_label_lit_review(self):
        review = {"per_paper": [{"doc_id": 1, "title": "Paper A"}],
                  "themes": [{"name": "t", "terms": ["photosynthesis"],
                              "papers": ["Paper A", "Paper B"]}],
                  "claims_table": [{"claim": "c"}],
                  "coverage_gaps": "", "bibtex": ""}
        labeled = rh.label_lit_review(review)
        assert rh.is_labeled(labeled)
        assert "heuristic" in labeled["disclaimer"].lower()
        ev = labeled["evidence_summary"]
        assert ev["papers"] == ["Paper A", "Paper B"]
        assert ev["theme_terms"] == ["photosynthesis"]
        assert ev["claims"] == 1
        assert "method_label" not in review  # input not mutated

    def test_label_lit_review_error_shape(self):
        labeled = rh.label_lit_review({"error": "need 2 papers",
                                       "per_paper": [], "themes": [],
                                       "claims_table": [], "coverage_gaps": "",
                                       "bibtex": ""})
        assert rh.is_labeled(labeled)

    def test_is_labeled_false_for_plain(self):
        assert rh.is_labeled({}) is False
        assert rh.is_labeled(None) is False
        assert rh.is_labeled({"method": "heuristic"}) is False

    def test_gap_evidence_summary_terms(self):
        s = rh.gap_evidence_summary({
            "title": "Underexplored: 'photosynthesis' — deep",
            "type": "underexplored",
            "evidence": [{"doc": "Paper A", "page": 1, "chunk": 0,
                          "excerpt": "x"}]})
        assert s["terms"] == ["photosynthesis"]
        assert s["papers"] == ["Paper A"]


# ---------------------------------------------------------------------------
# RAG-05: doc_chunks migration (upgrade/downgrade on SQLite)
# ---------------------------------------------------------------------------

def _load_migration_module():
    path = (REPO / "migrations" / "versions"
            / "b2c3d4e5f6a7_rag05_doc_chunks.py")
    spec = importlib.util.spec_from_file_location(
        "b2c3d4e5f6a7_rag05_doc_chunks", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_flask_db(*args, db_path):
    env = dict(os.environ,
               DATABASE_URL=f"sqlite:///{db_path}",
               SKIP_DB_INIT="1",
               OPP_NO_AUTO_REFRESH="1",
               FLASK_APP="unified_app",
               SECRET_KEY="migration-test")
    return subprocess.run(
        [sys.executable, "-m", "flask", "db", *args],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=180)


def _tables(db_path):
    con = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")}
    finally:
        con.close()


def _insert_study_doc(db_path, doc_id, chunks):
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "insert into study_doc (id, user_id, title, source, data, "
            "created_at) values (?, 1, ?, 'upload', ?, "
            "datetime('now'))",
            (doc_id, f"Doc {doc_id}",
             json.dumps({"chunks": chunks})))
        con.commit()
    finally:
        con.close()


class TestDocChunksMigration:
    def test_upgrade_creates_table_and_indexes(self, tmp_path):
        db = tmp_path / "rag05.db"
        r = _run_flask_db("upgrade", "b2c3d4e5f6a7", db_path=db)
        assert r.returncode == 0, r.stderr[-800:]
        tables = _tables(db)
        assert "doc_chunks" in tables
        con = sqlite3.connect(str(db))
        try:
            idx = {r[0] for r in con.execute(
                "select name from sqlite_master where type='index' "
                "and tbl_name='doc_chunks'")}
        finally:
            con.close()
        assert "ix_doc_chunks_doc_page" in idx

    def test_migrate_existing_copies_and_is_idempotent(self, tmp_path):
        db = tmp_path / "rag05b.db"
        r = _run_flask_db("upgrade", "b2c3d4e5f6a7", db_path=db)
        assert r.returncode == 0, r.stderr[-800:]
        _insert_study_doc(db, 10, [
            {"page": 1, "index": 0, "text": "First chunk text here.",
             "heading": "Intro"},
            {"page": 2, "index": 1, "text": "Second chunk text here."},
            {"page": 3, "index": 2, "text": "   "},  # blank: skipped
        ])
        _insert_study_doc(db, 11, [])  # no chunks: skipped
        mod = _load_migration_module()
        import sqlalchemy as sa
        engine = sa.create_engine(f"sqlite:///{db}")
        res = mod.migrate_existing(engine)
        assert res["chunks_inserted"] == 2
        assert res["docs_migrated"] == 1
        con = sqlite3.connect(str(db))
        try:
            rows = con.execute(
                "select doc_id, page, section, text, embedding_id, "
                "char_start from doc_chunks order by id").fetchall()
        finally:
            con.close()
        assert len(rows) == 2
        assert rows[0][0] == 10 and rows[0][1] == 1
        assert rows[0][2] == "Intro"
        assert rows[0][3] == "First chunk text here."
        assert rows[0][4].startswith("emb-")
        assert rows[0][5] is None  # old chunks: no fabricated offsets
        # Idempotent: second run inserts nothing.
        res2 = mod.migrate_existing(engine)
        assert res2["chunks_inserted"] == 0
        con = sqlite3.connect(str(db))
        try:
            n = con.execute("select count(*) from doc_chunks").fetchone()[0]
        finally:
            con.close()
        assert n == 2

    def test_downgrade_removes_table(self, tmp_path):
        db = tmp_path / "rag05c.db"
        assert _run_flask_db(
            "upgrade", "b2c3d4e5f6a7", db_path=db).returncode == 0
        assert "doc_chunks" in _tables(db)
        r = _run_flask_db("downgrade", "01c271a81d47", db_path=db)
        assert r.returncode == 0, r.stderr[-800:]
        tables = _tables(db)
        assert "doc_chunks" not in tables
        assert "study_doc" in tables  # only our table is dropped
