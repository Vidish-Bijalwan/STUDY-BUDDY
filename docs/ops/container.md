# OPS-04: Containerization — verification report (2026-10-19)

`Dockerfile` and `docker-compose.yml` already exist in the repo root. Verified against the roadmap's OPS-04 checklist:

| Requirement | Status |
|---|---|
| Multi-stage Dockerfile | **Gap — single stage.** Current file is `python:3.12-slim` in one stage. Works, but build tools/cache are not a problem here since apt only installs `curl`. Recommendation: split into builder + runtime stages when the dependency list grows native extensions. |
| Slim base | ✅ `python:3.12-slim` |
| Non-root user | ✅ `appuser`, `USER appuser` |
| No build tools in final image | ✅ (only `curl` for HEALTHCHECK) |
| HEALTHCHECK | ✅ `curl -f http://localhost:5000/healthz`, 30s interval |
| Hash-pinned deps | ✅ `--require-hashes -r requirements.txt` |
| `.dockerignore` | **Gap — was missing, ADDED 2026-10-19.** Without it, `.venv/`, `instance/`, `uploads/`, `.env`, `.git/` all entered the build context (slow builds, secret-leak risk). |
| compose: app + Postgres + Redis + Ollama | ⚠️ Partial — app + optional Ollama + optional Postgres profiles exist; **Redis service missing**. Add a `redis:` service when rate-limit/queue work needs it. |
| `.devcontainer/` | **Gap — missing.** Add when a contributor asks for Codespaces. |
| `make dev` | **Gap — no Makefile.** `docker compose up` is the documented equivalent today. |

## Local dev parity

```bash
docker compose up            # app + sqlite, LLM_MODE=off, no keys needed
docker compose --profile ollama up     # + local LLM
docker compose --profile postgres up   # + Postgres instead of sqlite
```

## Follow-ups (not done in WS6)

1. Multi-stage Dockerfile (builder/runtime split).
2. Redis service in compose when queue work lands.
3. `.devcontainer/devcontainer.json` for Codespaces.
4. `Makefile` with `dev`, `test`, `lint` targets.
5. Dockerfile CMD still uses inline gunicorn flags (`--workers 2 --timeout 120`) — should switch to `-c gunicorn.conf.py` (see docs/ops/memory.md).
