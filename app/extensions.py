"""Shared Flask extension objects — ARC-01 extraction from unified_app.py.

These are the *unbound* extension instances. They are initialised against the
app inside ``create_app`` (``init_app``), exactly as before. Importing them
from here instead of ``unified_app`` lets blueprints and helpers use ``db``,
``limiter``, etc. without importing the monolith.
"""

from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
# ARC-03: Alembic migrations via Flask-Migrate. Initialized in create_app().
migrate = None  # set to Migrate() once flask-migrate is importable
try:
    from flask_migrate import Migrate as _Migrate

    migrate = _Migrate()
except ImportError:  # pragma: no cover - dev without flask-migrate
    pass

login_manager = LoginManager()
csrf = CSRFProtect()


def _rate_limit_key():
    """SEC-04: key by user id when authenticated, else client IP.

    ProxyFix (x_for=1) runs before this, so remote_addr is the real client
    behind Render's single proxy hop — not one global bucket for everyone.
    """
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            return f"user:{current_user.get_id()}"
    except Exception:
        pass
    return f"ip:{get_remote_address()}"


# SEC-04: storage from env (memory:// dev/test; Redis in production via
# RATELIMIT_STORAGE_URI). Global default limits + per-route limits.
limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=["200 per day", "60 per hour"],
    storage_uri=(
        __import__("os").environ.get("RATELIMIT_STORAGE_URI") or "memory://"
    ),
)
oauth = OAuth()  # social login clients (registered per-app in create_app)

__all__ = [
    "db",
    "migrate",
    "login_manager",
    "csrf",
    "limiter",
    "oauth",
    "_rate_limit_key",
]
