"""ARC-03 regression: production Postgres schema self-heal at boot.

Production (Render free tier) has no release step, so `flask db upgrade`
never ran: the DB predates the Alembic migrations (create_all era) and is
missing tables/columns the current models need (`user.email_verified`,
`llm_consent`, `user_api_key`, ...). Every User query then 500s — after
the 2026-10-20 domain move this surfaced as register/login being down and
quizzes/aptitude (which need an account) unreachable.

`create_app` now runs an idempotent, additive-only schema ensure for
Postgres at boot. These tests run against a REAL Postgres (pgserver) and
prove: old schema -> boot -> auth + quiz flows work; empty DB -> boot ->
works; booting twice is harmless.

Skipped automatically when pgserver/psycopg are unavailable (dev machines
without the PG test extras); CI's test-postgres job covers the same path.
"""

import pytest

pgserver = pytest.importorskip("pgserver")
pytest.importorskip("psycopg")

from sqlalchemy import text  # noqa: E402

from unified_app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

# Artifacts added by post-baseline migrations; dropping them simulates the
# pre-migration production schema.
_OLD_SCHEMA_DDL = [
    'ALTER TABLE "user" DROP COLUMN IF EXISTS email_verified',
    'ALTER TABLE "user" DROP COLUMN IF EXISTS email_verified_at',
    'ALTER TABLE "user" DROP COLUMN IF EXISTS is_admin',
    "DROP TABLE IF EXISTS llm_consent",
    "DROP TABLE IF EXISTS password_reset_token",
    "DROP TABLE IF EXISTS user_api_key",
    "DROP TABLE IF EXISTS doc_chunks",
    "DROP TABLE IF EXISTS llm_usage",
    "DROP TABLE IF EXISTS alembic_version",
]


@pytest.fixture(scope="module")
def _pg_server():
    # One server for the whole module: spinning up a fresh Postgres per
    # test is slow. The data dir must NOT pre-exist under pytest's
    # root-owned tmp dirs — pgserver runs initdb as the unprivileged
    # 'pgserver' user, so point it at a fresh path directly under /tmp.
    import shutil
    import uuid
    pg_dir = f"/tmp/sb_pg_{uuid.uuid4().hex[:10]}"
    srv = pgserver.get_server(pg_dir)
    yield srv
    try:
        srv.cleanup()
    except Exception:
        pass
    shutil.rmtree(pg_dir, ignore_errors=True)


_db_counter = [0]


@pytest.fixture()
def pg_uri(_pg_server):
    """A fresh, empty database on the shared module server per test."""
    import psycopg
    _db_counter[0] += 1
    dbname = f"ensure_test_{_db_counter[0]}"
    admin_uri = _pg_server.get_uri()  # 'postgres' database
    with psycopg.connect(admin_uri, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{dbname}"')
    assert "/postgres?" in admin_uri, admin_uri
    return admin_uri.replace("/postgres?", f"/{dbname}?", 1)


def _make_app(uri):
    return create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": uri,
        "WTF_CSRF_ENABLED": False,
        "SECRET_KEY": "schema-ensure-test-secret",
    })


def _register(client, email="ensure@example.com"):
    return client.post("/register", data={
        "name": "Ensure User", "email": email,
        "password": "Str0ng!Pass1", "age_confirm": "1",
    }, follow_redirects=False)


def _login(client, email="ensure@example.com"):
    return client.post("/login", data={
        "email": email, "password": "Str0ng!Pass1",
    }, follow_redirects=False)


def test_boot_on_empty_postgres_creates_working_schema(pg_uri):
    app = _make_app(pg_uri)
    client = app.test_client()
    assert _register(client).status_code == 302
    assert _login(client).status_code == 302


def test_boot_repairs_pre_migration_schema(pg_uri):
    """The production bug: old schema -> register 500 -> boot repair -> 302."""
    # Boot 1: full current schema, then roll it back to the old state.
    app = _make_app(pg_uri)
    with app.app_context():
        for stmt in _OLD_SCHEMA_DDL:
            try:
                db.session.execute(text(stmt))
            except Exception:
                db.session.rollback()
        db.session.commit()

    # Sanity: the old schema really is missing the new columns.
    with app.app_context():
        cols = {r[0] for r in db.session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='user'"))}
        assert "email_verified" not in cols

    # Boot 2: the ensure must repair the schema during create_app.
    app2 = _make_app(pg_uri)
    client = app2.test_client()
    r = _register(client)
    assert r.status_code == 302, f"register after repair: {r.status_code}"
    r = _login(client)
    assert r.status_code == 302, f"login after repair: {r.status_code}"

    # Quiz flow (the user-visible breakage) works end to end.
    r = client.get("/learn/quizzes")
    assert r.status_code == 200
    from studybuddy.skill_quizzes import quiz_skills
    skill = quiz_skills()[0][0]
    r = client.post("/learn/quizzes/start",
                    json={"skill": skill, "num_questions": 5,
                          "difficulties": [], "timed": False})
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    assert len(r.get_json()["questions"]) == 5

    # BYOK table (user_api_key) exists and the page loads.
    r = client.get("/profile/ai-key")
    assert r.status_code in (200, 302)


def test_boot_is_idempotent(pg_uri):
    app1 = _make_app(pg_uri)
    assert _register(app1.test_client()).status_code == 302
    # Second and third boots against the repaired schema: no error, no dupes.
    for _ in range(2):
        app = _make_app(pg_uri)
        client = app.test_client()
        assert _login(client).status_code == 302
        with app.app_context():
            n = db.session.execute(text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name='user' AND column_name='email_verified'"
            )).scalar()
            assert n == 1


def test_schema_ensure_never_drops_data(pg_uri):
    app = _make_app(pg_uri)
    client = app.test_client()
    assert _register(client).status_code == 302
    # Roll back schema, boot again (repair), user row must survive.
    with app.app_context():
        for stmt in _OLD_SCHEMA_DDL[:2]:  # drop only the user columns
            db.session.execute(text(stmt))
        db.session.commit()
    app2 = _make_app(pg_uri)
    with app2.app_context():
        from unified_app import User
        u = User.query.filter_by(email="ensure@example.com").first()
        assert u is not None, "existing user lost during schema repair"
        assert u.email_verified is False  # backfilled with safe default
