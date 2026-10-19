# ARC-11: Background jobs

## The problem

Two bad patterns existed:

1. **Request-triggered daemon thread for data refresh.** `studybuddy/opportunities.py::_maybe_trigger_refresh()` spawns a `threading.Thread(target=refresh_opportunities, daemon=True)` from inside request handling whenever the opportunities data looks stale, rewriting `data/opportunities.json` on the **ephemeral** filesystem (lost on restart/redeploy; on a spun-down free Render instance it rarely runs at all).
2. **Heavy work inline in requests.** PDF parsing / embedding batches run synchronously in the request cycle.

## What changed

### 1. Bounded job pool — `studybuddy/jobs.py` (new)

A process-wide `JobManager` backed by a **bounded** `ThreadPoolExecutor`
(`MAX_WORKERS = 2`, tuned for the Render free tier):

```python
from studybuddy.jobs import submit_job, job_status

job_id = submit_job(parse_and_index_pdf, pdf_bytes, name="pdf-index")
# ...later, poll:
info = job_status(job_id)
# {"job_id": ..., "name": ..., "state": "pending|running|done|error",
#  "result": ..., "error": ...}
```

* `submit(fn, *args, **kwargs) -> job_id` — never raises for queue-full (the pool is bounded; excess work queues behind the 2 workers instead of spawning threads).
* `status(job_id)` — polling dict with `pending / running / done / error` + `result` / `error`. Unknown ids raise `KeyError` (map to HTTP 404).
* Results are stored in a bounded FIFO dict (`MAX_JOBS_KEPT = 500`) — no unbounded memory growth in a long-lived process.
* The singleton is created **lazily** (`get_job_manager()`), so importing the module never starts threads — important under gunicorn, where each forked worker gets its own manager.
* Errors are recorded as `"Type: message"` strings, never exception objects (no frame/payload leaks).

When the app moves to a paid always-on tier, swap this for a real queue
(RQ/Arq + Redis); the `submit`/`status` contract stays the same.

### 2. Suggested route wiring (NOT applied — needs a unified_app.py edit)

```python
from studybuddy.jobs import job_status, submit_job

@app.post("/api/jobs/pdf-index")
@login_required
def api_pdf_index():
    job_id = submit_job(index_pdf_for_qa, request.files["pdf"].read(),
                        name="pdf-index")
    return jsonify({"job_id": job_id}), 202

@app.get("/api/jobs/<job_id>")
@login_required
def api_job_status(job_id):
    try:
        return jsonify(job_status(job_id))
    except KeyError:
        abort(404)
```

The UI polls `GET /api/jobs/<id>` until `state` is `done`/`error` (ARC-11 acceptance: UI shows job status via polling).

### 3. Data refresh moved to CI — `.github/workflows/data-refresh.yml` (new)

Weekly cron (Mondays 02:00 UTC) that:

1. runs `scripts/build_opportunities.py --prune --write` (dedupe, expire past deadlines, prune) and `scripts/build_skills_taxonomy.py`,
2. validates with `scripts/validate_data.py --strict` (DATA-01 schemas + freshness),
3. link-checks with `scripts/check_links.py`,
4. opens a PR via `peter-evans/create-pull-request` (`chore/weekly-data-refresh`).

Datasets become **versioned, reviewable, and deployed with the app**.

### 4. Thread to REMOVE (reported, not removed)

`studybuddy/opportunities.py::_maybe_trigger_refresh()` (line ~175):

```python
t = threading.Thread(target=refresh_opportunities,
                     name="opp-refresh", daemon=True)
t.start()
```

This is the request-triggered daemon thread ARC-11 calls out. It should be
deleted once the weekly CI refresh is confirmed producing PRs — the
`OPP_NO_AUTO_REFRESH=1` escape hatch already exists for tests/operators, so
removal is a pure deletion with no behavior to preserve. **Deliberately left
in place by WS4-ARCBIG** (task rule: remove no existing threads; report only).

After removal, also delete the now-dead `_take_refresh_lock()` /
`_refresh_already_running()` helpers and the `data/.refresh_lock` artifact.
