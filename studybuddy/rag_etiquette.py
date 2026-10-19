"""RAG-06: research data-source etiquette and safety.

Shared plumbing for polite access to arXiv, OpenAlex, Crossref and
Semantic Scholar:

- a shared :class:`requests.Session` with a descriptive ``User-Agent``
  carrying a contact email (``RESEARCH_CONTACT_EMAIL`` env, with a sane
  default)
- per-host rate limiting (arXiv: at most 1 request per 3 seconds, per
  their published guidance; gentler defaults for the others)
- ETag / Last-Modified conditional caching (file-backed, 24h default TTL)
- ``defusedxml`` parsing for all XML (SEC-10)
- graceful degradation: every public helper returns ``{"ok": ...}``
  result dicts with clear, user-facing messages instead of raising
- :func:`stamp_record` attaches ``retrieved_at`` + ``source`` provenance
  to imported records

Pure stdlib + ``requests`` + ``defusedxml``. No Flask.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import defusedxml.ElementTree as ET
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Identity: descriptive User-Agent with contact email
# ---------------------------------------------------------------------------

#: Contact email for the User-Agent "mailto:" token. Operators of arXiv /
#: OpenAlex / Crossref ask for a way to reach API users.
CONTACT_EMAIL = os.environ.get(
    "RESEARCH_CONTACT_EMAIL", "research@student.local").strip()


def user_agent() -> str:
    """Descriptive User-Agent identifying this app + a contact email."""
    return (
        "StudyBuddy-ResearchAssistant/1.0 "
        "(mailto:%s; educational research assistant; "
        "+https://github.com/Vivek492005/Sunday)" % CONTACT_EMAIL
    )


# ---------------------------------------------------------------------------
# 2. Shared session
# ---------------------------------------------------------------------------

_SESSION: requests.Session | None = None
_SESSION_LOCK = threading.Lock()


def get_session() -> requests.Session:
    """Return the shared polite session (created once, thread-safe)."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            sess = requests.Session()
            sess.headers.update({
                "User-Agent": user_agent(),
                "Accept": "application/json, application/xml;q=0.9",
            })
            _SESSION = sess
        return _SESSION


# ---------------------------------------------------------------------------
# 3. Per-host rate limiting
# ---------------------------------------------------------------------------

#: Minimum seconds between requests, per host. arXiv's guidance: no more
#: than one request every 3 seconds.
HOST_INTERVALS: dict[str, float] = {
    "export.arxiv.org": 3.0,
    "arxiv.org": 3.0,
    "api.openalex.org": 1.0,
    "api.crossref.org": 1.0,
    "api.semanticscholar.org": 1.0,
}
DEFAULT_INTERVAL = 1.0


class RateLimiter:
    """Per-host minimum-interval rate limiter (thread-safe).

    ``wait(host)`` sleeps just long enough to honor the interval, then
    records the call. Hosts are matched on the URL's netloc (lowercased,
    port stripped).
    """

    def __init__(self, intervals: dict[str, float] | None = None,
                 default_interval: float = DEFAULT_INTERVAL) -> None:
        self.intervals = dict(intervals) if intervals else dict(HOST_INTERVALS)
        self.default_interval = default_interval
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def host_of(url: str) -> str:
        try:
            return (urlparse(url).hostname or "").lower()
        except Exception:
            return ""

    def interval_for(self, host: str) -> float:
        return self.intervals.get((host or "").lower(), self.default_interval)

    def wait(self, url_or_host: str) -> float:
        """Sleep until the host's interval has elapsed. Returns seconds slept."""
        host = url_or_host if "://" not in url_or_host else self.host_of(url_or_host)
        interval = self.interval_for(host)
        slept = 0.0
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait_for = interval - (now - last)
            if wait_for > 0:
                slept = wait_for
            self._last[host] = now + slept
        if slept > 0:
            time.sleep(slept)
        return slept


#: Process-wide limiter used by :func:`polite_get`.
limiter = RateLimiter()


# ---------------------------------------------------------------------------
# 4. ETag / Last-Modified conditional cache (file-backed)
# ---------------------------------------------------------------------------

_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "cache", "http")
CACHE_TTL = 24 * 3600  # 24h


def _cache_path(url: str, params: dict | None) -> str:
    canon = url + "?" + "&".join(
        "%s=%s" % (k, params[k]) for k in sorted(params or {}))
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    return os.path.join(_CACHE_DIR, digest + ".json")


def _cache_read(url: str, params: dict | None) -> dict | None:
    try:
        with open(_cache_path(url, params), encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("stored_at", 0) + CACHE_TTL < time.time():
        return None
    return payload


def _cache_write(url: str, params: dict | None, entry: dict) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        tmp = _cache_path(url, params) + ".tmp"
        entry = dict(entry)
        entry["stored_at"] = time.time()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry, fh)
        os.replace(tmp, _cache_path(url, params))
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("HTTP cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# 5. Polite GET with graceful degradation
# ---------------------------------------------------------------------------

TIMEOUT = 15


def polite_get(url: str, params: dict | None = None,
               timeout: int = TIMEOUT,
               use_cache: bool = True) -> dict:
    """GET a research API politely. Never raises.

    Honors the per-host rate limit, sends ``If-None-Match`` /
    ``If-Modified-Since`` when a cached entry exists, and returns one of::

        {"ok": True, "status": 200, "text": str, "from_cache": bool,
         "url": str}
        {"ok": False, "error": str, "hint": str, "retryable": bool}

    ``error`` is always a clear, user-facing message; ``hint`` suggests
    what to do next.
    """
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "error": "No URL was provided.",
                "hint": "This looks like an app bug — please report it.",
                "retryable": False}
    host = RateLimiter.host_of(url)
    cached = _cache_read(url, params) if use_cache else None
    headers: dict[str, str] = {}
    if cached:
        if cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]
        if cached.get("last_modified"):
            headers["If-Modified-Since"] = cached["last_modified"]
    limiter.wait(host or url)
    try:
        resp = get_session().get(url, params=params, headers=headers,
                                 timeout=timeout)
    except requests.Timeout:
        if cached and cached.get("body") is not None:
            return {"ok": True, "status": 200, "text": cached["body"],
                    "from_cache": True, "url": url,
                    "note": "Live request timed out; showing cached copy."}
        return {"ok": False,
                "error": "%s did not respond within %ds."
                         % (host or "The research service", timeout),
                "hint": "Check your connection and try again shortly.",
                "retryable": True}
    except requests.RequestException as exc:
        if cached and cached.get("body") is not None:
            return {"ok": True, "status": 200, "text": cached["body"],
                    "from_cache": True, "url": url,
                    "note": "Network error; showing cached copy."}
        return {"ok": False,
                "error": "Could not reach %s (%s)."
                         % (host or "the research service",
                            type(exc).__name__),
                "hint": "Check your connection and try again shortly.",
                "retryable": True}

    if resp.status_code == 304 and cached and cached.get("body") is not None:
        return {"ok": True, "status": 200, "text": cached["body"],
                "from_cache": True, "url": url}
    if resp.status_code == 429:
        return {"ok": False,
                "error": "%s is rate-limiting us (HTTP 429)."
                         % (host or "The research service"),
                "hint": "Wait a minute and try again — no data was lost.",
                "retryable": True}
    if resp.status_code >= 500:
        return {"ok": False,
                "error": "%s returned HTTP %d (server error)."
                         % (host or "The research service",
                            resp.status_code),
                "hint": "The service may be down; try again later.",
                "retryable": True}
    if resp.status_code == 404:
        return {"ok": False,
                "error": "Nothing found at %s (HTTP 404)." % url,
                "hint": "Double-check the ID or DOI and try again.",
                "retryable": False}
    if resp.status_code != 200:
        return {"ok": False,
                "error": "%s returned HTTP %d."
                         % (host or "The research service",
                            resp.status_code),
                "hint": "Try again shortly; report it if it persists.",
                "retryable": resp.status_code not in (400, 401, 403)}

    body = resp.text
    if use_cache:
        _cache_write(url, params, {
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "body": body,
        })
    return {"ok": True, "status": 200, "text": body,
            "from_cache": False, "url": url}


def fetch_xml(url: str, params: dict | None = None,
              timeout: int = TIMEOUT) -> dict:
    """polite_get + defusedxml parsing. Never raises.

    Returns ``{"ok": True, "root": Element, ...}`` or the polite_get
    ``{"ok": False, ...}`` shape (plus a clear message when the XML
    itself is malformed — never an XML bomb, thanks to defusedxml).
    """
    res = polite_get(url, params=params, timeout=timeout)
    if not res.get("ok"):
        return res
    try:
        root = ET.fromstring(res["text"])
    except Exception:
        # Includes ET.ParseError AND defusedxml's bomb defenses
        # (EntitiesForbidden etc.): hostile XML degrades gracefully too.
        return {"ok": False,
                "error": "The response from %s was not valid XML."
                         % RateLimiter.host_of(url),
                "hint": "Try again shortly; report it if it persists.",
                "retryable": True}
    res["root"] = root
    del res["text"]
    return res


def fetch_json(url: str, params: dict | None = None,
               timeout: int = TIMEOUT) -> dict:
    """polite_get + JSON parsing. Never raises."""
    res = polite_get(url, params=params, timeout=timeout)
    if not res.get("ok"):
        return res
    try:
        data = json.loads(res["text"])
    except ValueError:
        return {"ok": False,
                "error": "The response from %s was not valid JSON."
                         % RateLimiter.host_of(url),
                "hint": "Try again shortly; report it if it persists.",
                "retryable": True}
    res["data"] = data
    del res["text"]
    return res


# ---------------------------------------------------------------------------
# 6. Record provenance
# ---------------------------------------------------------------------------

def stamp_record(record: dict | None, source: str) -> dict:
    """Attach ``retrieved_at`` (UTC ISO-8601) + ``source`` to a record.

    Returns a copy; never mutates the input. Never raises.
    """
    out = dict(record) if isinstance(record, dict) else {}
    out["retrieved_at"] = datetime.now(UTC).isoformat()
    out["source"] = source
    return out
