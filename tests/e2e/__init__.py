"""TEST-07/08: Playwright end-to-end tests (package marker).

This __init__.py makes tests/e2e a package so tests/e2e/conftest.py is
imported as e2e.conftest — without it, pytest registers it as top-level
`conftest`, shadowing tests/conftest.py and breaking every existing
`from conftest import ...` in a full-suite run.
"""
