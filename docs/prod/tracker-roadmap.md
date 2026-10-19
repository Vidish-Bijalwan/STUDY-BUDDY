# Application tracker roadmap (PROD-05)

## Where we are

The tracker renders a kanban board today. The data layer is now portable:
`studybuddy/prod_tracker.py` provides `export_csv` / `import_csv` with
validation (unknown stages rejected, dates ISO-checked, bad rows reported
not silently dropped).

## Roadmap

### v1 (done)
- CSV export (UTF-8 BOM for Excel) and import with per-row error reporting.
- Canonical stages: `wishlist → applied → oa → interview → offer | rejected`.

### v1.1 — Drag-and-drop
- HTML5 drag-and-drop between columns, with **accessible alternative**:
  every card gets "Move to …" buttons/keyboard controls (UX-03: kanban must
  be keyboard-operable).
- Optimistic UI: move applies instantly, syncs in background; conflict →
  toast + retry (use `templates/partials/states.html` macros).
- Persist order per column (fractional indexing, no full rewrites).

### v1.2 — Reminders & follow-ups
- Per-application `follow_up_on` date (already in the CSV schema).
- Opt-in email nudges via `studybuddy/ux_notify.py` (`application_followup`
  category). No reminders without opt-in.
- Follow-up email templates (copy-paste, no auto-send).

### v1.3 — Depth
- Notes per application (timeline), resume version linked per application
  (already in CSV schema as `resume_version`).
- Funnel analytics: counts per stage, median days-in-stage — computed
  locally, per user (privacy-preserving; see `studybuddy/prod_analytics.py`).

## Non-goals

- Auto-applying to jobs, scraping job boards against their terms, or
  sharing application data across users.
