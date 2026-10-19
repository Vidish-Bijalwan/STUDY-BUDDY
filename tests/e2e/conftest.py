"""TEST-07: shared fixtures for Playwright end-to-end tests.

Runs the real Flask app (create_app) on a local port in a background
thread against a temp SQLite DB, then drives it with a real Chromium.

If Playwright browsers cannot launch in an environment, tests SKIP
gracefully (documented in docs/testing/e2e.md).
"""
import os
import tempfile
import threading
import uuid

import pytest

playwright_mod = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_mod.sync_playwright

os.environ.setdefault("OPP_NO_AUTO_REFRESH", "1")
# In-process parsing (no sandbox subprocess) keeps the upload journey fast.
os.environ["STUDYBUDDY_NO_PARSE_SANDBOX"] = "1"

from unified_app import create_app  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def _make_resume_pdf_bytes():
    """Minimal valid single-page PDF resume (no network, no fixtures)."""
    lines = [
        "Aarav Sharma",
        "aarav.sharma@example.com | +91-9876543210",
        "SUMMARY",
        "Computer Science undergraduate with strong Python and machine learning skills.",
        "EDUCATION",
        "B.Tech Computer Science, Graphic Era Hill University, 2023 - 2027",
        "EXPERIENCE",
        "Machine Learning Intern, 6 months building Flask APIs and data pipelines.",
        "SKILLS",
        "Python, Java, SQL, Machine Learning, Flask, Git, Data Analysis, HTML, CSS, JavaScript",
        "PROJECTS",
        "Built a resume analyzer web app with Flask and NLP.",
    ]
    content = b"BT /F1 12 Tf 72 740 Td 14 TL\n"
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content += b"(" + safe.encode("latin-1", "ignore") + b") Tj T*\n"
    content += b"ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objects) + 1)
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1, xref_pos)
    return pdf


@pytest.fixture(scope="module")
def live_server():
    """Real app on a real port with a temp SQLite DB + upload dir."""
    tmp = tempfile.mkdtemp(prefix="sb-e2e-")
    db_path = os.path.join(tmp, "e2e.db")
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "SECRET_KEY": "e2e-test-secret-key",
        "WTF_CSRF_ENABLED": False,
        "UPLOAD_FOLDER": tmp,
    })
    server = make_server("127.0.0.1", 0, app)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser_ctx():
    """Chromium browser; skips cleanly if browsers can't launch."""
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:  # browsers missing / sandbox blocked
        pytest.skip(f"Playwright browser unavailable: {exc}")
    yield pw, browser
    browser.close()
    pw.stop()


@pytest.fixture()
def page(browser_ctx, live_server):
    _, browser = browser_ctx
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.set_default_timeout(30000)
    yield pg
    ctx.close()


def unique_email(prefix="e2e"):
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)


@pytest.fixture(autouse=True)
def _screenshots_on_failure(request, page):
    """Save a screenshot artifact when an e2e test fails."""
    yield
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        shot = os.path.join(tempfile.gettempdir(),
                            f"e2e-fail-{request.node.name}.png")
        try:
            page.screenshot(path=shot)
            print(f"\n[e2e] failure screenshot: {shot}")
        except Exception:
            pass


def signup(page, base, name="E2E User", email=None, password="<redacted>"):
    """Drive the real /register form; returns the email used."""
    email = email or unique_email()
    page.goto(f"{base}/register")
    page.fill("#name", name)
    page.fill("#email", email)
    page.fill("#password", password)
    page.check('input[name="age_confirm"]')
    page.click('button[type="submit"]')
    page.wait_for_url("**/dashboard**", timeout=15000)
    return email
