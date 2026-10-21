"""Regression tests for the public no-signup demo at /try.

The demo broke silently in production: the page's fetch sent no CSRF
token (production /analyze rejected it with a 400 HTML page), the
offered sample was a .txt the analyzer rejects, and the success path
dumped raw JSON instead of opening the report. These tests exercise
the demo exactly as a visitor's browser drives it — CSRF enabled.
"""
import io
import os
import re

import pytest

from unified_app import create_app

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")


@pytest.fixture()
def csrf_app():
    return create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": True,  # production condition — the point here
        "RATELIMIT_ENABLED": False,
    })


@pytest.fixture()
def csrf_client(csrf_app):
    return csrf_app.test_client()


def _demo_token(client):
    html = client.get("/try").get_data(as_text=True)
    m = re.search(r'name="csrf-token" content="([^"]+)"', html)
    assert m, "/try must expose a csrf-token meta for its fetch call"
    return m.group(1)


def test_try_page_wires_the_demo_correctly(csrf_client):
    html = csrf_client.get("/try").get_data(as_text=True)
    assert 'name="csrf-token"' in html
    assert "sample_resume.docx" in html
    assert "sample_resume.txt" not in html
    assert "github.com/Vivek492005/STUDY-BUDDY" in html


def test_demo_flow_end_to_end_with_csrf(csrf_client):
    token = _demo_token(csrf_client)
    with open(os.path.join(STATIC, "sample_resume.docx"), "rb") as f:
        payload = f.read()
    r = csrf_client.post(
        "/analyze",
        data={"resume": (io.BytesIO(payload), "sample_resume.docx")},
        headers={"Accept": "application/json", "X-CSRFToken": token},
    )
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    body = r.get_json()
    assert body["success"] is True
    assert body["redirect"].startswith("/results/")
    report = csrf_client.get(body["redirect"])
    assert report.status_code == 200
    assert "score" in report.get_data(as_text=True).lower()


def test_analyze_without_csrf_token_is_rejected(csrf_client):
    with open(os.path.join(STATIC, "sample_resume.docx"), "rb") as f:
        payload = f.read()
    r = csrf_client.post(
        "/analyze",
        data={"resume": (io.BytesIO(payload), "sample_resume.docx")},
        headers={"Accept": "application/json"},
    )
    assert r.status_code == 400


def test_sample_resume_docx_is_a_real_resume():
    import docx

    doc = docx.Document(os.path.join(STATIC, "sample_resume.docx"))
    text = "\n".join(p.text for p in doc.paragraphs)
    for section in ("Skills", "Experience", "Projects", "Education"):
        assert section in text


def test_social_meta_tags_render(csrf_client):
    home = csrf_client.get("/").get_data(as_text=True)
    assert 'property="og:image"' in home
    assert "social-preview.png" in home
    assert 'name="twitter:card" content="summary_large_image"' in home
    inner = csrf_client.get("/try").get_data(as_text=True)
    assert 'property="og:image"' in inner
    assert 'name="description"' in inner
