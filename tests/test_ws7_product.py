"""WS7-PRODUCT tests: UX/DATA/PROD/OSS items (v1)."""
import json
import time

import pytest

from studybuddy import (
    api_keys,
    i18n,
    oss_share,
    prod_analytics,
    prod_gating,
    prod_packs,
    prod_tracker,
    ux_explain,
    ux_export,
    ux_notify,
)

SECRET = "ws7-test-secret"


# ---------------------------------------------------------------- i18n
class TestI18n:
    def test_module_loads_without_flask_babel(self):
        assert i18n.DEFAULT_LOCALE == "en"
        assert "hi" in i18n.SUPPORTED_LOCALES

    def test_hindi_catalog_exists(self):
        assert "hi" in i18n.available_locales()

    def test_translate_hindi(self):
        assert i18n.translate("Analyze resume", locale="hi") == "रिज़्यूमे का विश्लेषण करें"

    def test_translate_fallback_english(self):
        assert i18n.translate("Analyze resume", locale="en") == "Analyze resume"
        assert i18n.translate("No such string", locale="hi") == "No such string"

    def test_resolve_locale(self):
        assert i18n.resolve_locale(lang_param="hi") == "hi"
        assert i18n.resolve_locale(lang_param="xx") == "en"
        assert i18n.resolve_locale(accept_language="hi-IN,hi;q=0.9") == "hi"

    def test_init_babel_lazy_no_crash(self):
        # No Flask-Babel installed in this env -> returns None, never raises.
        assert i18n.init_babel(object()) is None

    def test_format_inr_lpa(self):
        assert "L/yr" in i18n.format_inr_lpa(12.5)
        assert "Cr/yr" in i18n.format_inr_lpa(150)


# ---------------------------------------------------------------- explain
class TestExplain:
    def test_fixture_validates(self):
        assert ux_explain.validate_explanation(ux_explain.fixture_report()) == []

    def test_weights_sum_to_100(self):
        assert sum(p["weight"] for p in ux_explain.READINESS_PILLARS) == 100

    def test_render_html_escapes_and_has_details(self):
        html = ux_explain.render_explanation_html(ux_explain.fixture_report())
        assert "<details" in html and "Why this score" in html
        assert "vivek@example.com" in html

    def test_render_html_escapes_xss(self):
        report = ux_explain.fixture_report()
        report["pillars"][0]["findings"][0]["evidence_span"] = "<script>alert(1)</script>"
        html = ux_explain.render_explanation_html(report)
        assert "<script>" not in html

    def test_pillar_summary(self):
        s = ux_explain.pillar_summary(ux_explain.fixture_report()["pillars"][0])
        assert s["n_deductions"] == 1 and "single-column-layout" in s["deduction_rules"]

    def test_validate_catches_bad_weights(self):
        report = ux_explain.fixture_report()
        report["pillars"][0]["weight"] = 10
        assert any("100" in p for p in ux_explain.validate_explanation(report))


# ---------------------------------------------------------------- export
class TestExport:
    def test_markdown_export(self):
        md = ux_export.export_report_markdown(ux_explain.fixture_report())
        assert md.startswith("# Resume Readiness Report")
        assert "Parseability" in md and "heuristic" in md

    def test_pdf_export_valid_header(self):
        pdf = ux_export.export_report_pdf(ux_explain.fixture_report())
        assert pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")

    def test_share_token_roundtrip(self):
        token = ux_export.create_share_token(SECRET, "rep-123")
        assert ux_export.verify_share_token(SECRET, token) == "rep-123"

    def test_share_token_expiry(self):
        token = ux_export.create_share_token(SECRET, "rep-1", ttl_hours=0)
        time.sleep(0.05)
        assert ux_export.verify_share_token(SECRET, token) is None

    def test_share_token_revoke(self):
        store = ux_export.RevocationList()
        token = ux_export.create_share_token(SECRET, "rep-9")
        assert ux_export.verify_share_token(SECRET, token, revoked=store.is_revoked) == "rep-9"
        store.revoke(token)
        assert ux_export.verify_share_token(SECRET, token, revoked=store.is_revoked) is None

    def test_share_token_tampered(self):
        token = ux_export.create_share_token(SECRET, "rep-1")
        assert ux_export.verify_share_token(SECRET, token + "x") is None

    def test_template_passes_parser(self):
        text = (
            "Aarav Sharma\n"
            "aarav@example.com\n"
            "+91 98765 43210\n"
            "Experience\nBuilt an API serving 2000 requests per day.\n"
            "Education\nB.Tech, 2024\n"
            "Skills\nPython, Flask\n"
        )
        res = ux_export.template_passes_parser(text)
        assert res["ok"] and not res["missing"]


# ---------------------------------------------------------------- notify
class TestNotify:
    def test_defaults_all_off(self):
        prefs = ux_notify.NotificationPrefs(user_id=1, email="a@b.c")
        assert not any(prefs.is_on(c) for c in ux_notify.CATEGORIES)

    def test_opt_in_and_unsubscribe_all(self):
        prefs = ux_notify.NotificationPrefs(user_id=1, email="a@b.c")
        prefs.set("streak_nudge", True)
        assert prefs.is_on("streak_nudge")
        prefs.unsubscribe_all()
        assert not prefs.is_on("streak_nudge")

    def test_marketing_requires_verified_email(self):
        prefs = ux_notify.NotificationPrefs(user_id=1, email="a@b.c")
        with pytest.raises(ValueError):
            prefs.set("announcements", True)
        prefs.email_verified = True
        prefs.set("announcements", True)
        assert prefs.is_on("announcements")

    def test_unknown_category_rejected(self):
        prefs = ux_notify.NotificationPrefs(user_id=1)
        with pytest.raises(KeyError):
            prefs.set("spam", True)

    def test_unsubscribe_token_roundtrip(self):
        token = ux_notify.make_unsubscribe_token(SECRET, 42)
        assert ux_notify.verify_unsubscribe_token(SECRET, token) == "42"
        assert ux_notify.verify_unsubscribe_token(SECRET, "bogus") is None

    def test_maybe_notify_respects_opt_out(self):
        provider = ux_notify.EmailProviderStub()
        prefs = ux_notify.NotificationPrefs(user_id=1, email="a@b.c")
        assert (
            ux_notify.maybe_notify(
                provider, prefs, category="streak_nudge", subject="s",
                text_body="b", unsubscribe_base_url="https://x/unsub", secret_key=SECRET,
            )
            is None
        )
        prefs.set("streak_nudge", True)
        out = ux_notify.maybe_notify(
            provider, prefs, category="streak_nudge", subject="s",
            text_body="b", unsubscribe_base_url="https://x/unsub", secret_key=SECRET,
        )
        assert out and "Unsubscribe:" in out["text_body"]


# ---------------------------------------------------------------- gating
class TestGating:
    def test_below_threshold_not_ready(self):
        assert not prod_gating.community_ready(verified_mentors=3, weekly_active_peers=10)

    def test_at_threshold_ready(self):
        assert prod_gating.community_ready(
            verified_mentors=prod_gating.MIN_VERIFIED_MENTORS,
            weekly_active_peers=prod_gating.MIN_WEEKLY_ACTIVE_PEERS,
        )

    def test_empty_state_copy_honest(self):
        copy = prod_gating.empty_state("mentors", n=10)
        assert "Be the first mentor" in copy["title"]
        assert "verified mentors" in copy["body"]

    def test_sample_profile_labeling(self):
        assert prod_gating.sample_profile_label({"name": "Seed"}) == "Sample profile"
        assert prod_gating.sample_profile_label({"verified": True}) == "Verified"
        # A seed must NEVER be labelled verified.
        assert prod_gating.sample_profile_label({"seed": True, "verified": False}) != "Verified"

    def test_visible_features_hidden_until_ready(self):
        feats = prod_gating.visible_features(verified_mentors=0, weekly_active_peers=0)
        assert feats["mentor_booking"] is False and feats["solo_practice"] is True


# ---------------------------------------------------------------- packs
class TestPacks:
    def test_load_pack_valid_role_profile(self, tmp_path):
        d = tmp_path / "backend"
        d.mkdir()
        (d / "pack.yaml").write_text(
            "name: backend-pack\nversion: '1.0'\nkind: role_profile\nlicense: CC0-1.0\n"
        )
        (d / "data.json").write_text(json.dumps({"title": "Backend Dev", "skills": ["Python"]}))
        res = prod_packs.load_pack(d)
        assert res["errors"] == [] and res["manifest"]["kind"] == "role_profile"

    def test_load_pack_rejects_unknown_kind(self, tmp_path):
        d = tmp_path / "evil"
        d.mkdir()
        (d / "pack.yaml").write_text(
            "name: x\nversion: '1.0'\nkind: plugin\nlicense: CC0-1.0\n"
        )
        res = prod_packs.load_pack(d)
        assert any("unknown kind" in e for e in res["errors"])

    def test_load_pack_rejects_missing_manifest(self, tmp_path):
        res = prod_packs.load_pack(tmp_path)
        assert res["errors"]

    def test_question_bank_dupe_ids_rejected(self, tmp_path):
        d = tmp_path / "qb"
        d.mkdir()
        (d / "pack.yaml").write_text(
            "name: q\nversion: '1.0'\nkind: question_bank\nlicense: CC0-1.0\n"
        )
        (d / "data.yaml").write_text("- id: q1\n  question: What?\n- id: q1\n  question: What again?\n")
        res = prod_packs.load_pack(d)
        assert any("duplicate id" in e for e in res["errors"])

    def test_no_code_execution_yaml_safe(self, tmp_path):
        d = tmp_path / "tricky"
        d.mkdir()
        (d / "pack.yaml").write_text(
            "name: t\nversion: '1.0'\nkind: skill_aliases\nlicense: CC0-1.0\n"
        )
        (d / "data.yaml").write_text("x: !!python/object/apply:os.system ['echo pwned']\n")
        res = prod_packs.load_pack(d)
        assert res["errors"]  # safe_load must refuse the python object tag

    def test_load_all_packs_empty_dir(self, tmp_path):
        assert prod_packs.load_all_packs(tmp_path) == {}


# ---------------------------------------------------------------- share card
class TestShareCard:
    def test_requires_opt_in(self):
        with pytest.raises(PermissionError):
            oss_share.build_score_card(ux_explain.fixture_report(), opt_in=False)

    def test_card_has_no_pii(self):
        card = oss_share.build_score_card(ux_explain.fixture_report(), opt_in=True)
        assert set(card) >= {"project", "score", "pillars", "generated_at"}
        assert oss_share.assert_no_pii(card, ux_explain.fixture_report()) == []


# ---------------------------------------------------------------- tracker
class TestTracker:
    def test_export_import_roundtrip(self):
        apps = [{"company": "Acme", "role": "SDE", "stage": "applied",
                 "applied_on": "2026-10-01", "source": "", "notes": "",
                 "resume_version": "v3", "follow_up_on": "2026-10-08"}]
        result = prod_tracker.import_csv(prod_tracker.export_csv(apps))
        assert result["errors"] == [] and result["rows"][0]["company"] == "Acme"

    def test_import_rejects_bad_rows_not_silently(self):
        text = "company,role,stage,applied_on\n,Dev,applied,2026-10-01\nAcme,Dev,bogus,not-a-date\n"
        result = prod_tracker.import_csv(text)
        assert result["rows"] == [] and len(result["errors"]) == 3


# ---------------------------------------------------------------- api keys
class TestApiKeys:
    def test_create_verify_revoke(self):
        store = api_keys.ApiKeyStore()
        kid, raw = store.create("partner", rate_per_minute=30)
        rec = store.verify(raw)
        assert rec is not None and rec.name == "partner"
        assert store.verify("sb_bogus") is None
        assert store.revoke(kid) and store.verify(raw) is None

    def test_raw_key_never_stored(self):
        store = api_keys.ApiKeyStore()
        _, raw = store.create("x")
        assert all(raw not in r.key_hash for r in store._records.values())

    def test_rate_limiter(self):
        limiter = api_keys.RateLimiter()
        ok, _ = limiter.check("k1", 2)
        assert ok
        ok, _ = limiter.check("k1", 2)
        assert ok
        ok, wait = limiter.check("k1", 2)
        assert not ok and wait > 0


# ---------------------------------------------------------------- analytics
class TestAnalytics:
    def test_streak_forgiving(self):
        stats = prod_analytics.streak_stats(
            ["2026-10-10", "2026-10-11", "2026-10-13"], today="2026-10-13"
        )
        assert stats["current"] == 3  # one missed day forgiven

    def test_streak_lapsed(self):
        stats = prod_analytics.streak_stats(["2026-10-01"], today="2026-10-13")
        assert stats["current"] == 0 and stats["best"] == 1

    def test_weak_topics(self):
        attempts = [{"topic": "arrays", "correct": True}] * 5 + [
            {"topic": "dp", "correct": False},
            {"topic": "dp", "correct": True},
            {"topic": "dp", "correct": False},
        ]
        weak = prod_analytics.weak_topics(attempts)
        assert weak[0]["topic"] == "dp"

    def test_export_user_analytics_shape(self):
        out = prod_analytics.export_user_analytics(7, history={})
        assert set(out) >= {"user_id", "readiness_over_time", "streak", "weak_topics"}
