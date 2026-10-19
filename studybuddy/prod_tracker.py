"""Application tracker CSV import/export (PROD-05).

v1 of the kanban drag-and-drop story: the tracker already renders a board;
this module adds the portable layer (export/import) with validation, so users
can back up their data and migrate. Accessible DnD controls ship with the UI
work; these helpers are the data contract for it.
"""
from __future__ import annotations

import csv
import io
from datetime import date

#: Canonical columns. Unknown columns are ignored on import (forward compat).
CSV_COLUMNS = (
    "company",
    "role",
    "stage",
    "applied_on",
    "source",
    "notes",
    "resume_version",
    "follow_up_on",
)

#: Kanban stages (must match the UI board columns).
STAGES = ("wishlist", "applied", "oa", "interview", "offer", "rejected")


def _validate_row(row: dict, line: int) -> list[str]:
    errors: list[str] = []
    if not (row.get("company") or "").strip():
        errors.append(f"line {line}: company is required")
    stage = (row.get("stage") or "wishlist").strip().lower()
    if stage not in STAGES:
        errors.append(f"line {line}: unknown stage '{row.get('stage')}'")
    for dcol in ("applied_on", "follow_up_on"):
        val = (row.get(dcol) or "").strip()
        if val:
            try:
                date.fromisoformat(val)
            except ValueError:
                errors.append(f"line {line}: {dcol} must be YYYY-MM-DD")
    return errors


def normalize_row(row: dict) -> dict:
    norm = {c: (row.get(c) or "").strip() for c in CSV_COLUMNS}
    norm["stage"] = (norm["stage"] or "wishlist").lower()
    return norm


def export_csv(applications: list[dict]) -> str:
    """Serialize application dicts to CSV text (UTF-8, BOM for Excel)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    for app in applications:
        writer.writerow({c: app.get(c, "") for c in CSV_COLUMNS})
    return "\ufeff" + buf.getvalue()


def import_csv(text: str) -> dict:
    """Parse + validate CSV text. Returns {rows, errors}; rows are normalized.

    Invalid rows are skipped but reported — never silently dropped.
    """
    text = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    errors: list[str] = []
    if reader.fieldnames is None:
        return {"rows": [], "errors": ["empty file: no header row"]}
    for i, raw in enumerate(reader, start=2):
        row_errors = _validate_row(raw, i)
        if row_errors:
            errors.extend(row_errors)
            continue
        rows.append(normalize_row(raw))
    return {"rows": rows, "errors": errors}


def tracker_wiring_snippet() -> str:
    return (
        "from studybuddy.prod_tracker import export_csv, import_csv\n"
        "# export: return Response(export_csv(apps), mimetype='text/csv',\n"
        "#                        headers={'Content-Disposition': 'attachment; filename=applications.csv'})\n"
        "# import: result = import_csv(file.read().decode('utf-8')); \n"
        "#         if result['errors']: flash them; else save result['rows']\n"
    )


__all__ = [
    "CSV_COLUMNS",
    "STAGES",
    "export_csv",
    "import_csv",
    "normalize_row",
    "tracker_wiring_snippet",
]
