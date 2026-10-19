"""ENG-07: JD matcher v2 — structured requirement parsing and weighted coverage.

Parses a job description into discrete requirements by splitting on section
headings (Requirements / Qualifications / Responsibilities / Nice-to-have),
classifies each requirement as must-have vs nice-to-have from cue phrases,
extracts skills through the canonical taxonomy engine, and captures
years-of-experience and education requirements with regexes.

Scoring is weighted coverage: must-haves count more than nice-to-haves, with
field-aware weights. A semantic-similarity fallback (callable ``embed``)
can resolve unmatched requirements that lexical matching misses
("REST APIs" vs "built HTTP services"); when no embeddings are configured
the report says so plainly instead of guessing.

All outputs are deterministic and JSON-serializable.
"""

import re
from datetime import date

from .skills_taxonomy import extract_skills_fast

# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

# Canonical section -> heading variants (lowercased) matched as headings.
_SECTION_HEADINGS = {
    "requirements": [
        "requirements", "minimum requirements", "basic requirements",
        "what you'll need", "what you need", "you'll need",
        "minimum qualifications", "basic qualifications", "required skills",
        "required qualifications", "must haves", "must-haves",
    ],
    "qualifications": [
        "qualifications", "education", "educational qualifications",
        "eligibility", "who you are",
    ],
    "responsibilities": [
        "responsibilities", "what you'll do", "what you will do",
        "the role", "about the role", "job duties", "key responsibilities",
        "your responsibilities", "day to day", "day-to-day",
    ],
    "nice_to_have": [
        "nice to have", "nice-to-have", "nice to haves", "nice-to-haves",
        "bonus", "bonuses", "pluses", "plus", "preferred skills",
        "preferred qualifications", "desirable", "good to have",
        "would be nice", "nice if you have", "differentiators",
    ],
}

# Default importance by section before cue phrases are applied.
_SECTION_DEFAULT_IMPORTANCE = {
    "requirements": "must",
    "qualifications": "must",
    "responsibilities": "context",
    "nice_to_have": "nice",
}

# ---------------------------------------------------------------------------
# Cue phrases for must-have vs nice-to-have classification
# ---------------------------------------------------------------------------

_MUST_CUES = [
    "required", "requires", "requirement", "must have", "must-have",
    "mandatory", "essential", "should have", "need to have", "non-negotiable",
    "minimum of", "at least", "will have", "proven experience",
]
_NICE_CUES = [
    "preferred", "preferably", "plus", "a plus", "nice to have",
    "nice-to-have", "bonus", "desirable", "familiarity", "familiar with",
    "exposure to", "would be great", "ideal but", "optional",
    "good to have", "would be nice",
]


def _heading_regex():
    parts = []
    for section, variants in _SECTION_HEADINGS.items():
        for v in sorted(variants, key=len, reverse=True):
            parts.append((v, section))
    pattern = r"^\s*(?:#{1,4}\s*)?(" + "|".join(re.escape(v) for v, _ in parts) + r")\s*:?\s*$"
    return re.compile(pattern, re.IGNORECASE), {v.lower(): s for v, s in parts}


_HEADING_RX, _HEADING_MAP = _heading_regex()


def split_jd_sections(jd_text):
    """Split JD text into {section: body} using heading detection.

    Lines that match a known heading variant (optionally with a trailing
    colon or markdown #s) start a new section. Text before the first
    heading lands in "overview". Unknown sections are kept under their own
    heading text.
    """
    text = jd_text or ""
    sections = {"overview": []}
    current = "overview"
    for line in text.splitlines():
        m = _HEADING_RX.match(line.strip())
        if m:
            current = _HEADING_MAP[m.group(1).lower()]
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items() if "\n".join(v).strip()}


def _split_requirements(body):
    """Split a section body into individual requirement strings."""
    reqs = []
    for line in (body or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip bullet / numbering markers.
        line = re.sub(r"^(?:[-*•◦▪–—]|\d{1,2}[.)])\s+", "", line).strip()
        if not line or len(line) < 4:
            continue
        # A line may hold several sentences; split very long lines on ';'.
        parts = [p.strip() for p in re.split(r"\s*;\s*", line) if p.strip()]
        reqs.extend(parts)
    return reqs


def classify_requirement(text, section):
    """Classify one requirement: 'must', 'nice', or 'context'.

    Explicit cue phrases override the section default — e.g. a "plus:"
    line inside Requirements is nice-to-have, and "required" inside
    Nice-to-have is still must-have (rare but decisive).
    """
    lower = (text or "").lower()
    if any(cue in lower for cue in _NICE_CUES):
        return "nice"
    if any(cue in lower for cue in _MUST_CUES):
        return "must"
    return _SECTION_DEFAULT_IMPORTANCE.get(section, "context")


# ---------------------------------------------------------------------------
# Years-of-experience and education extraction
# ---------------------------------------------------------------------------

_YEARS_RX = re.compile(
    r"(\d{1,2})\s*(?:\+)?\s*(?:-|to|–)?\s*(?:(\d{1,2})\s*)?"
    r"(?:years?|yrs?)\b(?:\s*(?:of|minimum|at\s+least))?\s*(?:experience)?",
    re.IGNORECASE)

_EDUCATION_PATTERNS = [
    (re.compile(r"\bph\.?d\b|\bdoctorate\b", re.IGNORECASE), "PhD"),
    (re.compile(r"\bm\.?tech\b|\bm\.?e\.?\b(?!\s*tech)", re.IGNORECASE), "M.Tech/M.E."),
    (re.compile(r"\bmba\b", re.IGNORECASE), "MBA"),
    (re.compile(r"\bmaster'?s\b|\bm\.?sc\b|\bm\.?s\.?\b", re.IGNORECASE), "Master's"),
    (re.compile(r"\bb\.?tech\b|\bb\.?e\.?\b", re.IGNORECASE), "B.Tech/B.E."),
    (re.compile(r"\bbachelor'?s\b|\bb\.?sc\b|\bb\.?ca\b|\bundergraduate\b", re.IGNORECASE), "Bachelor's"),
    (re.compile(r"\bdiploma\b", re.IGNORECASE), "Diploma"),
]


def extract_years_requirement(text):
    """Return the maximum years-of-experience figure in ``text``, or None."""
    years = None
    for m in _YEARS_RX.finditer(text or ""):
        nums = [int(g) for g in m.groups() if g]
        if not nums:
            continue
        n = max(nums)
        if 0 < n <= 30 and (years is None or n > years):
            years = n
    return years


def extract_education_requirement(text):
    """Return a list of education levels mentioned in ``text``."""
    found = []
    for rx, label in _EDUCATION_PATTERNS:
        if rx.search(text or "") and label not in found:
            found.append(label)
    return found


# ---------------------------------------------------------------------------
# Full JD parse
# ---------------------------------------------------------------------------

_FIELD_WEIGHTS = {"skills": 1.0, "years": 1.2, "education": 1.0, "lexical": 0.6}
_IMPORTANCE_WEIGHTS = {"must": 3.0, "context": 2.0, "nice": 1.0}

_HONESTY_NOTE = (
    "Add only skills you genuinely have. Mirror the JD's exact wording for "
    "skills you already possess, but never invent experience — fabricated "
    "skills surface in technical interviews and can cost you the offer."
)


def extract_jd_v2(jd_text):
    """Parse a JD into structured requirements.

    Returns {"job_title", "sections", "requirements"} where each requirement
    is {"text", "section", "importance", "skills", "years", "education"}.
    """
    text = jd_text or ""
    sections = split_jd_sections(text)
    title = ""
    for line in text.splitlines():
        if line.strip():
            title = line.strip()[:120]
            break
    requirements = []
    for section, body in sections.items():
        if section == "overview":
            continue
        for req_text in _split_requirements(body):
            skills = extract_skills_fast(req_text)
            requirements.append({
                "text": req_text,
                "section": section,
                "importance": classify_requirement(req_text, section),
                "skills": [s["name"] for s in skills],
                "years": extract_years_requirement(req_text),
                "education": extract_education_requirement(req_text),
            })
    return {"job_title": title, "sections": sections, "requirements": requirements}


# ---------------------------------------------------------------------------
# Scoring — weighted coverage with field-aware weights + semantic fallback
# ---------------------------------------------------------------------------

def _lexical_hit(requirement_text, resume_lower):
    """Fraction of requirement tokens (>=4 chars) present in the resume."""
    toks = [t for t in re.findall(r"[a-z0-9][a-z0-9+#.\-]{3,}", requirement_text.lower())]
    toks = [t for t in toks if not t.isdigit()]
    if not toks:
        return 1.0
    hits = sum(1 for t in toks if t in resume_lower)
    return hits / len(toks)


def _requirement_match(req, resume_lower, resume_skill_set, resume_years,
                       resume_education, embed):
    """Score one requirement 0..1 and report which fields matched."""
    matched_fields = []
    field_scores = {}

    skills = req.get("skills") or []
    if skills:
        hit = [s for s in skills if s.lower() in resume_skill_set]
        field_scores["skills"] = len(hit) / len(skills)
        if field_scores["skills"] >= 1.0:
            matched_fields.append("skills")
    req_years = req.get("years")
    if req_years:
        field_scores["years"] = 1.0 if (resume_years or 0) >= req_years else 0.0
        if field_scores["years"] >= 1.0:
            matched_fields.append("years")
    edu = req.get("education") or []
    if edu:
        edu_lower = {e.lower() for e in (resume_education or [])}
        hit = [e for e in edu if e.lower() in edu_lower or _edu_alias_hit(e, resume_lower)]
        field_scores["education"] = len(hit) / len(edu)
        if field_scores["education"] >= 1.0:
            matched_fields.append("education")

    semantic_note = None
    if not field_scores:
        # No structured fields: lexical coverage, with optional semantic check.
        lex = _lexical_hit(req["text"], resume_lower)
        sem = None
        if embed is not None:
            try:
                sem = float(embed(req["text"], resume_lower))
            except Exception:
                sem = None
        if sem is not None:
            field_scores["lexical"] = max(lex, 1.0 if sem >= 0.75 else 0.0)
            semantic_note = f"semantic similarity {sem:.2f} vs resume text"
        else:
            field_scores["lexical"] = lex
            semantic_note = ("lexical match only — no semantic embeddings "
                             "configured, so paraphrased equivalents may be missed")
    else:
        # Structured fields present but unmatched: semantic fallback check.
        all_zero = all(v == 0.0 for v in field_scores.values())
        if all_zero and embed is not None:
            try:
                sem = float(embed(req["text"], resume_lower))
            except Exception:
                sem = None
            if sem is not None and sem >= 0.75:
                field_scores["semantic_rescue"] = 1.0
                semantic_note = (f"semantic fallback: similarity {sem:.2f} "
                                 "— requirement may be met under different wording")
            elif sem is not None:
                semantic_note = (f"semantic fallback: similarity {sem:.2f} "
                                 "(below rescue threshold)")

    weighted = sum(_FIELD_WEIGHTS.get(f, 1.0) * v for f, v in field_scores.items())
    norm = sum(_FIELD_WEIGHTS.get(f, 1.0) for f in field_scores)
    score = (weighted / norm) if norm else 0.0
    return min(max(score, 0.0), 1.0), matched_fields, semantic_note


def _edu_alias_hit(edu_label, resume_lower):
    """Loose education alias matching against raw resume text."""
    aliases = {
        "b.tech/b.e.": ["btech", "b.tech", "bachelor of technology", "b.e.", "be "],
        "m.tech/m.e.": ["mtech", "m.tech", "master of technology", "m.e."],
        "master's": ["masters", "master's", "m.sc", "msc", "postgraduate"],
        "bachelor's": ["bachelors", "bachelor's", "b.sc", "bsc", "undergraduate"],
        "phd": ["phd", "ph.d", "doctorate"],
        "mba": ["mba"],
        "diploma": ["diploma"],
    }
    for alias in aliases.get(edu_label.lower(), []):
        if alias.strip() in resume_lower:
            return True
    return False


def score_resume_v2(jd_struct, resume_text, resume_skill_names=None,
                    resume_years=0, resume_education=None, embed=None):
    """Weighted coverage of JD requirements against a resume.

    ``embed`` is an optional callable ``(requirement_text, resume_text) -> float``
    in [0, 1] used as the semantic fallback (see RAG-03 embeddings).
    """
    jd_struct = jd_struct or {}
    requirements = jd_struct.get("requirements") or []
    resume_lower = (resume_text or "").lower()
    # Skill set = caller-provided names UNION taxonomy-extracted skills from
    # the resume text itself (a skill mentioned in the text counts as present).
    resume_skill_set = {s.lower() for s in (resume_skill_names or [])}
    for s in extract_skills_fast(resume_text or ""):
        resume_skill_set.add(s["name"].lower())

    per_req = []
    total_w = 0.0
    covered_w = 0.0
    for req in requirements:
        match, fields, sem_note = _requirement_match(
            req, resume_lower, resume_skill_set, resume_years,
            resume_education or [], embed)
        w = _IMPORTANCE_WEIGHTS.get(req.get("importance", "context"), 1.0)
        total_w += w
        covered_w += w * match
        per_req.append({**req, "match": round(match, 3),
                        "matched_fields": fields, "semantic_note": sem_note})

    overall = (covered_w / total_w) if total_w else 1.0
    score = round(overall * 100, 1)

    must = [r for r in per_req if r["importance"] == "must"]
    nice = [r for r in per_req if r["importance"] == "nice"]
    must_cov = (sum(r["match"] for r in must) / len(must)) if must else 1.0
    nice_cov = (sum(r["match"] for r in nice) / len(nice)) if nice else 1.0

    # Missing must-haves ranked by impact (weight x gap).
    missing = []
    for r in must:
        gap = 1.0 - r["match"]
        if gap <= 0.01:
            continue
        impact = round(_IMPORTANCE_WEIGHTS["must"] * gap, 3)
        missing.append({"requirement": r["text"],
                        "skills": r["skills"],
                        "years": r["years"],
                        "education": r["education"],
                        "impact": impact,
                        "match": r["match"],
                        "how_to_evidence": evidence_suggestion(r)})
    missing.sort(key=lambda m: -m["impact"])

    return {
        "job_title": jd_struct.get("job_title", ""),
        "score": score,
        "coverage": {
            "overall": round(overall, 3),
            "must_have": round(must_cov, 3),
            "nice_to_have": round(nice_cov, 3),
            "n_requirements": len(requirements),
            "n_must": len(must),
            "n_nice": len(nice),
        },
        "per_requirement": per_req,
        "missing_must_haves": missing,
        "semantic_fallback_available": embed is not None,
        "honesty_note": _HONESTY_NOTE,
        "scored_on": date.today().isoformat(),
        "method": ("weighted coverage with field-aware weights; "
                   "semantic fallback " + ("enabled" if embed else "not configured")),
    }


def evidence_suggestion(req):
    """Concrete, honest ways to evidence one missing requirement.

    Returns {"bullet_templates": [...], "project_ideas": [...]} — always
    framed as "only if you genuinely have or will build this".
    """
    skills = req.get("skills") or []
    name = skills[0] if skills else "this requirement"
    bullet_templates = [
        f"Built <project/system> using {name} to <solve what>; <quantified outcome>.",
        f"Applied {name} in <context: internship / freelance / coursework> — "
        f"<what you did>, resulting in <metric>.",
    ]
    project_ideas = [
        f"Ship a small portfolio project using {name} and write up the "
        f"architecture decisions in the README.",
        f"Contribute a {name}-based fix or feature to an open-source repo "
        f"and link the PR on your resume.",
    ]
    if req.get("years"):
        bullet_templates.append(
            f"Date every {name} bullet (e.g. '2023–2025') so the {req['years']}-year "
            f"bar reads clearly to screeners.")
    return {"bullet_templates": bullet_templates, "project_ideas": project_ideas,
            "condition": "Use only if you genuinely have this skill or do the work."}


def match_jd_v2(jd_text, resume_text, resume_skill_names=None,
                resume_years=0, resume_education=None, embed=None):
    """One-call JD v2 match: parse the JD then score the resume."""
    jd_struct = extract_jd_v2(jd_text)
    return score_resume_v2(jd_struct, resume_text, resume_skill_names,
                           resume_years, resume_education, embed)


# ---------------------------------------------------------------------------
# Honest relabel of jd_matcher's screening heuristic (ENG-07 #5)
#
# The roadmap requires: remove `simulate_ai_screen` claims unless backed by
# a documented method, otherwise rename to "Illustrative screening
# checklist". jd_matcher.py now defines `illustrative_screening_checklist`
# directly (renamed by coordinator); this wrapper delegates to it and
# keeps the honest label/disclaimer contract explicit.
# ---------------------------------------------------------------------------

def illustrative_screening_checklist(report, resume_text):
    """Honestly-labeled wrapper around jd_matcher's screening heuristic.

    Same deterministic heuristic as ``jd_matcher.illustrative_screening_checklist``;
    the "Illustrative screening checklist" label and disclaimer make clear
    this does NOT model any real ATS or recruiter decision.
    """
    from .jd_matcher import illustrative_screening_checklist as _screening_heuristic
    result = _screening_heuristic(report, resume_text)
    result["label"] = "Illustrative screening checklist"
    result["honest_label"] = True
    result["disclaimer"] = (
        "Illustrative only — this heuristic checks surface signals "
        "(quantified bullets, action verbs, placeholders) and does not "
        "model any real applicant-tracking system or recruiter decision.")
    # Drop any wording that sounds like a real screening prediction.
    if "verdict" in result:
        result["illustrative_reading"] = result.pop("verdict")
    return result
