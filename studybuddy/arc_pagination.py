"""ARC-13: Pagination and query limits for list endpoints.

Every list endpoint (reports, applications, bookmarks, history) must paginate
with sane defaults (page size 20, max 100) and STABLE ordering.

Stable ordering requirement (read before wiring a route):
    Pagination is only correct when the ordering is deterministic. Always pass
    ``order_by`` ending in a unique tiebreak — e.g.
    ``(Model.created_at.desc(), Model.id.desc())``. Without the id tiebreak,
    rows sharing a timestamp can appear on two pages or vanish between pages.

Two usage patterns:

1. Explicit (recommended for JSON APIs — view keeps control of serialization)::

    from studybuddy.arc_pagination import paginate

    @app.route("/api/reports")
    @login_required
    def list_reports():
        q = ResumeAnalysis.query.filter_by(user_id=current_user.id)
        page = paginate(request.args.get("page"), request.args.get("per_page"), q,
                        order_by=(ResumeAnalysis.created_at.desc(),
                                  ResumeAnalysis.id.desc()))
        return jsonify({**page, "items": [serialize(r) for r in page["items"]]})

2. Decorator (view returns a bare Query; decorator paginates + serializes)::

    from studybuddy.arc_pagination import paginated

    @app.route("/api/reports")
    @login_required
    @paginated(order_by=(ResumeAnalysis.created_at.desc(),
                         ResumeAnalysis.id.desc()),
               serialize=serialize_report)
    def list_reports():
        return ResumeAnalysis.query.filter_by(user_id=current_user.id)
"""

from __future__ import annotations

import math
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Sequence

from flask import request

DEFAULT_PER_PAGE = 20
MAX_PER_PAGE = 100

__all__ = [
    "DEFAULT_PER_PAGE",
    "MAX_PER_PAGE",
    "normalize_pagination",
    "paginate",
    "paginated",
]


def normalize_pagination(page: Any, per_page: Any,
                         default: int = DEFAULT_PER_PAGE,
                         max_per_page: int = MAX_PER_PAGE) -> tuple[int, int]:
    """Clamp raw page/per_page inputs to sane values.

    * non-numeric / missing -> defaults (page 1, ``default`` per page)
    * page < 1 -> 1
    * per_page < 1 -> 1; per_page > max_per_page -> max_per_page
    """
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(per_page)
    except (TypeError, ValueError):
        per_page = default
    page = max(1, page)
    per_page = min(max_per_page, max(1, per_page))
    return page, per_page


def paginate(page: Any, per_page: Any, query,
             order_by: Optional[Sequence] = None,
             default: int = DEFAULT_PER_PAGE,
             max_per_page: int = MAX_PER_PAGE) -> Dict[str, Any]:
    """Paginate a SQLAlchemy query. Returns an envelope dict.

    Args:
        page: 1-based page number (clamped, defaults to 1).
        per_page: page size (clamped to [1, max_per_page], defaults to 20).
        query: SQLAlchemy Query (or Flask-SQLAlchemy BaseQuery).
        order_by: REQUIRED for correct pagination — a deterministic ordering
            (see module docstring). Applied on top of any existing ordering.

    Returns:
        {"items", "page", "per_page", "total", "pages", "has_next", "has_prev"}
    """
    page, per_page = normalize_pagination(page, per_page, default, max_per_page)
    if order_by:
        query = query.order_by(*order_by)
    # Count without ordering (cheaper on some backends, same result).
    total = query.order_by(None).count()
    pages = max(1, math.ceil(total / per_page)) if total else 1
    items: List[Any] = (
        query.offset((page - 1) * per_page).limit(per_page).all()
    )
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def paginated(order_by: Optional[Sequence] = None,
              serialize: Callable[[Any], Any] = lambda x: x,
              default_per_page: int = DEFAULT_PER_PAGE,
              max_per_page: int = MAX_PER_PAGE):
    """Route decorator: the view returns a Query; the decorator paginates it.

    ``order_by`` is REQUIRED (stable ordering — see module docstring); the
    decorator raises ValueError without it so a missing tiebreak can never
    silently ship. ``serialize`` converts each item for JSON output.
    Reads ``page`` / ``per_page`` from the request query string.
    """
    if order_by is None:
        raise ValueError(
            "paginated: stable order_by is required (ARC-13) — pass e.g. "
            "(Model.created_at.desc(), Model.id.desc())")

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            query = view(*args, **kwargs)
            result = paginate(
                request.args.get("page", 1),
                request.args.get("per_page", default_per_page),
                query,
                order_by=order_by,
                default=default_per_page,
                max_per_page=max_per_page,
            )
            result["items"] = [serialize(item) for item in result["items"]]
            return result

        return wrapper

    return decorator
