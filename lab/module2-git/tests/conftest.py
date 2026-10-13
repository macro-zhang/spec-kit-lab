# -*- coding: utf-8 -*-
"""conftest.py - put scripts/ on sys.path and expose the checker as a module.

The checker is loaded by path (not imported by name) so that the tests
exercise the exact file the hooks call, and so that a stray copy of
`check_tests_touched.py` elsewhere on sys.path cannot be substituted.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = MODULE_ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(scope="session")
def checker():
    """The checker imported as a module, for unit-testing its pure helpers."""
    path = SCRIPTS / "check_tests_touched.py"
    spec = importlib.util.spec_from_file_location("_check_tests_touched", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
