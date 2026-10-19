# TEST-09: Load and soak testing

Scenario: `locustfile.py` (repo root) — ~50 concurrent users browsing
(public pages + public JSON APIs) plus ~10 uploading resumes
(authenticated, `/api/parse_preview`).

## Quick smoke (30s, local)

```bash
# terminal 1: app with the production-ish worker config
gunicorn --bind 127.0.0.1:5000 --workers 2 --timeout 60 \
  "unified_app:create_app()"

# terminal 2: 30-second smoke
.venv/bin/locust -f locustfile.py --headless -u 5 -r 2 -t 30s \
  --host http://127.0.0.1:5000 --csv /tmp/locust-smoke
```

Expected: 0 unexpected failures (HTTP 429 on the upload endpoint under
burst is *expected* — the scenario treats it as success).

## Full soak (10 min, staging)

Run against a staging instance with the **production worker config**
(same gunicorn workers/timeout as `render.yaml`):

```bash
.venv/bin/locust -f locustfile.py --headless -u 60 -r 5 -t 10m \
  --host https://staging.example.com --csv /tmp/locust-soak
```

Record from the run: p50/p95/p99 latency (from the `--csv` stats),
error rate, and worker RSS (below).

## 400 MB RSS budget — assertion approach

Locust does not track server memory. Measure the gunicorn workers
directly during the soak with a sampler:

```bash
# terminal 3, during the soak: sample worker RSS every 5s
python3 - <<'EOF'
import subprocess, time
peak = 0
samples = []
end = time.time() + 600
while time.time() < end:
    out = subprocess.run(
        ["ps", "-C", "gunicorn", "-o", "rss=", "--no-headers"],
        capture_output=True, text=True).stdout
    rss_mb = sum(int(x) for x in out.split()) / 1024
    peak = max(peak, rss_mb)
    samples.append(rss_mb)
    time.sleep(5)
print(f"peak worker RSS: {peak:.0f} MB")
assert peak < 400, f"RSS budget exceeded: {peak:.0f} MB >= 400 MB"
EOF
```

Budget: **total gunicorn worker RSS must stay under 400 MB** on the
512 MB tier (roadmap TEST-09). If it leaks, `max_requests` with jitter
is an acceptable *mitigation* — the leak itself must still be fixed.

## Honest status

- The 30s smoke config and scenario wiring are validated by
  `tests/test_ws5_load_smoke.py` (AST checks + PDF helper round-trip).
- **No 10-minute soak has been run yet** — it needs a staging instance
  with the production worker config. The first soak establishes the
  real p50/p95/p99 and RSS baseline; record the numbers here.
- `import locust` inside the pytest process hits a gevent/ssl
  RecursionError on Python 3.12, so the smoke test probes locust in an
  isolated subprocess instead of importing it in-process.
