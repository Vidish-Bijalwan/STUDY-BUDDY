"""Community gating by real supply (PROD-06, decision D-9).

Until at least N verified mentors and M weekly active peers exist, mentor
booking and peer rooms stay hidden; seeded profiles are labelled
"Sample profile" (never "verified"); empty states are honest.
"""
from __future__ import annotations

#: D-9 thresholds.
MIN_VERIFIED_MENTORS = 10
MIN_WEEKLY_ACTIVE_PEERS = 50


def community_ready(*, verified_mentors: int, weekly_active_peers: int) -> bool:
    return (
        verified_mentors >= MIN_VERIFIED_MENTORS
        and weekly_active_peers >= MIN_WEEKLY_ACTIVE_PEERS
    )


def gate_status(*, verified_mentors: int, weekly_active_peers: int) -> dict:
    ready = community_ready(
        verified_mentors=verified_mentors, weekly_active_peers=weekly_active_peers
    )
    return {
        "ready": ready,
        "verified_mentors": verified_mentors,
        "weekly_active_peers": weekly_active_peers,
        "needed_mentors": max(0, MIN_VERIFIED_MENTORS - verified_mentors),
        "needed_peers": max(0, MIN_WEEKLY_ACTIVE_PEERS - weekly_active_peers),
    }


#: Honest empty-state copy per feature.
EMPTY_STATE_COPY: dict[str, dict[str, str]] = {
    "mentors": {
        "title": "Be the first mentor",
        "body": (
            "Mentor bookings open once {n} verified mentors join. "
            "Community features launch with real people, not placeholders."
        ),
        "cta": "Apply as a mentor",
    },
    "peer_rooms": {
        "title": "Peer rooms open soon",
        "body": (
            "Mock-interview rooms open once {m} learners are active each week. "
            "Practice solo meanwhile — flashcards and quizzes are ready now."
        ),
        "cta": "Practice solo",
    },
}


def empty_state(feature: str, **fmt) -> dict[str, str]:
    copy = EMPTY_STATE_COPY.get(feature, {})
    return {k: v.format(**fmt) for k, v in copy.items()}


def sample_profile_label(profile: dict) -> str:
    """Return the honesty label for a profile dict.

    Seeded/sample profiles MUST be labelled "Sample profile"; only profiles
    with explicit verified=True may show "Verified".
    """
    if profile.get("verified") is True:
        return "Verified"
    return "Sample profile"


def visible_features(*, verified_mentors: int, weekly_active_peers: int) -> dict[str, bool]:
    """Feature visibility map the templates consume."""
    ready = community_ready(
        verified_mentors=verified_mentors, weekly_active_peers=weekly_active_peers
    )
    return {
        "mentor_booking": ready,
        "mentor_directory_seed": True,  # visible but labelled "Sample profile"
        "peer_rooms": ready,
        "solo_practice": True,
    }


def gating_wiring_snippet() -> str:
    return (
        "from studybuddy.prod_gating import gate_status, visible_features, sample_profile_label\n"
        "ctx = gate_status(verified_mentors=n_mentors, weekly_active_peers=wau)\n"
        "# hide booking links when not ctx['ready']; label seeds via sample_profile_label(p)\n"
    )


__all__ = [
    "MIN_VERIFIED_MENTORS",
    "MIN_WEEKLY_ACTIVE_PEERS",
    "community_ready",
    "gate_status",
    "empty_state",
    "sample_profile_label",
    "visible_features",
    "gating_wiring_snippet",
]
