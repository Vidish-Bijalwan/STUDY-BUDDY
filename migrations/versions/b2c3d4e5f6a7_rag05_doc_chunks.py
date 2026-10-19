"""RAG-05: doc_chunks table — move document chunks out of JSON blobs.

Revision ID: b2c3d4e5f6a7
Revises: 01c271a81d47
Create Date: 2026-10-19

``doc_chunks`` stores one row per retrieval chunk (see RAG-02 schema in
``studybuddy/rag_chunking.py``): id, doc_id (FK -> study_doc.id), page,
section, char_start, char_end, text, embedding_id, created_at, with an
index on (doc_id, page) so per-query top-k loads stay independent of
document size.

``migrate_existing(engine)`` copies ``StudyDoc.data["chunks"]`` rows into
the table. It is idempotent (docs that already have rows are skipped) and
is NOT run automatically by ``upgrade()`` — run it from a background
indexing task (ARC-11) or a one-off script after deploying, so large
libraries don't block the schema migration.
"""
from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = '01c271a81d47'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'doc_chunks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('doc_id', sa.Integer(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('section', sa.String(length=255), nullable=True),
        sa.Column('char_start', sa.Integer(), nullable=True),
        sa.Column('char_end', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('embedding_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                   server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['doc_id'], ['study_doc.id'],
                                name='fk_doc_chunks_doc_id_study_doc',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # RAG-05 acceptance: per-query top-k loads indexed by (doc_id, page).
    op.create_index('ix_doc_chunks_doc_page', 'doc_chunks',
                    ['doc_id', 'page'], unique=False)
    op.create_index(op.f('ix_doc_chunks_doc_id'), 'doc_chunks',
                    ['doc_id'], unique=False)
    op.create_index(op.f('ix_doc_chunks_embedding_id'), 'doc_chunks',
                    ['embedding_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_doc_chunks_embedding_id'), table_name='doc_chunks')
    op.drop_index(op.f('ix_doc_chunks_doc_id'), table_name='doc_chunks')
    op.drop_index('ix_doc_chunks_doc_page', table_name='doc_chunks')
    op.drop_table('doc_chunks')


# ---------------------------------------------------------------------------
# Data migration helper (idempotent; not run by upgrade())
# ---------------------------------------------------------------------------

def _chunk_embedding_id(doc_id, page, section, text):
    """Deterministic chunk id, mirroring studybuddy.rag_chunking.

    Imported lazily so this migration file stays import-safe without the
    app on the path (alembic loads it by file location in tests).
    """
    try:
        from studybuddy.rag_chunking import make_embedding_id
        return make_embedding_id(doc_id, page, section, 0, text or "")
    except Exception:
        import hashlib
        digest = hashlib.sha256(
            "|".join([str(doc_id), str(page), section or "",
                      "0", text or ""]).encode("utf-8")).hexdigest()
        return "emb-" + digest[:16]


def migrate_existing(engine=None, batch_size=500):
    """Copy ``study_doc.data["chunks"]`` into ``doc_chunks``.

    Idempotent: any ``doc_id`` that already has rows in ``doc_chunks`` is
    skipped. Old chunk dicts (``{"page", "index", "text", "heading"}``)
    have no char offsets, so ``char_start``/``char_end`` are stored NULL —
    honest about provenance instead of fabricating offsets. ``section``
    comes from the chunk's ``"heading"``.

    Returns ``{"docs_seen": n, "docs_migrated": n, "chunks_inserted": n}``.
    Never raises on malformed rows (they are skipped and counted).
    """
    import json as _json

    if engine is None:
        bind = op.get_bind()
    else:
        bind = engine
    meta = sa.MetaData()
    study_doc = sa.Table('study_doc', meta, autoload_with=bind)
    doc_chunks = sa.Table('doc_chunks', meta, autoload_with=bind)

    result = {"docs_seen": 0, "docs_migrated": 0, "chunks_inserted": 0,
              "docs_skipped": 0, "chunks_skipped": 0}
    with bind.begin() as conn:
        existing = {
            row[0] for row in
            conn.execute(sa.select(doc_chunks.c.doc_id).distinct())
        }
        rows = conn.execute(
            sa.select(study_doc.c.id, study_doc.c.data)).fetchall()
        pending: list[dict] = []

        def _flush():
            if pending:
                conn.execute(doc_chunks.insert(), pending)
                result["chunks_inserted"] += len(pending)
                pending.clear()

        for doc_id, data in rows:
            result["docs_seen"] += 1
            if doc_id in existing:
                result["docs_skipped"] += 1
                continue
            chunks = None
            if isinstance(data, dict):
                chunks = data.get("chunks")
            elif isinstance(data, str):
                try:
                    chunks = _json.loads(data).get("chunks")
                except (ValueError, AttributeError):
                    chunks = None
            if not isinstance(chunks, list) or not chunks:
                result["docs_skipped"] += 1
                continue
            valid = 0
            for ch in chunks:
                if not isinstance(ch, dict):
                    result["chunks_skipped"] += 1
                    continue
                text = ch.get("text")
                if not isinstance(text, str) or not text.strip():
                    result["chunks_skipped"] += 1
                    continue
                try:
                    page = ch.get("page")
                    page = int(page) if page is not None else None
                except (TypeError, ValueError):
                    page = None
                section = ch.get("heading") or ch.get("section")
                if not isinstance(section, str):
                    section = None
                pending.append({
                    "doc_id": doc_id,
                    "page": page,
                    "section": (section or "")[:255] or None,
                    "char_start": None,
                    "char_end": None,
                    "text": text,
                    "embedding_id": _chunk_embedding_id(
                        doc_id, page, section, text),
                    "created_at": datetime.now(UTC),
                })
                valid += 1
                if len(pending) >= batch_size:
                    _flush()
            if valid:
                result["docs_migrated"] += 1
                existing.add(doc_id)
            else:
                result["docs_skipped"] += 1
        _flush()
    return result
