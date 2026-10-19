"""ARC-04: schema quality improvements (pragmatic subset)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-19

What this migration does (verified against unified_app.py models first):
  (a) Composite indexes (user_id, created_at) on four high-traffic report
      tables: resume_analysis, jd_match_report, bullet_rewrite,
      linkedin_report. These back the "my reports / history" list pages
      filtered by user and ordered by recency (see also ARC-13 pagination).
  (b) paper_import.fetched_at: String(32) -> DateTime(timezone=True).
      The column EXISTS (PaperImport model, arXiv/DOI import provenance).
      Existing ISO-8601 string values are parsed in Python, normalized to UTC,
      and rewritten in SQLite's canonical 'YYYY-MM-DD HH:MM:SS' form;
      unparseable values are nulled (counted in the migration log) so a later
      ORM DateTime declaration never chokes on read. Postgres uses USING
      fetched_at::timestamptz.
      SQLite gotcha (verified 2026-10-19): batch_alter_table's table copy
      emits CAST(fetched_at AS DATETIME), and SQLite's CAST to DATETIME
      applies NUMERIC affinity, truncating '2026-10-19T10:30:00+00:00' to
      the integer 2026 — silent data loss. So on SQLite we migrate the data
      explicitly (add new column, UPDATE rows, drop old, rename) with no
      CAST anywhere.
      ORM follow-up (unified_app.py, owned by another workstream): change the
      PaperImport.fetched_at column declaration from String(32) to DateTime
      so reads/writes use datetime objects end to end.
  (c) Add nullable updated_at to three main tables that lack it:
      goal, job_application, health_review. ORM follow-up: declare the
      columns with onupdate=datetime.now(UTC) in unified_app.py.

Deliberately NOT done here (documented as Postgres-only follow-ups):
  * Enum/CheckConstraint conversions for free-text status columns
    (e.g. DSAProgress.status and similar String(20) "comment value"
    columns). SQLite cannot ALTER a column to add a CHECK constraint
    without a full table rebuild, and silently rewriting status strings
    risks data loss; do these on Postgres with explicit value mapping and
    a data-backup step (ARC-04 full item).
  * StudyDoc.data -> doc_chunks normalization (RAG-05, separate workstream).
  * Timezone-awareness sweep of all DateTime columns (ARC-15).
"""
from alembic import op
import sqlalchemy as sa

from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


# (a) report tables getting the composite (user_id, created_at) index.
_COMPOSITE_INDEX_TABLES = (
    "resume_analysis",
    "jd_match_report",
    "bullet_rewrite",
    "linked_in_report",
)

# (c) main tables gaining a nullable updated_at column.
_UPDATED_AT_TABLES = (
    "goal",
    "job_application",
    "health_review",
)


def _parse_iso(value):
    """Parse an ISO-8601-ish timestamp to an aware datetime, or None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _copy_fetched_at_sqlite(src, dst):
    """Copy fetched_at values from ``src`` to ``dst`` column, parsed to UTC.

    Plain UPDATEs only — deliberately no CAST (see module docstring: SQLite
    CAST(x AS DATETIME) truncates ISO strings to their leading year).
    Returns (rewritten, nulled) counts for the migration log.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT id, {src} FROM paper_import")).fetchall()
    rewritten, nulled = 0, 0
    for row_id, value in rows:
        if value is None:
            continue
        dt = _parse_iso(value)
        if dt is None:
            conn.execute(
                sa.text(f"UPDATE paper_import SET {dst} = NULL WHERE id = :i"),
                {"i": row_id},
            )
            nulled += 1
        else:
            canonical = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                sa.text(f"UPDATE paper_import SET {dst} = :v WHERE id = :i"),
                {"v": canonical, "i": row_id},
            )
            rewritten += 1
    return rewritten, nulled


def upgrade():
    # (a) composite indexes for frequent (user_id, created_at) filters.
    for table in _COMPOSITE_INDEX_TABLES:
        op.create_index(f"ix_{table}_user_created", table,
                        ["user_id", "created_at"], unique=False)

    # (b) paper_import.fetched_at String(32) -> timezone-aware DateTime.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Explicit add/copy/drop/rename: batch_alter_table would emit
        # CAST(fetched_at AS DATETIME), which silently truncates ISO strings
        # to the integer year on SQLite (see module docstring).
        op.add_column("paper_import",
                      sa.Column("fetched_at_new", sa.DateTime(timezone=True),
                                nullable=True))
        rewritten, nulled = _copy_fetched_at_sqlite("fetched_at",
                                                    "fetched_at_new")
        print(f"ARC-04: paper_import.fetched_at converted "
              f"({rewritten} rewritten to UTC, {nulled} unparseable nulled)")
        op.execute("ALTER TABLE paper_import DROP COLUMN fetched_at")
        op.execute("ALTER TABLE paper_import "
                   "RENAME COLUMN fetched_at_new TO fetched_at")
    else:
        # Postgres: explicit cast; fails loudly on bad data (honest).
        op.alter_column(
            "paper_import", "fetched_at",
            existing_type=sa.String(32),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using="fetched_at::timestamptz",
        )

    # (c) updated_at on main tables that lack it (nullable; ORM follow-up
    # declares onupdate behavior in unified_app.py).
    for table in _UPDATED_AT_TABLES:
        op.add_column(table, sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade():
    # (c) revert first (reverse order of upgrade).
    for table in _UPDATED_AT_TABLES:
        op.drop_column(table, "updated_at")

    # (b) fetched_at back to String(32). Values are canonical UTC strings
    # ('YYYY-MM-DD HH:MM:SS', 19 chars) so they fit String(32) as-is.
    # Same CAST-avoidance dance as upgrade, in reverse.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.add_column("paper_import",
                      sa.Column("fetched_at_old", sa.String(32), nullable=True))
        conn = op.get_bind()
        conn.execute(sa.text(
            "UPDATE paper_import SET fetched_at_old = fetched_at"))
        op.execute("ALTER TABLE paper_import DROP COLUMN fetched_at")
        op.execute("ALTER TABLE paper_import "
                   "RENAME COLUMN fetched_at_old TO fetched_at")
    else:
        op.alter_column(
            "paper_import", "fetched_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.String(32),
            existing_nullable=True,
            postgresql_using=(
                "to_char(fetched_at AT TIME ZONE 'UTC', "
                "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')"
            ),
        )

    # (a) drop the composite indexes.
    for table in _COMPOSITE_INDEX_TABLES:
        op.drop_index(f"ix_{table}_user_created", table_name=table)
