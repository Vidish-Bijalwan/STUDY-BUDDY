"""TEST-09: locustfile smoke validation.

Does NOT run a load test — it validates that locustfile.py defines a
runnable scenario (correct user class, tasks, upload helper) so the soak
script can't rot silently. The real runs are manual/staging per
docs/testing/load.md.

NOTE: `import locust` is never done in-process here. Locust pulls in
gevent, which monkey-patches ssl.SSLContext and hits a RecursionError on
Python 3.12 (gevent ssl + urllib3 at import time). Importability is probed
in an isolated subprocess instead.
"""
import ast
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

LOCUSTFILE = Path(__file__).resolve().parent.parent / "locustfile.py"


def _tree():
    assert LOCUSTFILE.exists(), "locustfile.py missing at repo root"
    return ast.parse(LOCUSTFILE.read_text(encoding="utf-8"))


def test_locust_importable_subprocess():
    """Probe `import locust` in isolation; skip if the env can't do it."""
    proc = subprocess.run(
        [sys.executable, "-c", "import locust; print(locust.__version__)"],
        capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        pytest.skip(f"locust not importable here: "
                    f"{(proc.stderr or proc.stdout).strip()[:200]}")
    assert proc.stdout.strip()


def test_locustfile_defines_http_user():
    tree = _tree()
    classes = {n.name: n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef)}
    assert "StudyBuddyUser" in classes
    bases = [ast.unparse(b) for b in classes["StudyBuddyUser"].bases]
    assert bases == ["HttpUser"], f"unexpected bases: {bases}"


def test_locustfile_tasks_cover_browse_and_upload():
    tree = _tree()
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "StudyBuddyUser")
    task_names = set()
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos = [ast.unparse(d) for d in node.decorator_list]
            if any(d.startswith("task") for d in decos):
                task_names.add(node.name)
    expected = {"browse_home", "browse_resume_page", "public_apis",
                "tracker_board", "upload_resume_preview", "healthz"}
    assert expected <= task_names, f"missing tasks: {expected - task_names}"


def test_locustfile_pdf_helper_builds_valid_pdf():
    """Exec the _minimal_pdf helper standalone and parse its output."""
    tree = _tree()
    nodes = [n for n in tree.body
             if isinstance(n, ast.Assign)
             and any(getattr(t, "id", "") == "_PDF_LINES" for t in n.targets)
             or isinstance(n, ast.FunctionDef) and n.name == "_minimal_pdf"]
    namespace = {}
    exec(textwrap.dedent("\n".join(ast.unparse(n) for n in nodes)),
         namespace)  # noqa: S102
    pdf = namespace["_minimal_pdf"]()
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 500
    # Parseable by our own hardened pipeline (in-process for the test).
    import os
    os.environ["STUDYBUDDY_NO_PARSE_SANDBOX"] = "1"
    from studybuddy.parsing import parse_document, ParseResult
    result = parse_document(pdf, filename="load.pdf", kind="resume")
    assert isinstance(result, ParseResult)
    assert "Aarav Sharma" in result.text
