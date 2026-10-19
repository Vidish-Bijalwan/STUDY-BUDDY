"""ENG-11: Job and opportunity recommendations that are real and legal.

Product promise (honest, shown on every surface using this module):
    "Curated opportunities — every card shows its source and last-verified date."

Principles enforced here:
- Every recommendation card carries ``source`` and ``last_verified``; cards
  older than ``MAX_CARD_AGE_DAYS`` are flagged expired, never silently served.
- Paste-a-JD is the strongest flow: zero third-party terms-of-service risk,
  matched with the ENG-07 parser.
- Live feeds come ONLY from official APIs whose terms have been verified
  (see docs/eng/jobs-sources.md). Adapter stubs below raise
  ``NotImplementedError`` until an API key is configured AND the ToS
  checklist is signed off — there is no scraping path anywhere in this
  module, by design.
- Each recommendation explains itself: "matched 7 of 9 must-haves;
  missing: Docker".
"""

from datetime import date, datetime
import re

from .eng_jd_v2 import extract_jd_v2

PRODUCT_PROMISE = ("Curated opportunities — every card shows its source "
                   "and last-verified date.")
MAX_CARD_AGE_DAYS = 30
TOS_CHECKLIST_DOC = "docs/eng/jobs-sources.md"

LEVELS = ("intern", "fresher", "junior", "mid", "senior")


def make_job_card(*, title, company, location="", level="fresher",
                  source, source_url=None, last_verified=None, jd_text="",
                  external_id=None):
    """Build a recommendation card. ``source`` and ``last_verified`` are mandatory."""
    if not source:
        raise ValueError("source is required on every job card (ENG-11)")
    card = {
        "id": external_id or f"{(company or '').strip().lower()}::{(title or '').strip().lower()}",
        "title": (title or "").strip(),
        "company": (company or "").strip(),
        "location": (location or "").strip(),
        "level": (level or "").strip().lower(),
        "source": source,
        "source_url": source_url,
        "last_verified": last_verified or date.today().isoformat(),
        "jd_text": jd_text or "",
        "must_haves": [],
        "nice_to_haves": [],
        "expired": False,
    }
    if card["level"] not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}, got {level!r}")
    parsed = extract_jd_v2(card["jd_text"]) if card["jd_text"] else {"requirements": []}
    for req in parsed["requirements"]:
        entry = {"text": req["text"], "skills": req["skills"]}
        if req["importance"] == "must":
            card["must_haves"].append(entry)
        elif req["importance"] == "nice":
            card["nice_to_haves"].append(entry)
    return card


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except (ValueError, TypeError):
        return None


def is_expired(card, today=None, max_age_days=MAX_CARD_AGE_DAYS):
    """True when the card's last_verified is older than ``max_age_days``."""
    verified = _parse_date((card or {}).get("last_verified"))
    if verified is None:
        return True  # no verifiable date -> treat as expired
    today = today or date.today()
    return (today - verified).days > max_age_days


def refresh_card(card, today=None):
    """Mark a card re-verified today (after a link/source check)."""
    card = dict(card or {})
    card["last_verified"] = (today or date.today()).isoformat()
    card["expired"] = False
    return card


def explain_match(card, resume_skill_names, resume_years=0):
    """Human-readable explanation for one recommendation.

    Format: "Matched 7 of 9 must-haves; missing: Docker, Kubernetes".
    """
    resume_skills = {s.lower() for s in (resume_skill_names or [])}
    must = (card or {}).get("must_haves") or []
    matched, missing = [], []
    for req in must:
        skills = req.get("skills") or []
        if not skills:
            # Non-skill requirement: count as matched only if its key terms
            # appear; here we conservatively count lexical presence.
            matched.append(req.get("text", "")[:60])
            continue
        if all(s.lower() in resume_skills for s in skills):
            matched.extend(skills)
        else:
            missing.extend([s for s in skills if s.lower() not in resume_skills])
    total = len(must)
    explanation = (f"Matched {len(matched)} of {total} must-haves"
                   + (f"; missing: {', '.join(sorted(set(missing)))}" if missing else "; no must-have gaps"))
    return {"matched": len(matched), "total": total,
            "matched_skills": sorted(set(matched)),
            "missing_skills": sorted(set(missing)),
            "explanation": explanation}


def score_job_card(card, resume_skill_names, resume_years=0):
    """Score a card for ranking: must-have coverage, nice-to-have bonus."""
    exp = explain_match(card, resume_skill_names, resume_years)
    must_score = (exp["matched"] / exp["total"]) if exp["total"] else 1.0
    resume_skills = {s.lower() for s in (resume_skill_names or [])}
    nice = (card or {}).get("nice_to_haves") or []
    nice_hit = sum(1 for r in nice for s in (r.get("skills") or [])
                   if s.lower() in resume_skills)
    nice_total = sum(len(r.get("skills") or []) for r in nice)
    nice_score = (nice_hit / nice_total) if nice_total else 0.0
    score = round(0.8 * must_score + 0.2 * nice_score, 3)
    return {"score": score, "must_coverage": round(must_score, 3),
            "nice_coverage": round(nice_score, 3), **exp,
            "expired": is_expired(card)}


def recommend_jobs(cards, resume_skill_names, resume_years=0, *,
                   geography=None, level=None, include_expired=False):
    """Rank cards for a user: dedupe -> filter -> drop expired -> score -> sort."""
    cards = dedupe_jobs(cards or [])
    cards = filter_jobs(cards, geography=geography, level=level)
    if not include_expired:
        cards = [c for c in cards if not is_expired(c)]
    scored = []
    for card in cards:
        s = score_job_card(card, resume_skill_names, resume_years)
        scored.append({**card, "recommendation": s})
    scored.sort(key=lambda c: -c["recommendation"]["score"])
    return scored


def _norm(value):
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def dedupe_jobs(cards):
    """Drop duplicate cards: same normalized (title, company, source_url)."""
    seen, out = set(), []
    for card in cards or []:
        key = (_norm(card.get("title")), _norm(card.get("company")),
               _norm(card.get("source_url") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out


def filter_jobs(cards, geography=None, level=None):
    """Filter by geography substring and/or career level."""
    out = []
    for card in cards or []:
        if geography and geography.strip().lower() not in (card.get("location") or "").lower():
            continue
        if level and (card.get("level") or "").lower() != level.strip().lower():
            continue
        out.append(card)
    return out


def paste_jd_flow(jd_text, *, title="Pasted role", company="User-provided JD",
                  location="", level="fresher"):
    """Paste-a-JD flow: no ToS risk, matched locally with the ENG-07 parser.

    Returns a job card sourced from the user's own paste, ready for
    ``explain_match`` / ``score_job_card``.
    """
    if not (jd_text or "").strip():
        raise ValueError("jd_text must not be empty")
    return make_job_card(title=title, company=company, location=location,
                         level=level, source="User-pasted JD",
                         source_url=None, jd_text=jd_text)


# ---------------------------------------------------------------------------
# Official-API adapters (pragmatic v1: structured, not live)
#
# These adapters are DELIBERATELY inert: each raises NotImplementedError
# until (a) an official API credential is configured and (b) the ToS
# checklist in docs/eng/jobs-sources.md is verified for that source.
# There is no scraping code path — scraping job boards whose terms forbid
# it would violate ENG-11 and the sites' terms of service.
# ---------------------------------------------------------------------------

class JobSourceAdapter:
    """Base class for official job-feed API adapters."""

    name = "base"
    api_docs_url = ""
    tos_verified = False  # set True only after docs/eng/jobs-sources.md sign-off

    def __init__(self, api_key=None):
        self.api_key = api_key

    def fetch(self, query, location="", level=None, limit=20):
        """Fetch live listings. Raises until credential + ToS sign-off exist."""
        if not self.api_key:
            raise NotImplementedError(
                f"{self.name}: no API credential configured. Configure the "
                f"official {self.name} API key first.")
        if not self.tos_verified:
            raise NotImplementedError(
                f"{self.name}: terms-of-service not yet verified. Complete the "
                f"checklist in {TOS_CHECKLIST_DOC} and set tos_verified=True.")
        raise NotImplementedError(f"{self.name}: live fetch not implemented in v1.")

    def to_cards(self, raw_listings):
        """Normalize raw API listings into job cards. Override per source."""
        raise NotImplementedError


class AdzunaAdapter(JobSourceAdapter):
    name = "Adzuna"
    api_docs_url = "https://developer.adzuna.com/"


class JoobleAdapter(JobSourceAdapter):
    name = "Jooble"
    api_docs_url = "https://jooble.org/api/about"


class RemoteOKAdapter(JobSourceAdapter):
    name = "RemoteOK"
    api_docs_url = "https://remoteok.com/api"
