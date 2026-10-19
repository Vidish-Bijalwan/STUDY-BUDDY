"""ENG-06: Skills taxonomy with aliases, hierarchy, and fast matching.

Replaces the one-regex-per-skill loop in models/skill_extractor.py with a
single compiled alternation regex over all aliases (803 unique aliases).

ARC-14: the taxonomy JSON, the alias/skill indexes, and the compiled regex
used to be module-level ``_FOO = None`` globals mutated with no lock.
They are now lock-protected lazy singletons via :mod:`studybuddy.arc_state`
(``get_or_init``) — identical public API, thread-safe first build, and
resettable in tests via ``arc_state.reset_singleton(...)``.

Public API:
    load_taxonomy()        -> the parsed taxonomy dict
    normalize_skill(text)  -> canonical skill name or None
    extract_skills_fast(text) -> [{"name": ..., "category": ...}, ...]
    get_parent(name)       -> parent skill name or None
    get_related(name)      -> list of related skill names
    get_category(name)     -> category string or None
"""
import json
import os
import re

from studybuddy.arc_state import get_or_init

_TAXONOMY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "taxonomy", "skills_taxonomy.json")

# ARC-14 singleton keys (stable — tests reset by these keys).
_TAXONOMY_KEY = "skills_taxonomy.taxonomy"
_INDEXES_KEY = "skills_taxonomy.indexes"
_REGEX_KEY = "skills_taxonomy.compiled_re"


def _load_taxonomy_file():
    """Factory: parse the taxonomy JSON (runs once per process)."""
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_taxonomy():
    """Load (and cache) the taxonomy JSON."""
    return get_or_init(_TAXONOMY_KEY, _load_taxonomy_file)


def _build_indexes_data():
    """Factory: build alias->canonical and canonical->entry index dicts."""
    tax = load_taxonomy()
    alias_index = {}
    skill_index = {}
    for skill in tax["skills"]:
        name = skill["name"]
        skill_index[name] = skill
        for alias in skill["aliases"]:
            # first writer wins (deterministic, CSV order)
            alias_index.setdefault(alias.lower(), name)
    return {"alias": alias_index, "skill": skill_index}


def _indexes():
    """Return the (alias_index, skill_index) singleton pair."""
    data = get_or_init(_INDEXES_KEY, _build_indexes_data)
    return data["alias"], data["skill"]


def _build_regex_data():
    """Factory: compile the one-regex alternation over all aliases."""
    alias_index, _ = _indexes()
    # longest-first so "react.js" beats "react", "c++" beats "c"
    aliases = sorted(alias_index.keys(), key=len, reverse=True)
    pattern = (r"(?<![a-zA-Z0-9+#.])("
               + "|".join(re.escape(a) for a in aliases)
               + r")(?![a-zA-Z0-9])")
    return re.compile(pattern, re.IGNORECASE)


def _compiled_regex():
    """Return the cached compiled skill-matching regex."""
    return get_or_init(_REGEX_KEY, _build_regex_data)


# Backward-compat alias: pre-existing tests (tests/test_skills_taxonomy.py)
# call the old internal name. Same behavior — returns the single compiled
# alternation regex (ARC-14 only changed how it is cached, not what it is).
_build_regex = _compiled_regex


def normalize_skill(text):
    """Map any alias/variant to the canonical skill name. None if unknown.

    >>> normalize_skill("reactjs")
    'React'
    >>> normalize_skill("  REACT.JS  ")
    'React'
    >>> normalize_skill("not-a-real-skill-xyz") is None
    True
    """
    if not text or not isinstance(text, str):
        return None
    alias_index, _ = _indexes()
    return alias_index.get(text.strip().lower())


def extract_skills_fast(text):
    """Extract skills with ONE compiled regex (not one per skill).

    Returns a list of {"name", "category"} dicts with canonical names,
    sorted by category then name — same shape as
    models.skill_extractor.extract_skills for drop-in compatibility.
    """
    if not text:
        return []
    rx = _compiled_regex()
    alias_index, skill_index = _indexes()
    found = {}
    for m in rx.finditer(text):
        canonical = alias_index.get(m.group(1).lower())
        if canonical:
            entry = skill_index[canonical]
            found[canonical] = entry["category"]
    result = [{"name": name, "category": cat}
              for name, cat in found.items()]
    result.sort(key=lambda x: (x["category"], x["name"]))
    return result


def get_parent(name):
    """Return the parent skill name, or None."""
    _, skill_index = _indexes()
    entry = skill_index.get(name)
    return entry.get("parent") if entry else None


def get_related(name):
    """Return related skill names (may be empty)."""
    _, skill_index = _indexes()
    entry = skill_index.get(name)
    return list(entry.get("related", [])) if entry else []


def get_category(name):
    """Return the category of a canonical skill name, or None."""
    _, skill_index = _indexes()
    entry = skill_index.get(name)
    return entry.get("category") if entry else None
