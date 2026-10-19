"""TEST-06: property-based and fuzz tests for parsers and regexes.

Uses hypothesis (dev dependency):
    pip install -r requirements-dev.txt

Properties:
  1. parsing.detect_fields never raises on arbitrary text.
  2. parsing.detect_type never raises on arbitrary bytes.
  3. parsing.validate_upload returns 'pdf'/'docx' or raises ParseError only.
  4. skills_taxonomy.normalize_skill is idempotent.
  5. The phone/email/URL regexes never catastrophic-backtrack
     (time-boxed on adversarial inputs).
  6. Fuzz: parse_document / parse_upload_file with malformed/oversized
     bytes must only return ParseResult or raise ParseError (never a raw
     exception, never a hang beyond the sandbox timeout).
"""
import os
import re
import time

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402

from studybuddy import parsing  # noqa: E402
from studybuddy import skills_taxonomy  # noqa: E402
from studybuddy.parsing import ParseError, ParseResult  # noqa: E402

# Parsing spawns a sandbox subprocess by default; tests run in-process.
os.environ["STUDYBUDDY_NO_PARSE_SANDBOX"] = "1"

# Fuzz settings: enough examples to find crashes, small enough for CI.
FUZZ = settings(max_examples=60, deadline=2000)


# ---------------------------------------------------------------------------
# 1. detect_fields: never raises, always returns a dict of str keys
# ---------------------------------------------------------------------------
@FUZZ
@given(st.text(max_size=5000))
def test_detect_fields_never_raises(text):
    fields = parsing.detect_fields(text)
    assert isinstance(fields, dict)
    for k, v in fields.items():
        assert isinstance(k, str)
        assert v is None or isinstance(v, (str, list, dict))


# ---------------------------------------------------------------------------
# 2. detect_type: never raises, returns pdf/docx/None
# ---------------------------------------------------------------------------
@FUZZ
@given(st.binary(max_size=4096))
def test_detect_type_never_raises(blob):
    result = parsing.detect_type(blob)
    assert result in ("pdf", "docx", None)


# ---------------------------------------------------------------------------
# 3. validate_upload: 'pdf'/'docx' or ParseError -- nothing else
# ---------------------------------------------------------------------------
@FUZZ
@given(st.binary(max_size=4096), st.text(max_size=30))
def test_validate_upload_only_parseerror_or_type(blob, filename):
    try:
        ftype = parsing.validate_upload(blob, filename, kind="resume")
    except ParseError:
        return
    assert ftype in ("pdf", "docx")


# ---------------------------------------------------------------------------
# 4. normalize_skill idempotence: normalize(normalize(x)) == normalize(x)
# ---------------------------------------------------------------------------
@FUZZ
@given(st.text(max_size=60))
def test_normalize_skill_idempotent(text):
    once = skills_taxonomy.normalize_skill(text)
    assert once is None or isinstance(once, str)
    if once is not None:
        assert skills_taxonomy.normalize_skill(once) == once


# ---------------------------------------------------------------------------
# 5. Regexes: no catastrophic backtracking on adversarial input
# ---------------------------------------------------------------------------
_ADVERSARIAL = st.one_of(
    st.builds(lambda n: "+" + "9" * n, st.integers(1, 300)),
    st.builds(lambda n: "+91-" + "1" * n, st.integers(1, 300)),
    st.builds(lambda n: "a@b." + "c" * n, st.integers(1, 300)),
    st.builds(lambda n: "https://" + "x/" * n, st.integers(1, 300)),
    st.builds(lambda n: ("+91 98765 4321 " * n), st.integers(1, 60)),
    st.builds(lambda n: "9" * n, st.integers(1, 500)),
)

_REGEXES = {
    "phone": parsing._PHONE_RE,
    "email": parsing._EMAIL_RE,
    "url": parsing._URL_RE,
}


@pytest.mark.parametrize("name", sorted(_REGEXES))
@settings(max_examples=40, deadline=None)
@given(blob=_ADVERSARIAL)
def test_regex_no_catastrophic_backtracking(name, blob):
    rx = _REGEXES[name]
    start = time.perf_counter()
    rx.findall(blob)
    rx.search(blob)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"{name} regex took {elapsed:.2f}s on {blob[:40]!r}"


def test_regexes_are_module_level_compiled():
    # Guard against future refactors that move these to re.compile-per-call
    # (the original substring-verb/phone-regex performance bugs).
    for name, rx in _REGEXES.items():
        assert isinstance(rx, re.Pattern), name


# ---------------------------------------------------------------------------
# 6. Fuzz upload parsers: malformed/oversized bytes -> ParseResult/ParseError
# ---------------------------------------------------------------------------
@settings(max_examples=40, deadline=5000)
@given(st.binary(min_size=0, max_size=8192))
def test_parse_document_fuzz_malformed(blob):
    try:
        result = parsing.parse_document(blob, filename="fuzz.bin", kind="resume")
    except ParseError:
        return
    assert isinstance(result, ParseResult)


@settings(max_examples=30, deadline=5000)
@given(st.binary(min_size=0, max_size=8192))
def test_parse_upload_file_fuzz_malformed(blob):
    import tempfile
    import uuid

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"fuzz-{uuid.uuid4().hex}.bin")
        with open(path, "wb") as f:
            f.write(blob)
        try:
            result = parsing.parse_upload_file(path, filename="fuzz.bin")
        except ParseError:
            return
        assert isinstance(result, ParseResult)
        # SEC-08.4: originals are deleted immediately after parsing
        assert not os.path.exists(path), "upload temp file was not deleted"


def test_parse_document_rejects_oversize():
    blob = b"x" * (parsing.MAX_RESUME_BYTES + 1)
    with pytest.raises(ParseError):
        parsing.parse_document(blob, filename="big.pdf", kind="resume")


def test_validate_upload_zip_bomb_guard(monkeypatch):
    # Simulate a zip-bomb claim without writing 50MB: patch the guard limit.
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document/>")
    data = buf.getvalue()
    monkeypatch.setattr(parsing, "MAX_DOCX_DECOMPRESSED", 1)
    with pytest.raises(ParseError):
        parsing.validate_upload(data, "bomb.docx", kind="resume")
