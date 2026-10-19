"""Typed Ultimate Lab tool registry — ARC-05.

Phase 1 of dismantling the dynamic ``ultimate_reg_a/b/c`` + ``importlib`` /
``getattr`` dispatcher in ``ultimate_routes.py``:

* The 20 most-used tools are **schema-wrapped**: every tool has a pydantic
  input model, an explicit handler registered in :data:`TOOL_HANDLERS`
  (plain direct imports — no ``importlib`` / ``getattr`` on user input), and
  auth + rate-limit metadata.
* The remaining 71 tools stay on the legacy dict registry, marked
  ``legacy-unmigrated`` in ``docs/labs-inventory.csv`` (owner TBD) until they
  are promoted/merged/retired per the ARC-05 procedure.

Use :func:`run_typed_tool` for migrated tools; it mirrors the legacy
``run_tool(tool_id, payload) -> (result, error)`` contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, BeforeValidator, Field, ValidationError
from typing_extensions import Annotated

# ---------------------------------------------------------------------------
# Explicit backend imports — the allowlist. Adding a tool means adding an
# import + a ToolHandler entry below. Nothing here is resolved from strings.
# ---------------------------------------------------------------------------
from studybuddy.bullet_rewriter import (  # noqa: E402
    metric_finder,
    star_convert,
    verb_power_report,
)
from studybuddy.career_assessment import ai_role_fit  # noqa: E402
from studybuddy.cert_guide import cert_roi  # noqa: E402
from studybuddy.communication_coach import clarity_score  # noqa: E402
from studybuddy.cover_generator import outreach_score  # noqa: E402
from studybuddy.dsa_practice import pattern_mastery  # noqa: E402
from studybuddy.github_integration import grade_readme  # noqa: E402
from studybuddy.jd_matcher import (  # noqa: E402
    competitiveness_checklist,
    illustrative_screening_checklist,
    keyword_action_plan,
)
from studybuddy.learning_roadmaps import weekly_planner  # noqa: E402
from studybuddy.linkedin_grader import recruiter_search_check  # noqa: E402
from studybuddy.mock_interview import voice_interview_prep  # noqa: E402
from studybuddy.pdf_qa import qa_to_notes  # noqa: E402
from studybuddy.aptitude_test import pick_questions as aptitude_pick  # noqa: E402
from studybuddy.aptitude_test import score_attempt as aptitude_score  # noqa: E402
from studybuddy.portfolio import check_demo_links  # noqa: E402
from studybuddy.salary_data import evaluate_offer  # noqa: E402
from studybuddy.skill_quizzes import weakness_drill  # noqa: E402
from studybuddy.star_builder import story_bank_manager  # noqa: E402


# ---------------------------------------------------------------------------
# Coercion helpers — accept what the legacy dispatcher accepted.
# ---------------------------------------------------------------------------
def _as_json_list(v: Any) -> list:
    """Accept a JSON string, a newline/comma-separated string, or a list."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except (ValueError, TypeError):
            pass
        if "\n" in s:
            return [ln.strip() for ln in s.splitlines() if ln.strip()]
        return [p.strip() for p in s.split(",") if p.strip()]
    return [v]


def _as_json_value(v: Any) -> Any:
    """Accept an already-parsed value or a JSON string."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (ValueError, TypeError):
            return v
    return v


JsonList = Annotated[list, BeforeValidator(_as_json_list)]
JsonValue = Annotated[Any, BeforeValidator(_as_json_value)]


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
class ToolMeta(BaseModel):
    """Per-tool contract metadata (ARC-05 acceptance criteria)."""

    tool_id: str
    feature: str
    name: str
    description: str = ""
    requires_login: bool = True  # SEC-01: Lab tools require auth
    rate_limit: str = "60 per hour"
    needs_network: bool = False
    uses_llm: bool = False
    reads_db: bool = False
    writes_db: bool = False
    data_source: str = "user input (rule-based)"
    owner: str = "study-buddy-core"
    status: str = "migrated"  # or "legacy-unmigrated"


class ToolOutput(BaseModel):
    """Outputs are JSON-safe dicts (schemas vary per tool; v1 pragmatic)."""

    model_config = {"extra": "allow"}

    def jsonable(self) -> dict:
        data = self.model_dump()
        # ensure JSON-serialisable
        return json.loads(json.dumps(data, default=str))


@dataclass
class ToolHandler:
    """One allowlisted tool: schema + direct function reference."""

    meta: ToolMeta
    input_model: type[BaseModel]
    fn: Callable[..., Any]
    extra_kwargs: dict = field(default_factory=dict)

    def run(self, payload: dict) -> tuple[Optional[dict], Optional[str]]:
        try:
            validated = self.input_model.model_validate(payload)
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first["loc"])
            return None, f"Field '{loc}': {first['msg']}."
        try:
            result = self.fn(**validated.model_dump(), **self.extra_kwargs)
        except (ValueError, TypeError) as exc:
            return None, str(exc) or "Invalid input."
        except Exception as exc:  # never leak tracebacks
            return None, f"Tool failed: {type(exc).__name__}."
        try:
            return json.loads(json.dumps(result, default=str)), None
        except (ValueError, TypeError):
            return None, "Tool returned a non-serialisable result."


# ---------------------------------------------------------------------------
# Input schemas (top-20 tools)
# ---------------------------------------------------------------------------
class _NonEmpty(BaseModel):
    model_config = {"extra": "forbid"}


class PrescreenIn(_NonEmpty):
    resume_text: str = Field(min_length=1, max_length=60000)
    report: JsonValue


class KeywordPlanIn(_NonEmpty):
    resume_text: str = Field(min_length=1, max_length=60000)
    report: JsonValue


class OfferOddsIn(_NonEmpty):
    report: JsonValue
    applicants_estimate: Optional[int] = Field(default=None, ge=0)


class StarConvertIn(_NonEmpty):
    bullet_text: str = Field(min_length=1, max_length=2000)


class VerbPowerIn(_NonEmpty):
    bullets: JsonList


class MetricFinderIn(_NonEmpty):
    bullet_text: str = Field(min_length=1, max_length=2000)


class OutreachScoreIn(_NonEmpty):
    message: str = Field(min_length=1, max_length=10000)
    recipient_name: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)


class SearchCheckIn(_NonEmpty):
    headline: str = Field(min_length=1, max_length=500)
    about: str = Field(min_length=1, max_length=5000)
    skills: str = Field(min_length=1, max_length=2000)
    target_queries: JsonList


class ReadmeGradeIn(_NonEmpty):
    readme_text: str = Field(min_length=1, max_length=60000)


class AiFitIn(_NonEmpty):
    user_skills: JsonList


class SalaryEvaluateIn(_NonEmpty):
    role: str = Field(min_length=1, max_length=200)
    tier: str = Field(min_length=1, max_length=100)
    band: str = Field(min_length=1, max_length=100)
    offer_lpa: float = Field(ge=0, le=1000)


class LinkCheckIn(_NonEmpty):
    projects: JsonValue


class VoicePrepIn(_NonEmpty):
    question: JsonValue
    answer_text: str = Field(min_length=1, max_length=20000)
    seconds_taken: int = Field(ge=0, le=3600)


class PatternMasteryIn(_NonEmpty):
    solved_ids: JsonList
    attempted_ids: JsonList = Field(default_factory=list)


class ClarityScoreIn(_NonEmpty):
    transcript: str = Field(min_length=1, max_length=60000)


class StoryBankIn(_NonEmpty):
    stories: JsonValue


class WeeklyPlannerIn(_NonEmpty):
    roadmap_stages: JsonValue
    hours_per_week: int = Field(default=6, ge=1, le=80)


class WeaknessDrillIn(_NonEmpty):
    skill: str = Field(min_length=1, max_length=200)
    past_results: JsonValue
    n: int = Field(default=10, ge=1, le=50)


class CertRoiIn(_NonEmpty):
    cert_id: str = Field(min_length=1, max_length=200)
    current_lpa: float = Field(ge=0, le=1000)


class QaToNotesIn(_NonEmpty):
    qa_pairs: JsonValue
    title: str = Field(default="Study Notes", max_length=300)


class AptitudePickIn(_NonEmpty):
    category: Optional[str] = Field(default=None, max_length=50)
    n: int = Field(default=10, ge=1, le=50)
    seed: Optional[int] = Field(default=None)


class AptitudeScoreIn(_NonEmpty):
    question_ids: list[str] = Field(min_length=1, max_length=50)
    answers: dict[str, str]


def _meta(tool_id: str, feature: str, name: str, **kw: Any) -> ToolMeta:
    return ToolMeta(tool_id=tool_id, feature=feature, name=name, **kw)


# ---------------------------------------------------------------------------
# The allowlist: tool_id -> handler. Dispatch goes through this dict ONLY.
# ---------------------------------------------------------------------------
TOOL_HANDLERS: dict[str, ToolHandler] = {}


def _reg(meta: ToolMeta, input_model: type[BaseModel], fn: Callable[..., Any]) -> None:
    TOOL_HANDLERS[meta.tool_id] = ToolHandler(
        meta=meta, input_model=input_model, fn=fn
    )


_reg(_meta("jd/prescreen", "JD-Matched ATS Scoring", "Illustrative Screening Checklist"),
     PrescreenIn, illustrative_screening_checklist)
_reg(_meta("jd/keyword-plan", "JD-Matched ATS Scoring", "Missing-Keyword Action Plan"),
     KeywordPlanIn, keyword_action_plan)
_reg(_meta("jd/offer-odds", "JD-Matched ATS Scoring", "Competitiveness Checklist"),
     OfferOddsIn, competitiveness_checklist)
_reg(_meta("bullets/star-convert", "AI Bullet Rewriter", "STAR Auto-Converter"),
     StarConvertIn, star_convert)
_reg(_meta("bullets/verb-power", "AI Bullet Rewriter", "Verb Power Ranking"),
     VerbPowerIn, verb_power_report)
_reg(_meta("bullets/metric-finder", "AI Bullet Rewriter", "Metric Finder"),
     MetricFinderIn, metric_finder)
_reg(_meta("outreach/score", "Outreach", "Outreach Score"),
     OutreachScoreIn, outreach_score)
_reg(_meta("linkedin/search-check", "LinkedIn Grader", "Recruiter Search Check"),
     SearchCheckIn, recruiter_search_check)
_reg(_meta("github/readme-grade", "GitHub Integration", "README Grade",
           needs_network=False, data_source="user input (rule-based)"),
     ReadmeGradeIn, grade_readme)
_reg(_meta("assessment/ai-fit", "Career Assessment", "AI Role Fit"),
     AiFitIn, ai_role_fit)
_reg(_meta("salary/evaluate", "Salary Data", "Evaluate Offer",
           data_source="curated JSON"),
     SalaryEvaluateIn, evaluate_offer)
_reg(_meta("portfolio/link-check", "Portfolio", "Check Demo Links",
           needs_network=True, rate_limit="30 per hour",
           data_source="live HTTP fetch"),
     LinkCheckIn, check_demo_links)
_reg(_meta("mock/voice-prep", "Mock Interview", "Voice Interview Prep"),
     VoicePrepIn, voice_interview_prep)
_reg(_meta("dsa/pattern-mastery", "DSA Practice", "Pattern Mastery"),
     PatternMasteryIn, pattern_mastery)
_reg(_meta("coach/clarity-score", "Communication Coach", "Clarity Score"),
     ClarityScoreIn, clarity_score)
_reg(_meta("star/story-bank", "STAR Builder", "Story Bank Manager"),
     StoryBankIn, story_bank_manager)
_reg(_meta("roadmaps/weekly-planner", "Learning Roadmaps", "Weekly Planner"),
     WeeklyPlannerIn, weekly_planner)
_reg(_meta("quizzes/weakness-drill", "Skill Quizzes", "Weakness Drill"),
     WeaknessDrillIn, weakness_drill)
_reg(_meta("certs/roi", "Cert Guide", "Cert ROI", data_source="curated JSON"),
     CertRoiIn, cert_roi)
_reg(_meta("pdfqa/qa-to-notes", "PDF Q&A", "Q&A to Notes"),
     QaToNotesIn, qa_to_notes)
_reg(_meta("aptitude/pick-questions", "Aptitude Test", "Pick Questions",
           data_source="curated JSON (338 questions)"),
     AptitudePickIn, aptitude_pick)
_reg(_meta("aptitude/score", "Aptitude Test", "Score Attempt",
           data_source="curated JSON"),
     AptitudeScoreIn, aptitude_score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def is_migrated(tool_id: str) -> bool:
    """True when tool_id dispatches through the typed allowlist."""
    return tool_id in TOOL_HANDLERS


def migrated_tool_ids() -> list[str]:
    return sorted(TOOL_HANDLERS)


def run_typed_tool(
    tool_id: str, payload: dict
) -> tuple[Optional[dict], Optional[str]]:
    """Run a migrated tool. Returns (result_dict, None) or (None, error).

    Unknown ids are REJECTED — there is no fallback to dynamic dispatch.
    """
    handler = TOOL_HANDLERS.get(tool_id)
    if handler is None:
        return None, f"Unknown tool '{tool_id}'."
    if not isinstance(payload, dict):
        return None, "Request body must be a JSON object."
    return handler.run(payload)


__all__ = [
    "TOOL_HANDLERS",
    "ToolHandler",
    "ToolMeta",
    "is_migrated",
    "migrated_tool_ids",
    "run_typed_tool",
]
