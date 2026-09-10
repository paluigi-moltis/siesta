"""Persistent user configuration — ~/.config/siesta/ (XDG).

Two files:
  config.json   UI + app prefs: theme, working directory
  models.json   the effective provider/role routing (created on first save;
                until then the packaged default config is used)

Only the env-var NAME of an API key is ever stored here, never the key.
"""
import json
import os
import tempfile
from pathlib import Path

APP = "siesta"


def config_dir() -> Path:
    if os.environ.get("SIESTA_CONFIG_HOME"):
        d = Path(os.environ["SIESTA_CONFIG_HOME"])
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        d = Path(base) / APP
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return config_dir() / "config.json"


def models_file() -> Path:
    return config_dir() / "models.json"


DEFAULTS = {"theme": "dark", "working_dir": ""}


def load() -> dict:
    cfg = dict(DEFAULTS)
    f = config_file()
    if f.exists():
        try:
            cfg.update(json.loads(f.read_text()))
        except (OSError, ValueError):
            pass
    return cfg


def save(cfg: dict) -> Path:
    merged = {**DEFAULTS, **load(), **cfg}
    return _atomic_json(config_file(), merged)


def _atomic_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def save_models(models: dict) -> Path:
    """Persist the effective provider/role routing (models.json)."""
    return _atomic_json(models_file(), models)


def user_models_exists() -> bool:
    return models_file().exists()
