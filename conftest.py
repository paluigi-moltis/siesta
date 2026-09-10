"""Test bootstrap: src/ on sys.path + hermetic env.

Every test runs with its own SIESTA_CONFIG_HOME so a developer's real
~/.config/siesta/models.json can never leak routing into the suite (or
the suite leak into the developer's config).
"""
import os
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC))

_cfg = tempfile.mkdtemp(prefix="pysiesta-test-cfg-")
os.environ.setdefault("SIESTA_CONFIG_HOME", _cfg)
