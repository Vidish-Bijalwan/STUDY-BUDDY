"""Application package — ARC-01 strangler-pattern extraction.

Phase 1 moves Flask extension *objects* and validated configuration out of the
``unified_app.py`` monolith. Route blueprints follow the same pattern
(see ``app.blueprints.auth_bp``).

``unified_app.py`` keeps working by importing these objects back; over time,
``create_app`` itself migrates here and the monolith shrinks to routes/models.
"""

from app import config, extensions  # noqa: F401  (re-export for convenience)

__all__ = ["config", "extensions"]
