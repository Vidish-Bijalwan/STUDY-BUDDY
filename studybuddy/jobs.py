"""Bounded background job system — ARC-11.

Heavy request work (PDF parsing, embedding batches, LLM batches) should not
block the request/response cycle and must not spawn unbounded threads. This
module provides a single process-wide :class:`JobManager` backed by a bounded
:class:`~concurrent.futures.ThreadPoolExecutor`:

* :meth:`JobManager.submit` -> ``job_id`` (UUID hex)
* :meth:`JobManager.status` -> dict with ``state`` (``pending`` | ``running`` |
  ``done`` | ``error``), plus ``result`` / ``error`` when finished
* :meth:`JobManager.result` -> convenience accessor (raises KeyError/pending)

Jobs are in-memory (MVP per ARC-11: bounded executor now, real queue like RQ
with Redis when moving to a paid always-on tier). Results are kept in a
bounded dict (default 500 entries, FIFO eviction) so a long-lived process
cannot leak memory.

Thread-safety: all state mutations happen under a lock; the worker callback
records outcome via ``Future.add_done_callback``.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# ARC-11: hard bound on concurrent heavy work. Two workers is plenty for the
# Render free tier (512MB); raise when moving to a bigger instance.
MAX_WORKERS = 2
MAX_JOBS_KEPT = 500

PENDING = "pending"
RUNNING = "running"
DONE = "done"
ERROR = "error"


@dataclass
class Job:
    """One background job's observable state."""

    job_id: str
    name: str
    state: str = PENDING
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    """Bounded executor + job registry. Create ONE per process."""

    def __init__(self, max_workers: int = MAX_WORKERS,
                 max_jobs_kept: int = MAX_JOBS_KEPT) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="sb-job"
        )
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs_kept = max_jobs_kept

    # -- submission -----------------------------------------------------
    def submit(self, fn: Callable[..., Any], *args: Any,
               name: Optional[str] = None, **kwargs: Any) -> str:
        """Enqueue ``fn(*args, **kwargs)``; returns the job id."""
        job = Job(job_id=uuid.uuid4().hex,
                  name=name or getattr(fn, "__name__", "job"))
        # Register BEFORE submitting: a fast task could otherwise finish
        # before the job is in the dict and its outcome would be dropped.
        with self._lock:
            self._jobs[job.job_id] = job
            while len(self._jobs) > self._max_jobs_kept:
                self._jobs.popitem(last=False)  # FIFO eviction
        future: Future = self._executor.submit(self._run_wrapped, job, fn,
                                               args, kwargs)
        future.add_done_callback(lambda f, j=job: self._record(j, f))
        return job.job_id

    @staticmethod
    def _run_wrapped(job: Job, fn: Callable, args: tuple,
                     kwargs: dict) -> Any:
        job.state = RUNNING
        job.started_at = time.time()
        return fn(*args, **kwargs)

    def _record(self, job: Job, future: Future) -> None:
        with self._lock:
            if job.job_id not in self._jobs:
                return  # evicted while running; nothing to record into
            job.finished_at = time.time()
            exc = future.exception()
            if exc is not None:
                job.state = ERROR
                # Never store the exception object (may hold frames/payloads);
                # store a short, PII-free summary instead.
                job.error = f"{type(exc).__name__}: {str(exc)[:500]}"
            else:
                job.state = DONE
                job.result = future.result()

    # -- polling --------------------------------------------------------
    def status(self, job_id: str) -> dict:
        """Current status dict for ``job_id`` (KeyError when unknown)."""
        with self._lock:
            job = self._jobs[job_id]  # raises KeyError — caller maps to 404
            return job.as_dict()

    def result(self, job_id: str) -> Any:
        """Return the result, or raise a descriptive error."""
        info = self.status(job_id)
        if info["state"] == PENDING or info["state"] == RUNNING:
            raise RuntimeError(f"Job {job_id} is not finished yet.")
        if info["state"] == ERROR:
            raise RuntimeError(f"Job {job_id} failed: {info['error']}")
        return info["result"]

    def list_jobs(self, limit: int = 50) -> list[dict]:
        """Newest-first status dicts (for admin/debug views)."""
        with self._lock:
            jobs = list(self._jobs.values())
        return [j.as_dict() for j in reversed(jobs[-limit:])]

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


# Process-wide singleton, created lazily so importing this module never
# starts threads (gunicorn forks workers; each worker gets its own).
_manager: Optional[JobManager] = None
_manager_lock = threading.Lock()


def get_job_manager() -> JobManager:
    """Return the process-wide job manager (creates it on first use)."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = JobManager()
    return _manager


def submit_job(fn: Callable[..., Any], *args: Any,
               name: Optional[str] = None, **kwargs: Any) -> str:
    """Submit heavy work to the shared bounded pool. Returns job_id."""
    return get_job_manager().submit(fn, *args, name=name, **kwargs)


def job_status(job_id: str) -> dict:
    """Poll a job's status dict (KeyError -> unknown id)."""
    return get_job_manager().status(job_id)


__all__ = [
    "DONE",
    "ERROR",
    "PENDING",
    "RUNNING",
    "MAX_WORKERS",
    "Job",
    "JobManager",
    "get_job_manager",
    "job_status",
    "submit_job",
]
