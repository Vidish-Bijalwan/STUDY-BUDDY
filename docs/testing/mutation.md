# TEST-10: Mutation testing

## Config

`pyproject.toml [tool.mutmut]` (mutmut 3.8.0):

```toml
source_paths = ["studybuddy/parsing.py", "studybuddy/skills_taxonomy.py"]
pytest_add_cli_args_test_selection = [
  "tests/test_ws5_property.py",
  "tests/test_skills_taxonomy.py",
  "tests/test_phase1_parsing.py",
]
```

Target: **mutation score > 70%** on these modules (roadmap TEST-10).
This directly addresses the finding that thousands of tests missed the
phone-regex and substring-verb bugs — mutation testing finds tests that
pass despite logic changes.

## Run

```bash
# install (also add to requirements-dev.txt via uv when recompiling:
#  uv pip compile --generate-hashes --python-version 3.12 \
#      --output-file=requirements-dev.txt requirements-dev.in)
.venv/bin/pip install "mutmut==3.8.0"

# full run on the configured targets (slow: hundreds of mutants × the
# property suite — run on a beefy machine or overnight, not per-PR)
.venv/bin/mutmut run

# results + per-mutant diffs
.venv/bin/mutmut results
.venv/bin/mutmut show <mutant-name>
```

Notes:
- Run from the repo root (mutmut reads `pyproject.toml` there).
- `STUDYBUDDY_NO_PARSE_SANDBOX=1` should be set so the property suite
  doesn't spawn a sandbox subprocess per mutant.
- Only the three configured test files run per mutant (fast,
  deterministic, no network) — the full suite is too slow for
  per-mutant execution.

## Demo run (2026-10-19, /tmp/mutdemo)

Proved the harness end-to-end on a tiny `clamp()` module:

```
$ mutmut run
    done in 59ms (1 files mutated, 0 ignored, 0 unmodified)
    2/2  🎉 0 🫥 0  ⏰ 0  🤔 0  🙁 2  🔇 0  🧙 0
    27.64 mutations/second
$ mutmut results
    tiny.x_clamp__mutmut_1: survived   # n < lo  -> n <= lo
    tiny.x_clamp__mutmut_2: survived   # n > hi  -> n >= hi
```

Triage: **both mutants are equivalent** — `clamp()` returns the same
value on every input under either mutation (at `n == lo` both branches
return `lo`; at `n == hi` both return `hi`), so no test can kill them.
Raw score 0%, triaged score 100%. Lesson for the real run: "survived"
mutants must be triaged into *equivalent* vs *test gap* — chasing a raw
100% without triage wastes effort.

## Honest status

- Config + docs + working harness: done. `mutmut --help` and
  `mutmut run` verified working against the repo's `pyproject.toml`.
- **No full run on `studybuddy/parsing.py` + `skills_taxonomy.py` yet.**
  parsing.py is large and the property suite is slow per mutant —
  expect hours; schedule it as a nightly job, not a PR gate, until the
  >70% target is measured. Record the score here when done.
- Follow-up: cosmic-ray as an alternative engine; schemathesis for API
  contract fuzzing (TEST-13).
