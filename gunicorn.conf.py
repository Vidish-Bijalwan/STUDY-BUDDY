# OPS-09: Gunicorn config for the 512 MB free tier.
#
# Memory discipline: ONE sync worker process (Python's GIL makes threads the
# right concurrency model for an I/O-bound Flask app). Four gthread threads
# handle concurrent uploads while keeping RSS around ~130 MB (measured on
# 2026-10-19: 127 MB peak boot + /healthz + /readyz + /version).
#
# Start with:  gunicorn -c gunicorn.conf.py unified_app:app
# Render:      change render.yaml startCommand to
#              "gunicorn -c gunicorn.conf.py unified_app:app"
#              (render.yaml NOT edited here — see docs/ops/memory.md)
import os
import multiprocessing  # noqa: F401  (kept for the commented formula below)

# --- workers ---------------------------------------------------------------
workers = 1
worker_class = "gthread"
threads = 4
# If we ever leave the free tier: workers = 2 * cpu + 1 is for CPU-bound
# workloads; for this I/O-bound app prefer workers=1..2 + more threads.

# --- timeouts ----------------------------------------------------------------
timeout = 60            # kill a hung worker after 60s (long jobs go to bg)
graceful_timeout = 30   # give in-flight requests 30s on SIGTERM

# --- memory hygiene ------------------------------------------------------------
max_requests = 1000        # recycle each worker every 1000 requests...
max_requests_jitter = 100  # ...with +/-100 jitter so workers don't all restart
# NOTE: preload_app intentionally OFF — thread-safety of every module
# (caches, singletons) must be audited before enabling (OPS-09 roadmap).

# --- binding / logging -----------------------------------------------------------
bind = "0.0.0.0:" + os.environ.get("PORT", "5000")
accesslog = "-"   # stdout -> Render log stream
errorlog = "-"
loglevel = "info"
