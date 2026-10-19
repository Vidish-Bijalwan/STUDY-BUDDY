# ATS-safe resume builder: spec (UX-09 / PROD-08)

Status: **spec + validation** (v1). The builder UI and template gallery are
future work; this spec defines what "ATS-safe" means here and how templates
are verified.

## Promise

"Built here, verified here": every builder template must pass the project's
own parser (`studybuddy.parsing.parse_document`) with 100% field extraction
in tests (`template_passes_parser` in `studybuddy/ux_export.py`).

## Template constraints (all templates)

1. **Single column only.** No multi-column layouts, no text boxes, no tables
   carrying core content — parsers read left-to-right, top-to-bottom.
2. **Standard section headings**: Summary, Experience, Education, Skills,
   Projects (synonyms mapped by the parser, e.g. "Work Experience").
3. **Real text, not images**: names, contact lines and bullets must be
   selectable text (image-only PDFs fail Parseability).
4. **Contact block first**: name, one email, one phone (+91 international
   format preferred), one profile link per line.
5. **Dates machine-readable**: `Jan 2023 – Present`, `01/2023`, `2023-2024`.
6. **No headers/footers for content**: contact info repeated in headers is
   duplicated or dropped by parsers — keep it in the body.
7. **Bullets, not paragraphs**: 8–30 words, action-verb start, quantified.

## Template set (planned, 3–5)

| Template   | Layout              | Best for            |
|------------|---------------------|---------------------|
| Classic    | Single column, serif headings | Traditional roles, campus placements |
| Compact    | Single column, tight spacing    | 1-page fresher resumes |
| Technical  | Single column, skills-first     | SDE / data roles |
| Academic   | Single column, publications     | Research / higher studies |

Each template is a Jinja template rendering **plain text first** (text is the
contract; PDF/DOCX are presentations of the same text). The rendered text is
what `template_passes_parser` validates.

## Export

- **Markdown/TXT**: direct from the model.
- **PDF**: via the export helper (`studybuddy/ux_export.py`); validate the
  exported PDF re-parses to identical fields (round-trip test per template).
- **DOCX**: future — must also round-trip through `parsing.extract_docx`.

## Validation gates (CI)

- `template_passes_parser` returns `ok: true` for every template × sample
  profile (fresher, 2-yr experience, career switcher).
- Round-trip: fields extracted from the exported PDF equal the source model
  (name/email/phone + section presence).
- No template may use constructs the parser warns about (tables, text boxes,
  multi-column) — asserted by checking `ParseResult.warnings`.
