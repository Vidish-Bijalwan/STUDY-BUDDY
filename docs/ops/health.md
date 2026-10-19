# OPS-05: Health, readiness, and version endpoints

All three endpoints exist in `unified_app.py` (verified 2026-10-19, lines ~2809–2880). `unified_app.py` was **not** edited by WS6 — this doc records the verified behavior and the recommended additions.

## Verified (live code)

| Endpoint | Behavior |
|---|---|
| `GET /healthz` | Liveness: returns `{"status": "ok"}`. **Touches no DB** (0 SQL statements — enforced by `test_healthz_statement_budget`, PERF-02). Render `healthCheckPath` points here. |
| `GET /readyz` | Readiness: checks (1) DB reachable (`SELECT 1`), (2) Alembic migrations at head, (3) required config present. Returns per-check map + 200/503. Never exposes secrets — errors are reported as `error: <ExceptionType>`, never messages or DSNs. Statement budget ≤ 20 (PERF-02). |
| `GET /version` | Build metadata: `app_version` ("1.0.0"), git SHA (short), schema revision (alembic heads), `data_versions`. No secrets. Statement budget ≤ 20. |

## Monitoring wiring

- **Render:** `healthCheckPath: /healthz` (already in `render.yaml`).
- **Uptime monitor / status page:** poll `/readyz` (it reflects "can serve traffic"), alert on non-200.
- **Deploy verification:** after every deploy, `curl /version` and confirm the SHA matches the release tag (OPS-07).

## REPORTED — recommended additions (not applied; needs unified_app.py edit)

The roadmap asks `/version` to carry **build time** and fuller **data versions**. Suggested fields to add inside the existing `version()` return dict:

```python
return jsonify({
    # ... existing fields ...
    "build_time": os.environ.get("BUILD_TIME", "unknown"),  # set at build: BUILD_TIME=$(date -u +%FT%TZ)
    "python": platform.python_version(),
    "data_versions": {
        "skills_taxonomy": "2026-10-19",   # bump when data/ changes
        "opportunities": "2026-10-19",
    },
})
```

And for `/readyz`, add an explicit `config` check already present in code — verified it checks required config; if it ever only checks DB+migrations, add:

```python
checks["config"] = "ok" if app.config.get("SECRET_KEY") else "missing SECRET_KEY"
```
