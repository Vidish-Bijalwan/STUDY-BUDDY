"""Feature 12 ultimate: harsh tests for pattern mastery, mock OA, spaced repetition."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from datetime import UTC, datetime, timedelta

import pytest

from studybuddy.dsa_practice import (
    all_problems,
    mock_oa,
    pattern_mastery,
    spaced_repetition_queue,
)
from tests.mega.harsh_corpus import HARSH_STRINGS


def _ok(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        return True
    except (ValueError, TypeError):
        return True
    except Exception:
        return False


@pytest.mark.parametrize("s", HARSH_STRINGS)
def test_mastery_never_crashes(s):
    assert _ok(pattern_mastery, [s, 1, None])
    assert _ok(pattern_mastery, s)


def test_mastery_rejects_non_list():
    with pytest.raises((ValueError, TypeError)):
        pattern_mastery("nope")


def test_mastery_structure():
    m = pattern_mastery([])
    assert len(m["patterns"]) == 14
    assert all(0 <= p["mastery_pct"] <= 100 for p in m["patterns"])
    assert m["weakest_pattern"]


def test_mastery_counts_solved():
    ids = [p["id"] for p in all_problems()[:10]]
    m = pattern_mastery(ids)
    assert m["overall_mastery_pct"] > 0


@pytest.mark.parametrize("n", [0, 1, 2, 5, -1, "bad", None, 2.5])
def test_oa_never_crashes(n):
    assert _ok(mock_oa, n, 60, seed=1)


def test_oa_structure():
    oa = mock_oa(2, 60, seed=42)
    assert oa["total"] == 2
    assert oa["minutes"] == 60
    assert len(oa["questions"]) == 2
    assert oa["instructions"]


def test_oa_deterministic_seed():
    a = mock_oa(2, 60, seed=7)
    b = mock_oa(2, 60, seed=7)
    assert [q["id"] for q in a["questions"]] == [q["id"] for q in b["questions"]]


def test_oa_clamps():
    assert mock_oa(99)["total"] == 4
    assert mock_oa(2, 999)["minutes"] == 180


@pytest.mark.parametrize("mistakes", [
    [], None, "junk",
    [{"problem_id": "bad", "wrong_at": "not-a-date"}],
    [{"problem_id": 1}],
    [{"no_id": True}],
])
def test_queue_never_crashes(mistakes):
    assert _ok(spaced_repetition_queue, mistakes)


def test_queue_rejects_non_list():
    with pytest.raises((ValueError, TypeError)):
        spaced_repetition_queue("nope")


def test_queue_intervals():
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    q = spaced_repetition_queue([
        {"problem_id": 1, "wrong_at": old, "streak": 1},
        {"problem_id": 2, "wrong_at": old, "streak": 2},
        {"problem_id": 3, "wrong_at": old, "streak": 5},
    ])
    by_id = {e["problem_id"]: e["interval_days"] for e in q["due"]}
    assert by_id[1] == 3 and by_id[2] == 7 and by_id[3] == 14
    assert q["due_count"] == 3


def test_queue_future_not_due():
    recent = datetime.now(UTC).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": recent, "streak": 1}])
    assert q["due_count"] == 0
    assert len(q["upcoming"]) == 1


# ---------------- Feature 12 extended: bank, filtering, hints, diagnosis ----------------

from studybuddy.dsa_practice import (
    difficulties,
    filter_problems,
    get_problem,
    public_problem,
    reveal_approach,
    reveal_hint,
    topics,
    validate_status_payload,
    weak_topic_diagnosis,
)


# ----- all_problems -----

def test_all_problems_count():
    assert len(all_problems()) == 132


def test_all_problems_required_fields():
    for p in all_problems():
        assert p["id"] and p["title"] and p["statement"]
        assert p["difficulty"] in ("Easy", "Medium", "Hard")
        assert isinstance(p["topics"], list) and p["topics"]


def test_all_problems_unique_ids():
    ids = [p["id"] for p in all_problems()]
    assert len(set(ids)) == len(ids)


def test_all_problems_cached():
    assert all_problems() is all_problems()


def test_all_problems_have_hints_and_approach():
    ps = all_problems()
    assert all(isinstance(p.get("hints"), list) for p in ps)
    assert all(p.get("approach") for p in ps)


# ----- get_problem -----

@pytest.mark.parametrize("pid", [
    "dsa-arrays-01", "dsa-arrays-02", "dsa-arrays-03",
])
def test_get_problem_known(pid):
    p = get_problem(pid)
    assert p is not None and p["id"] == pid


@pytest.mark.parametrize("pid", ["no-such-id", "", None, 12345])
def test_get_problem_missing(pid):
    assert get_problem(pid) is None


# ----- topics -----

def test_topics_sorted_desc():
    ts = topics()
    counts = [c for _, c in ts]
    assert counts == sorted(counts, reverse=True)


def test_topics_top_is_arrays():
    assert topics()[0] == ("arrays", 30)


def test_topics_cover_bank():
    assert len(topics()) == 41
    assert sum(c for _, c in topics()) >= len(all_problems())


def test_topics_structure():
    for name, count in topics():
        assert isinstance(name, str) and isinstance(count, int) and count > 0


# ----- difficulties -----

def test_difficulties_exact():
    assert difficulties() == [("Easy", 34), ("Medium", 79), ("Hard", 19)]


def test_difficulties_sum():
    assert sum(c for _, c in difficulties()) == len(all_problems())


def test_difficulties_order():
    assert [d for d, _ in difficulties()] == ["Easy", "Medium", "Hard"]


# ----- filter_problems -----

@pytest.mark.parametrize("topic,expected", [
    ("arrays", 30), ("strings", 21), ("graphs", 15),
    ("dynamic programming", 21), ("hash maps", 21),
])
def test_filter_by_topic(topic, expected):
    out = filter_problems(topic=topic)
    assert len(out) == expected
    assert all(topic in p["topics"] for p in out)


@pytest.mark.parametrize("diff,expected", [
    ("Easy", 34), ("Medium", 79), ("Hard", 19),
])
def test_filter_by_difficulty(diff, expected):
    out = filter_problems(difficulty=diff)
    assert len(out) == expected
    assert all(p["difficulty"] == diff for p in out)


def test_filter_combined():
    out = filter_problems(topic="arrays", difficulty="Easy")
    assert len(out) == 8
    assert all("arrays" in p["topics"] and p["difficulty"] == "Easy" for p in out)


def test_filter_no_match():
    assert filter_problems(topic="zzz-nope") == []
    assert filter_problems(difficulty="Impossible") == []


def test_filter_no_filters_returns_all():
    assert len(filter_problems()) == len(all_problems())


def test_filter_summary_keys():
    out = filter_problems(topic="arrays")
    assert all(set(p.keys()) == {"id", "title", "difficulty", "topics"} for p in out)


# ----- public_problem -----

def test_public_problem_keys():
    pp = public_problem("dsa-arrays-01")
    assert set(pp.keys()) == {
        "id", "title", "statement", "difficulty", "topics", "complexity",
        "pitfalls", "leetcode_url", "total_hints", "hints_revealed",
        "hints", "approach",
    }


def test_public_problem_withholds_hints():
    pp = public_problem("dsa-arrays-01", 0)
    assert pp["hints"] == [] and pp["hints_revealed"] == 0
    assert pp["total_hints"] == 3
    assert pp["approach"] is None


def test_public_problem_partial_reveal():
    pp = public_problem("dsa-arrays-01", 1)
    assert pp["hints_revealed"] == 1 and len(pp["hints"]) == 1


def test_public_problem_over_reveal_clamped():
    pp = public_problem("dsa-arrays-01", 99)
    assert pp["hints_revealed"] == pp["total_hints"] == 3
    assert len(pp["hints"]) == 3


def test_public_problem_missing():
    assert public_problem("zzz-nope") is None


def test_public_problem_passthrough():
    pp = public_problem("dsa-arrays-01")
    assert pp["title"] == "Two Sum"
    assert pp["difficulty"] == "Easy"
    assert "arrays" in pp["topics"]
    assert pp["statement"] and pp["complexity"]


# ----- reveal_hint -----

def test_reveal_hint_first():
    hint, n = reveal_hint("dsa-arrays-01", 0)
    assert hint and n == 1


def test_reveal_hint_progressive():
    n = 0
    seen = []
    for _ in range(5):
        hint, n = reveal_hint("dsa-arrays-01", n)
        if hint is None:
            break
        seen.append(hint)
    assert seen == ["A brute-force double loop works but is O(n^2) - can you do better?",
                    "As you scan, what would you need to remember to check each number instantly?",
                    "Store each value's index in a hash map; for x, look up (target - x)."]
    assert n == 3


def test_reveal_hint_exhausted():
    hint, n = reveal_hint("dsa-arrays-01", 3)
    assert hint is None and n == 3


def test_reveal_hint_beyond_total_unchanged():
    hint, n = reveal_hint("dsa-arrays-01", 999)
    assert hint is None and n == 999


def test_reveal_hint_missing_problem():
    assert reveal_hint("zzz-nope", 0) == (None, 0)


# ----- reveal_approach -----

def test_reveal_approach_content():
    a = reveal_approach("dsa-arrays-01")
    assert isinstance(a, str) and len(a) > 20
    assert "complement" in a.lower()


def test_reveal_approach_missing():
    assert reveal_approach("zzz-nope") is None


@pytest.mark.parametrize("pid", ["dsa-arrays-01", "dsa-arrays-02", "dsa-arrays-03"])
def test_reveal_approach_distinct_from_statement(pid):
    p = get_problem(pid)
    assert reveal_approach(pid) != p["statement"]


# ----- validate_status_payload -----

@pytest.mark.parametrize("status", ["attempted", "solved", "stuck"])
def test_validate_status_ok(status):
    data, err = validate_status_payload({"status": status, "code": "print(1)"})
    assert err is None and data == {"status": status, "code": "print(1)"}


@pytest.mark.parametrize("raw,expected", [
    (" SOLVED ", "solved"), ("Stuck", "stuck"), ("ATTEMPTED", "attempted"),
])
def test_validate_status_normalized(raw, expected):
    data, err = validate_status_payload({"status": raw})
    assert err is None and data["status"] == expected and data["code"] == ""


@pytest.mark.parametrize("payload", [
    {"status": "bad"}, {"status": ""}, {"status": "   "}, {},
    {"status": None},
])
def test_validate_status_rejected(payload):
    data, err = validate_status_payload(payload)
    assert data is None and err == "Status must be one of: attempted, solved, stuck."


def test_validate_status_non_string_raises():
    with pytest.raises(AttributeError):
        validate_status_payload({"status": 123})


def test_validate_status_code_too_long():
    data, err = validate_status_payload({"status": "solved", "code": "x" * 20001})
    assert data is None and err == "Code is too long (max 20000 characters)."


def test_validate_status_code_boundary():
    data, err = validate_status_payload({"status": "solved", "code": "x" * 20000})
    assert err is None and len(data["code"]) == 20000


def test_validate_status_none_payload_raises():
    with pytest.raises(AttributeError):
        validate_status_payload(None)


# ----- weak_topic_diagnosis -----

def test_diagnosis_empty():
    d = weak_topic_diagnosis([])
    assert d["overall"] == {"attempted": 0, "solved": 0, "stuck": 0, "solve_rate": 0.0}
    assert d["topics"] == [] and d["recommendations"] == []


def test_diagnosis_counts():
    ps = all_problems()
    rows = ([{"problem_id": p["id"], "status": "solved"} for p in ps[:5]]
            + [{"problem_id": p["id"], "status": "stuck"} for p in ps[5:7]]
            + [{"problem_id": p["id"], "status": "attempted"} for p in ps[7:9]])
    d = weak_topic_diagnosis(rows)
    assert d["overall"]["solved"] == 5
    assert d["overall"]["stuck"] == 2
    assert d["overall"]["attempted"] == 9
    assert d["overall"]["solve_rate"] == round(5 / 9 * 100, 1)


def test_diagnosis_skips_unknown_ids():
    d = weak_topic_diagnosis([{"problem_id": "nope-xyz", "status": "solved"}])
    assert d["overall"]["attempted"] == 0
    assert d["topics"] == []


def test_diagnosis_weakest_first():
    ps = all_problems()
    rows = ([{"problem_id": p["id"], "status": "solved"} for p in ps[:6]]
            + [{"problem_id": p["id"], "status": "stuck"} for p in ps[6:8]])
    d = weak_topic_diagnosis(rows)
    rates = [t["solve_rate"] for t in d["topics"]]
    assert rates == sorted(rates)


def test_diagnosis_topic_row_keys():
    d = weak_topic_diagnosis([{"problem_id": all_problems()[0]["id"], "status": "solved"}])
    row = d["topics"][0]
    assert set(row.keys()) == {"topic", "attempted", "solved", "stuck",
                               "solve_rate", "stuck_rate"}
    assert row["solve_rate"] == 100.0 and row["stuck_rate"] == 0.0


def test_diagnosis_recommendations_structure():
    ps = all_problems()
    rows = [{"problem_id": p["id"], "status": "stuck"} for p in ps[:4]]
    d = weak_topic_diagnosis(rows)
    assert d["recommendations"]
    for r in d["recommendations"]:
        assert set(r.keys()) == {"problem_id", "title", "difficulty", "reason"}
        assert "Weak topic" in r["reason"]


def test_diagnosis_recommendations_unsolved_and_capped():
    ps = all_problems()
    solved_ids = {p["id"] for p in ps[:10]}
    rows = [{"problem_id": pid, "status": "solved"} for pid in solved_ids]
    rows += [{"problem_id": p["id"], "status": "stuck"} for p in ps[10:14]]
    d = weak_topic_diagnosis(rows)
    assert len(d["recommendations"]) <= 8
    assert all(r["problem_id"] not in solved_ids for r in d["recommendations"])


def test_diagnosis_all_solved_no_weak():
    ps = all_problems()
    d = weak_topic_diagnosis([{"problem_id": p["id"], "status": "solved"} for p in ps])
    assert d["overall"]["solve_rate"] == 100.0


def test_diagnosis_accepts_generator():
    ps = all_problems()
    rows = ({"problem_id": p["id"], "status": "solved"} for p in ps[:3])
    d = weak_topic_diagnosis(rows)
    assert d["overall"]["solved"] == 3


# ----- pattern_mastery (extended) -----

def test_mastery_accepts_tuple():
    m = pattern_mastery(tuple(p["id"] for p in all_problems()[:10]))
    assert m["overall_mastery_pct"] > 0


def test_mastery_int_ids_yield_zero():
    m = pattern_mastery([1, 2, 3])
    assert m["overall_mastery_pct"] == 0.0


def test_mastery_strips_whitespace_ids():
    m = pattern_mastery([" dsa-arrays-01 "])
    hashing = next(p for p in m["patterns"] if p["pattern"] == "Hashing")
    assert hashing["solved"] == 1


def test_mastery_ignores_blanks_and_dupes():
    ids = [p["id"] for p in all_problems()[:10]]
    a = pattern_mastery(ids + ["", "   "])
    b = pattern_mastery(ids + ids)
    assert a["overall_mastery_pct"] == b["overall_mastery_pct"]


def test_mastery_all_solved_is_100():
    m = pattern_mastery([p["id"] for p in all_problems()])
    assert m["overall_mastery_pct"] == 100.0
    assert all(p["mastery_pct"] == 100.0 for p in m["patterns"])
    assert all(p["status"] == "mastered" for p in m["patterns"])


def test_mastery_status_values():
    m = pattern_mastery([])
    assert all(p["status"] == "weak" for p in m["patterns"])
    assert all(p["mastery_pct"] == 0.0 for p in m["patterns"])


def test_mastery_status_thresholds():
    for p in pattern_mastery([])["patterns"]:
        assert p["status"] in ("weak", "progressing", "mastered")


def test_mastery_sorted_ascending():
    m = pattern_mastery([p["id"] for p in all_problems()[:10]])
    pcts = [p["mastery_pct"] for p in m["patterns"]]
    assert pcts == sorted(pcts)
    assert m["weakest_pattern"] == m["patterns"][0]["pattern"]


def test_mastery_guidance_mentions_weakest():
    m = pattern_mastery([])
    assert m["weakest_pattern"] in m["guidance"]


def test_mastery_pattern_keys():
    m = pattern_mastery([])
    for p in m["patterns"]:
        assert set(p.keys()) == {"pattern", "solved", "total", "mastery_pct", "status"}
        assert p["solved"] <= p["total"]


def test_mastery_rejects_tuple_of_wrong_type():
    with pytest.raises((ValueError, TypeError)):
        pattern_mastery({"a": 1})
    with pytest.raises((ValueError, TypeError)):
        pattern_mastery(None)


def test_mastery_partial_progress():
    ps = all_problems()
    m = pattern_mastery([p["id"] for p in ps[:66]])
    assert 0 < m["overall_mastery_pct"] < 100


# ----- mock_oa (extended) -----

@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_oa_counts(n):
    oa = mock_oa(n, 60, seed=1)
    assert oa["total"] == n == len(oa["questions"])


@pytest.mark.parametrize("n,expected", [(0, 1), (-5, 1), (99, 4), (1000, 4), (True, 1)])
def test_oa_count_clamp(n, expected):
    assert mock_oa(n, 60, seed=1)["total"] == expected


@pytest.mark.parametrize("minutes,expected", [(5, 10), (10, 10), (60, 60), (180, 180), (999, 180)])
def test_oa_minutes_clamp(minutes, expected):
    assert mock_oa(2, minutes, seed=1)["minutes"] == expected


def test_oa_bad_minutes_default():
    assert mock_oa(2, "junk", seed=1)["minutes"] == 60
    assert mock_oa(2, None, seed=1)["minutes"] == 60


def test_oa_string_count_coerced():
    assert mock_oa("2", 60, seed=1)["total"] == 2


def test_oa_always_has_medium():
    for seed in range(10):
        qs = mock_oa(2, 60, seed=seed)["questions"]
        assert any(q["difficulty"] == "Medium" for q in qs)


def test_oa_question_keys():
    for q in mock_oa(3, 60, seed=3)["questions"]:
        assert set(q.keys()) == {"id", "title", "difficulty", "topics"}


def test_oa_instructions_mention_limits():
    oa = mock_oa(3, 45, seed=9)
    assert "45 minutes" in oa["instructions"]
    assert "3 questions" in oa["instructions"]


def test_oa_no_seed_works():
    oa = mock_oa(2, 60)
    assert oa["total"] == 2 and len(oa["questions"]) == 2


def test_oa_different_seeds_vary():
    seen = {tuple(q["id"] for q in mock_oa(2, 60, seed=s)["questions"])
            for s in range(20)}
    assert len(seen) > 1


def test_oa_unique_questions():
    for seed in range(10):
        ids = [q["id"] for q in mock_oa(4, 60, seed=seed)["questions"]]
        assert len(set(ids)) == len(ids)


# ----- spaced_repetition_queue (extended) -----

def test_queue_empty():
    q = spaced_repetition_queue([])
    assert q["due"] == [] and q["upcoming"] == []
    assert q["due_count"] == 0
    assert "Nothing due" in q["guidance"]


@pytest.mark.parametrize("streak,expected", [(0, 3), (-3, 3), (1, 3), (2, 7), (3, 14), (5, 14), (100, 14)])
def test_queue_intervals_table(streak, expected):
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": old, "streak": streak}])
    assert q["due"][0]["interval_days"] == expected
    assert q["due"][0]["streak"] == max(1, streak if isinstance(streak, int) else 1)


def test_queue_streak_string_coerced():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": old, "streak": "2"}])
    assert q["due"][0]["interval_days"] == 7


def test_queue_streak_garbage_defaults():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": old, "streak": "junk"}])
    assert q["due"][0]["interval_days"] == 3


def test_queue_missing_wrong_at_is_upcoming():
    q = spaced_repetition_queue([{"problem_id": 1, "streak": 1}])
    assert q["due_count"] == 0 and len(q["upcoming"]) == 1


def test_queue_z_suffix_parsed():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat().replace("+00:00", "Z")
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": old, "streak": 1}])
    assert q["due_count"] == 1


def test_queue_naive_datetime_assumed_utc():
    naive = (datetime.now() - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": naive, "streak": 1}])
    assert q["due_count"] == 1


def test_queue_due_sorted_by_overdue_desc():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([
        {"problem_id": "a", "wrong_at": old, "streak": 2},  # overdue 53
        {"problem_id": "b", "wrong_at": old, "streak": 1},  # overdue 57
    ])
    assert [e["problem_id"] for e in q["due"]] == ["b", "a"]
    assert q["due"][0]["overdue_days"] >= q["due"][1]["overdue_days"]


def test_queue_upcoming_sorted_by_due_at():
    now = datetime.now(UTC).isoformat()
    q = spaced_repetition_queue([
        {"problem_id": "a", "wrong_at": now, "streak": 2},  # due in 7d
        {"problem_id": "b", "wrong_at": now, "streak": 1},  # due in 3d
    ])
    assert [e["problem_id"] for e in q["upcoming"]] == ["b", "a"]


def test_queue_entry_keys():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 7, "wrong_at": old, "streak": 1}])
    e = q["due"][0]
    assert set(e.keys()) == {"problem_id", "streak", "interval_days", "due_at", "overdue_days"}
    assert e["problem_id"] == 7 and e["overdue_days"] > 0


def test_queue_int_and_str_ids():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([
        {"problem_id": 42, "wrong_at": old, "streak": 1},
        {"problem_id": "dsa-arrays-01", "wrong_at": old, "streak": 1},
    ])
    assert q["due_count"] == 2


def test_queue_guidance_when_due():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue([{"problem_id": 1, "wrong_at": old, "streak": 1}])
    assert "1 problem(s) due" in q["guidance"]


def test_queue_tuple_input():
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    q = spaced_repetition_queue(({"problem_id": 1, "wrong_at": old, "streak": 1},))
    assert q["due_count"] == 1


def test_queue_skips_blank_string_id():
    q = spaced_repetition_queue([{"problem_id": "   ", "wrong_at": "x", "streak": 1}])
    assert q["due_count"] == 0 and q["upcoming"] == []
