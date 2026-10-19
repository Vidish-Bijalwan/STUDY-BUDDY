"""TEST-13: API contract tests v1 (no schemathesis yet).

Contract source: docs/api/openapi.yaml (hand-written, honest).
This test asserts:
  1. the spec is well-formed and covers every /api/* route in
     tests/route_policy.yaml (no undocumented endpoints),
  2. every documented path+method exists in app.url_map,
  3. public endpoints return the documented top-level JSON keys,
  4. auth endpoints return 401/403 + {"error": str} when unauthenticated,
  5. the {"error": ...} envelope matches studybuddy/exceptions.py
     (user_message + status_code per subclass).

LLM/network-backed success bodies are documented from code only
(x-success-shape: from-code-only) and are NOT asserted here —
follow-up: schemathesis fuzzing against the spec.
"""
from pathlib import Path

import re

import yaml

from studybuddy import exceptions as exc

SPEC_PATH = Path(__file__).resolve().parent.parent / "docs" / "api" / "openapi.yaml"
POLICY_PATH = Path(__file__).resolve().parent / "route_policy.yaml"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

# Example concrete URLs for templated public paths.
EXAMPLE_URLS = {
    "/api/coding-practice/{company}": "/api/coding-practice/google",
    "/api/interview-questions/{company}": "/api/interview-questions/google",
    "/api/cite/guide/{style}": "/api/cite/guide/apa",
}

# Public POST probes: (url, json_body, expected_status, expected_keys).
# expected_status may be 200 (success shape) or 400 (error envelope).
PUBLIC_POST_PROBES = {
    "/api/parse_preview": ("/api/parse_preview", {}, 400, ["error"]),
    "/api/cite/format": ("/api/cite/format", {}, 400, ["error"]),
    "/api/cite/bibtex/export": (
        "/api/cite/bibtex/export", {"meta": {}}, 200, ["bibtex"]),
    "/api/cite/bibtex/import": (
        "/api/cite/bibtex/import", {}, 400, ["error"]),
    "/api/eng/jd-v2/match": (
        "/api/eng/jd-v2/match",
        {"jd_text": "Python developer needed. " * 10,
         "resume_text": "Python dev 3 years",
         "resume_skills": ["python"], "resume_years": 3,
         "resume_education": []},
        200, ["score"]),
    "/api/eng/jobs/recommend": (
        "/api/eng/jobs/recommend",
        {"cards": [], "resume_skills": ["python"], "resume_years": 3},
        200, []),
    "/api/eng/jobs/paste-jd": (
        "/api/eng/jobs/paste-jd",
        {"jd_text": "Python developer needed. " * 10, "title": "Test Role"},
        200, ["title"]),
    "/api/eng/interview/score-v2": (
        "/api/eng/interview/score-v2",
        {"question": "Tell me about yourself",
         "answer": "I am a developer with three years of Python experience",
         "key_points": ["communication"]},
        200, ["score", "rubric", "improvements"]),
}


def _spec():
    assert SPEC_PATH.exists(), "docs/api/openapi.yaml missing"
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    assert spec.get("openapi", "").startswith("3.")
    assert spec.get("paths"), "spec has no paths"
    return spec


def _operations(spec):
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method in HTTP_METHODS:
                yield path, method, op


def test_spec_well_formed():
    spec = _spec()
    ops = list(_operations(spec))
    assert len(spec["paths"]) == 24, \
        f"expected 24 /api/* paths, got {len(spec['paths'])}"
    for path, method, op in ops:
        assert path.startswith("/api/"), path
        assert op.get("x-flask-path"), f"{method} {path}: missing x-flask-path"
        assert op.get("x-auth") in ("public", "auth"), \
            f"{method} {path}: missing/invalid x-auth"
        assert isinstance(op.get("x-response-keys"), list), \
            f"{method} {path}: missing x-response-keys"


def _flask_to_openapi(path):
    """Convert Flask <converter:name>/<>name> templates to OpenAPI {name}."""
    return re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", path)


def test_spec_covers_route_policy():
    """No /api/* route in route_policy.yaml may go undocumented."""
    spec = _spec()
    with open(POLICY_PATH, encoding="utf-8") as f:
        policy = yaml.safe_load(f)
    policy_apis = {_flask_to_openapi(k) for k in policy
                   if k.startswith("/api/")}
    assert policy_apis, "no /api/* entries in route_policy.yaml"
    assert policy_apis == set(spec["paths"]), \
        f"spec/policy mismatch: {policy_apis ^ set(spec['paths'])}"


def test_documented_endpoints_exist(app):
    """Every spec path+method is registered in the Flask app."""
    spec = _spec()
    rules = {(str(r.rule), m)
             for r in app.url_map.iter_rules()
             for m in (r.methods or set()) - {"HEAD", "OPTIONS"}}
    missing = []
    for _path, method, op in _operations(spec):
        if (op["x-flask-path"], method.upper()) not in rules:
            missing.append(f"{method.upper()} {op['x-flask-path']}")
    assert not missing, f"documented but not routed: {missing}"


def test_public_get_response_shapes(client):
    spec = _spec()
    for path, method, op in _operations(spec):
        if method != "get" or op["x-auth"] != "public":
            continue
        url = EXAMPLE_URLS.get(path, path)
        r = client.get(url)
        assert r.status_code == 200, f"GET {url} -> {r.status_code}"
        assert r.is_json, f"GET {url} did not return JSON"
        body = r.get_json()
        expected = op["x-response-keys"]
        if expected:
            assert isinstance(body, dict), f"GET {url}: expected object"
            assert set(expected) <= set(body), \
                f"GET {url}: keys {sorted(body)} missing {expected}"
        else:
            assert isinstance(body, list), f"GET {url}: expected array"


def test_public_post_shapes(client):
    spec = _spec()
    documented = {p for p, m, op in _operations(spec)
                  if m == "post" and op["x-auth"] == "public"}
    assert set(PUBLIC_POST_PROBES) == documented, \
        f"probe/spec mismatch: {set(PUBLIC_POST_PROBES) ^ documented}"
    for _path, (url, body, status, keys) in PUBLIC_POST_PROBES.items():
        r = client.post(url, json=body)
        assert r.status_code == status, \
            f"POST {url} -> {r.status_code}, expected {status}: " \
            f"{r.get_data(as_text=True)[:120]}"
        assert r.is_json, f"POST {url} did not return JSON"
        payload = r.get_json()
        if isinstance(payload, list):
            assert isinstance(keys, list), f"POST {url}: list response"
            # list responses: keys must be empty (nothing to check per-item here)
            assert keys == [], f"POST {url}: list response with keys {keys}"
        else:
            assert set(keys) <= set(payload), \
                f"POST {url}: keys {sorted(payload)} missing {keys}"
        if "error" in keys:
            assert isinstance(payload["error"], str) and payload["error"]


def test_auth_endpoints_reject_anonymous(client):
    """Unauthenticated calls to auth endpoints: 401/403 + error envelope."""
    spec = _spec()
    for path, method, op in _operations(spec):
        if op["x-auth"] != "auth":
            continue
        url = EXAMPLE_URLS.get(path, path)
        if "{openalex_id}" in url:
            url = url.replace("{openalex_id}", "W123")
        if "{tool_id}" in url:
            url = url.replace("{tool_id}", "some-tool")
        if method == "get":
            r = client.get(url)
        else:
            r = client.post(url, json={})
        assert r.status_code in (401, 403), \
            f"{method.upper()} {url} anonymous -> {r.status_code}, " \
            f"expected 401/403"
        assert r.is_json, f"{method.upper()} {url} error was not JSON"
        payload = r.get_json()
        assert isinstance(payload.get("error"), str) and payload["error"], \
            f"{method.upper()} {url}: error envelope broken: {payload}"


def test_error_envelope_matches_exceptions(app):
    """handle_studybuddy_error returns {"error": user_message} + status."""
    subclasses = [
        exc.ValidationError, exc.ExternalServiceError, exc.QuotaExceeded,
        exc.NotFoundError, exc.AuthRequiredError,
    ]
    assert len(subclasses) == 5
    with app.test_request_context("/api/probe"):
        for cls in subclasses:
            err = cls()
            assert isinstance(err.user_message, str) and err.user_message
            assert isinstance(err.status_code, int)
            resp, status = exc.handle_studybuddy_error(err)
            assert status == err.status_code
            payload = resp.get_json()
            assert payload == {"error": err.user_message}, \
                f"{cls.__name__}: envelope {payload}"


def test_authed_success_shapes(client):
    """Spot-check success shapes behind login (local, no network)."""
    import uuid
    email = f"contract-{uuid.uuid4().hex[:8]}@example.com"
    client.post("/register", data={
        "name": "Contract", "email": email,
        "password": "<redacted>", "age_confirm": "1",
    }, follow_redirects=False)
    client.post("/login", data={"email": email, "password": "<redacted>"},
                follow_redirects=False)

    r = client.post("/api/cite/format", json={
        "meta": {"title": "T", "author": "A", "year": "2020"}, "style": "apa"})
    assert r.status_code == 200
    assert set(["citation", "style"]) <= set(r.get_json())

    r = client.get("/api/ultimate/tools")
    assert r.status_code == 200
    assert set(["ok", "count", "tools"]) <= set(r.get_json())

    # Empty chat message -> 400 error envelope (no LLM call made).
    r = client.post("/api/chat_research", json={"message": ""})
    assert r.status_code == 400
    assert isinstance(r.get_json().get("error"), str)
