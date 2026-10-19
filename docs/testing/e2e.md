# TEST-07: End-to-end browser tests

## What runs

`tests/e2e/test_smoke.py` — Playwright (Python) + real Chromium against a
real local instance (`tests/e2e/conftest.py::live_server`: `create_app`
with a temp SQLite DB, served by werkzeug in a background thread).

Journeys:
1. **signup → upload resume → readiness report** — fills the real
   `/register` form, uploads a generated PDF on `/resume`, clicks
   analyze, follows the JS redirect to `/results/<id>`, asserts the
   ATS/readiness report rendered.
2. **tracker add → move** — adds a job application via the page's own
   session, moves it `wishlist → applied`, asserts the board reflects it.
3. **delete account** — password re-auth + `DELETE` confirmation, asserts
   logout and that protected pages bounce to `/login`.

## Run locally

```bash
.venv/bin/python -m playwright install chromium --with-deps  # once
.venv/bin/python -m pytest tests/e2e/ -p no:cacheprovider -v
```

## CI

`.github/workflows/e2e.yml` — installs Chromium, runs `tests/e2e/`,
uploads `/tmp/e2e-fail-*.png` screenshots as artifacts on failure
(the autouse `_screenshots_on_failure` fixture in
`tests/e2e/conftest.py` saves them).

## Skip behavior (graceful)

- `pytest.importorskip("playwright")` at the top of each e2e module:
  no Playwright installed → whole module skips.
- `browser_ctx` fixture: if Chromium can't launch (no browsers, sandbox
  blocked), tests **skip** with the reason, they don't fail.
- A skip is a signal, not a pass — CI installs the browsers precisely
  so the e2e job actually runs.

## Honest status (2026-10-19)

All 3 smoke tests pass locally against the real app (~17s). Not yet
run in CI — the first `e2e.yml` run is the real proof.
