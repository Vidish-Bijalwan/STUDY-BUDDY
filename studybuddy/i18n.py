"""Internationalization helpers (UX-05).

Ship English and Hindi first; Hinglish microcopy where appropriate. Resume
analysis stays English-first (stated clearly; no multilingual-parsing claims
without tests).

Design: Flask-Babel is an OPTIONAL dependency wired lazily by
:meth:`init_babel`. Even without it installed, :func:`translate` works via a
stdlib gettext-based .po reader against ``translations/<locale>/LC_MESSAGES/``,
so the Hindi catalog is usable and testable with zero new deps.

Locale resolution order: ?lang query param (validated) > user preference >
Accept-Language header. Only locales with a compiled or parseable catalog are
served.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

#: Locales we ship. English is the fallback for everything.
SUPPORTED_LOCALES = ("en", "hi")
DEFAULT_LOCALE = "en"

_TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"


def available_locales() -> tuple[str, ...]:
    """Locales that have at least a parseable .po catalog (en always)."""
    found = ["en"]
    for loc in SUPPORTED_LOCALES:
        if loc == "en":
            continue
        po = _TRANSLATIONS_DIR / loc / "LC_MESSAGES" / "messages.po"
        if po.is_file():
            found.append(loc)
    return tuple(found)


def resolve_locale(lang_param: str | None = None, accept_language: str | None = None) -> str:
    """Pick a locale from ?lang, then Accept-Language; fall back to en."""
    available = set(available_locales())
    if lang_param:
        cand = lang_param.strip().lower().split("-")[0]
        if cand in available:
            return cand
    if accept_language:
        for part in accept_language.split(","):
            tag = part.split(";")[0].strip().lower().split("-")[0]
            if tag in available:
                return tag
    return DEFAULT_LOCALE


@lru_cache(maxsize=8)
def _load_po_catalog(locale: str) -> dict[str, str]:
    """Parse translations/<locale>/LC_MESSAGES/messages.po (msgid -> msgstr).

    Minimal .po reader: handles msgid/msgstr pairs (single- and multi-line
    strings). Plural forms are out of scope for v1.
    """
    catalog: dict[str, str] = {}
    po = _TRANSLATIONS_DIR / locale / "LC_MESSAGES" / "messages.po"
    if not po.is_file():
        return catalog

    msgid_parts: list[str] = []
    msgstr_parts: list[str] = []
    in_msgid = in_msgstr = False

    def unquote(s: str) -> str:
        s = s.strip()
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        return s.replace('\\"', '"').replace("\\n", "\n")

    def flush() -> None:
        if msgid_parts:
            msgid = "".join(msgid_parts)
            msgstr = "".join(msgstr_parts)
            if msgid and msgstr:
                catalog[msgid] = msgstr

    for raw in po.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid"):
            flush()
            msgid_parts, msgstr_parts = [unquote(line[5:])], []
            in_msgid, in_msgstr = True, False
        elif line.startswith("msgstr"):
            msgstr_parts = [unquote(line[6:])]
            in_msgid, in_msgstr = False, True
        elif line.startswith('"') and (in_msgid or in_msgstr):
            (msgid_parts if in_msgid else msgstr_parts).append(unquote(line))
    flush()
    # Header entry (msgid "") is not a real string.
    catalog.pop("", None)
    return catalog


def translate(msgid: str, locale: str | None = None, **kwargs: object) -> str:
    """Translate msgid to the locale (default en -> identity).

    Supports %-style or {named} formatting via kwargs. Unknown strings fall
    back to English (the msgid itself).
    """
    loc = (locale or DEFAULT_LOCALE).lower()
    text = _load_po_catalog(loc).get(msgid, msgid) if loc != "en" else msgid
    if kwargs:
        try:
            text = text.format(**kwargs) if "{" in text else text % kwargs
        except (KeyError, ValueError):
            pass
    return text


def init_babel(app, *, default_locale: str = DEFAULT_LOCALE):
    """Lazily wire Flask-Babel if installed; no-op otherwise.

    Returns the Babel instance or None. Never raises when Flask-Babel is
    missing — the app keeps serving English.
    """
    try:
        from flask_babel import Babel  # type: ignore
    except ImportError:
        return None
    babel = Babel(app, default_locale=default_locale)

    def _selector() -> str:  # Flask-Babel >= 3 style hook
        from flask import request

        return resolve_locale(
            request.args.get("lang"),
            request.headers.get("Accept-Language"),
        )

    if hasattr(babel, "locale_selector"):
        babel.locale_selector(_selector)  # type: ignore[attr-defined]
    return babel


def babel_wiring_snippet() -> str:
    return (
        "from studybuddy.i18n import init_babel\n"
        "init_babel(app)  # lazy; no-op if Flask-Babel is not installed\n"
        "# then: pip install Flask-Babel && pybabel compile -d translations\n"
    )


# ---------------------------------------------------------------------------
# INR / lakh-crore formatting note (UX-05 acceptance: locale-aware numbers)
# ---------------------------------------------------------------------------
def format_inr_lpa(value_lpa: float) -> str:
    """Render an LPA value in an Indian-friendly form."""
    if value_lpa >= 100:
        return f"₹{value_lpa / 100:.2f} Cr/yr"
    if value_lpa >= 1:
        return f"₹{value_lpa:.1f} L/yr"
    return f"₹{value_lpa * 100_000:,.0f}/yr"


def _is_valid_lang(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2,4})?", value or ""))


__all__ = [
    "SUPPORTED_LOCALES",
    "DEFAULT_LOCALE",
    "available_locales",
    "resolve_locale",
    "translate",
    "init_babel",
    "format_inr_lpa",
]
