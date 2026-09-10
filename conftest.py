"""Test bootstrap: put src/ on sys.path and alias `pipeline` imports.

The upstream codebase was a flat `factory/pipeline` package; PySiesta moves
it to `src/siesta/pipeline`. The alias keeps `from pipeline import phases`
style imports working in the (upstream) test suite while everything —
including the tests — resolves to the single installed/importable module.
"""
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

import siesta.pipeline  # noqa: E402

sys.modules.setdefault("pipeline", siesta.pipeline)
