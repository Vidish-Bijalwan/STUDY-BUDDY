"""Notification preferences + email hooks (UX-10).

Opt-in only. Categories: application follow-up reminders, opportunity
deadlines, streak nudges, product announcements (marketing = explicit consent
only). No provider keys here — the sending provider is chosen at deploy time;
see docs/ux/notifications.md for the SPF/DKIM/DMARC checklist.

Unsubscribe: per-user signed token (itsdangerous), works without login.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from itsdangerous import BadSignature, URLSafeSerializer


#: Notification categories and their defaults. All default OFF except
#: transactional necessities (none currently — even reminders are opt-in).
CATEGORIES: dict[str, dict] = {
    "application_followup": {
        "label": "Application follow-up reminders",
        "default": False,
        "marketing": False,
        "description": "Nudges to follow up on applications older than N days.",
    },
    "opportunity_deadline": {
        "label": "Opportunity deadline alerts",
        "default": False,
        "marketing": False,
        "description": "Reminders 3 days before saved opportunity deadlines.",
    },
    "streak_nudge": {
        "label": "Practice streak reminders",
        "default": False,
        "marketing": False,
        "description": "A gentle nudge when a streak is about to lapse.",
    },
    "announcements": {
        "label": "Product announcements",
        "default": False,
        "marketing": True,
        "description": "Occasional launch/feature news. Explicit consent required.",
    },
}


@dataclass
class NotificationPrefs:
    """Per-user preferences. Persist as JSON in the user record."""

    user_id: int | str
    email: str = ""
    email_verified: bool = False
    enabled: dict[str, bool] = field(default_factory=dict)

    def is_on(self, category: str) -> bool:
        if category not in CATEGORIES:
            raise KeyError(f"unknown notification category: {category}")
        return bool(self.enabled.get(category, CATEGORIES[category]["default"]))

    def set(self, category: str, on: bool) -> None:
        if category not in CATEGORIES:
            raise KeyError(f"unknown notification category: {category}")
        if CATEGORIES[category]["marketing"] and on and not self.email_verified:
            raise ValueError("marketing email requires a verified address")
        self.enabled[category] = bool(on)

    def unsubscribe_all(self) -> None:
        for cat in CATEGORIES:
            self.enabled[cat] = False

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "email_verified": self.email_verified,
            "enabled": {c: self.is_on(c) for c in CATEGORIES},
        }


def make_unsubscribe_token(secret_key: str, user_id: int | str) -> str:
    s = URLSafeSerializer(secret_key, salt="studybuddy-unsub-v1")
    return s.dumps({"uid": str(user_id), "ts": int(time.time())})


def verify_unsubscribe_token(secret_key: str, token: str) -> str | None:
    s = URLSafeSerializer(secret_key, salt="studybuddy-unsub-v1")
    try:
        payload = s.loads(token)
    except BadSignature:
        return None
    return payload.get("uid")


# ---------------------------------------------------------------------------
# Email hook stubs — the app calls these; a provider adapter implements send.
# ---------------------------------------------------------------------------
class EmailProviderStub:
    """Drop-in placeholder. Implement .send() with a real transactional
    provider (see docs/ux/notifications.md). Records calls for tests."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, *, to: str, subject: str, text_body: str, category: str,
             unsubscribe_url: str) -> dict:
        if category not in CATEGORIES:
            raise KeyError(f"unknown notification category: {category}")
        msg = {
            "to": to,
            "subject": subject,
            "text_body": text_body,
            "category": category,
            "unsubscribe_url": unsubscribe_url,
        }
        self.sent.append(msg)
        return {"queued": True, "message_id": f"stub-{len(self.sent)}",
                "text_body": text_body}


def maybe_notify(
    provider: EmailProviderStub,
    prefs: NotificationPrefs,
    *,
    category: str,
    subject: str,
    text_body: str,
    unsubscribe_base_url: str,
    secret_key: str,
) -> dict | None:
    """Send only if: opted in, (marketing => verified email), address present."""
    if not prefs.is_on(category):
        return None
    if not prefs.email:
        return None
    if CATEGORIES[category]["marketing"] and not prefs.email_verified:
        return None
    token = make_unsubscribe_token(secret_key, prefs.user_id)
    body = f"{text_body}\n\nUnsubscribe: {unsubscribe_base_url}?token={token}"
    return provider.send(
        to=prefs.email,
        subject=subject,
        text_body=body,
        category=category,
        unsubscribe_url=f"{unsubscribe_base_url}?token={token}",
    )


__all__ = [
    "CATEGORIES",
    "NotificationPrefs",
    "make_unsubscribe_token",
    "verify_unsubscribe_token",
    "EmailProviderStub",
    "maybe_notify",
]
