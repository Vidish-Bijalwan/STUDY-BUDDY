"""Export and private share links (UX-09 / PROD-08).

* Markdown export of reports (stdlib).
* PDF export with NO new dependencies: a minimal single-font PDF writer.
  For high-fidelity PDFs the project can later add reportlab; the API is the
  same (``export_report_pdf``), so the swap is drop-in.
* Shareable private links: itsdangerous timed tokens. Links never embed resume
  text — they reference a stored report id. Revocation via a token blacklist
  (caller-supplied store; default in-memory for dev).
* ATS resume builder: templates are heavy, so v1 ships a builder spec
  (docs/ux/resume-builder.md) plus ``template_passes_parser`` which runs a
  template's rendered text through the project's own parser.
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Callable

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------
def export_report_markdown(report: dict) -> str:
    """Render a readiness report dict as Markdown."""
    lines = [
        "# Resume Readiness Report",
        "",
        f"**Score:** {report.get('score', 0)}/100",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Method:** transparent heuristic (v{report.get('version', 'rr-1.0')}) — "
        "real employer systems differ; no tool can predict their scores.",
        "",
    ]
    for pillar in report.get("pillars", []):
        lines.append(
            f"## {pillar.get('name', '')} — {pillar.get('score', 0)}/{pillar.get('max', 0)}"
        )
        for f in pillar.get("findings", []):
            points = f.get("points", 0)
            lines.append(f"- **{f.get('rule', '')}** ({points:+d} pts): {f.get('fix', '')}")
            if f.get("evidence_span"):
                lines.append(f"  - Evidence: `{f['evidence_span']}`")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PDF export (no new deps)
# ---------------------------------------------------------------------------
def _escape_pdf_text(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # WinAnsi encoding: strip non-latin-1 chars for the base-14 Helvetica font.
    return text.encode("latin-1", "replace").decode("latin-1")


def _wrap(text: str, width: int = 90) -> list[str]:
    words, out, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def export_report_pdf(report: dict) -> bytes:
    """Render a readiness report as a simple, valid one-or-more-page PDF.

    Hand-written PDF 1.4 using the base-14 Helvetica font — no new
    dependencies. Layout is intentionally plain (v1 honesty: styled reports
    need a real typesetter later).
    """
    lines: list[str] = []
    lines.append("Resume Readiness Report")
    lines.append(f"Score: {report.get('score', 0)}/100")
    lines.append("Method: transparent heuristic — real employer systems differ.")
    lines.append("")
    for pillar in report.get("pillars", []):
        lines.append(f"{pillar.get('name', '')}: {pillar.get('score', 0)}/{pillar.get('max', 0)}")
        for f in pillar.get("findings", []):
            lines.append(f"  [{f.get('rule', '')}] {f.get('points', 0):+d} pts — {f.get('fix', '')}")
        lines.append("")

    content_lines = []
    for ln in lines:
        for w in _wrap(ln):
            content_lines.append(f"BT /F1 11 Tf 50 770 y Td ({_escape_pdf_text(w)}) Tj ET")

    # Paginate: ~50 lines per page (770pt start, 14pt leading).
    pages = [content_lines[i : i + 50] for i in range(0, len(content_lines), 50)] or [[]]
    objects: list[bytes] = []
    # 1: catalog, 2: pages, then per page: page obj + content obj, then font.
    page_obj_ids, content_obj_ids = [], []
    next_id = 3
    for _ in pages:
        page_obj_ids.append(next_id)
        content_obj_ids.append(next_id + 1)
        next_id += 2
    font_id = next_id

    kids = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())

    y0 = 770
    for _pid, cid, page in zip(page_obj_ids, content_obj_ids, pages, strict=False):
        stream_lines = []
        y = y0
        for cmd in page:
            stream_lines.append(cmd.replace("770 y", f"{y}"))
            y -= 14
        stream = "\n".join(stream_lines).encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {cid} 0 R >>".encode()
        )
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode()
    return pdf


# ---------------------------------------------------------------------------
# Private share links: expiring tokens + revocation
# ---------------------------------------------------------------------------
def make_share_serializer(secret_key: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key, salt="studybuddy-share-v1")


def create_share_token(secret_key: str, report_id: str, *, ttl_hours: int = 72) -> str:
    """Create a timed token. The token embeds ONLY the report id (never text)."""
    s = make_share_serializer(secret_key)
    payload = {"rid": report_id, "iat": int(time.time()), "ttl": ttl_hours * 3600}
    return s.dumps(payload)


def verify_share_token(
    secret_key: str,
    token: str,
    *,
    revoked: Callable[[str], bool] | None = None,
    max_age_seconds: int | None = None,
) -> str | None:
    """Return the report id if the token is valid, fresh, and not revoked."""
    s = make_share_serializer(secret_key)
    try:
        payload = s.loads(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    rid = payload.get("rid")
    if not rid:
        return None
    if revoked and revoked(token):
        return None
    if max_age_seconds is None:
        ttl = int(payload.get("ttl", 72 * 3600))
        if time.time() - int(payload.get("iat", 0)) > ttl:
            return None
    return str(rid)


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RevocationList:
    """In-memory revocation store (dev default). Production: persist to DB."""

    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def revoke(self, token: str) -> None:
        self._revoked.add(_token_fingerprint(token))

    def is_revoked(self, token: str) -> bool:
        return _token_fingerprint(token) in self._revoked


def share_wiring_snippet() -> str:
    return (
        "# token = create_share_token(app.secret_key, report_id, ttl_hours=72)\n"
        "# link = url_for('shared_report', token=token, _external=True)\n"
        "# rid = verify_share_token(app.secret_key, token, revoked=store.is_revoked)\n"
        "# store.revoke(token)  # one-click revoke\n"
    )


# ---------------------------------------------------------------------------
# Resume-builder template validation (PROD-08 / UX-09)
# ---------------------------------------------------------------------------
_REQUIRED_BUILDER_FIELDS = ("name", "email", "phone", "sections")


def template_passes_parser(rendered_text: str, *, min_fields: int = 3) -> dict:
    """Run a resume-builder template's rendered text through the project's own
    field extractor ("built here, verified here" — ENG-05's "what a parser
    sees"). Returns {ok, fields_found, missing, text_len}."""
    from studybuddy import parsing

    fields = parsing.detect_fields(rendered_text or "")
    found = [k for k in ("name", "email", "phone") if fields.get(k)]
    if fields.get("sections"):
        found.append("sections")
    missing = [k for k in _REQUIRED_BUILDER_FIELDS if k not in found]
    return {
        "ok": len(found) >= min_fields and not missing,
        "fields_found": found,
        "missing": missing,
        "text_len": len(rendered_text or ""),
        "sections": fields.get("sections", []),
    }


__all__ = [
    "export_report_markdown",
    "export_report_pdf",
    "create_share_token",
    "verify_share_token",
    "RevocationList",
    "template_passes_parser",
    "share_wiring_snippet",
]
