"""Config reload behavior: routing picks up saved user config immediately."""
import json
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path


class ConfigReload(unittest.TestCase):
    """A GUI save must change routing on the NEXT call, not next import."""

    def setUp(self):
        import importlib
        self._importlib = importlib
        self.tmp = Path(tempfile.mkdtemp(prefix="pysiesta-reload-"))
        self._saved_env = dict(Path and __import__("os").environ)
        self.models = {
            "providers": {
                "a": {"type": "ollama",
                      "endpoint": "http://localhost:11434/v1",
                      "api_key_env": None, "models": ["model-a"]},
                "b": {"type": "openai-compatible",
                      "endpoint": "https://api.example.com/v1",
                      "api_key_env": "EXAMPLE_KEY", "models": ["model-b"]},
            },
            "planner": {"provider": "a", "model": "model-a"},
            "worker": {"provider": "a", "model": "model-a"},
            "consultant": {"provider": "a", "model": "model-a"},
        }

    def tearDown(self):
        import os
        os.environ.clear()
        os.environ.update(self._saved_env)

    def _write_config(self, routing: str):
        for role in ("planner", "worker", "consultant"):
            self.models[role] = {"provider": routing, "model": f"model-{routing}"}
        f = self.tmp / "models.json"
        f.write_text(json.dumps(self.models))
        return f

    def test_build_args_follows_config_change_without_reimport(self):
        from siesta.pipeline import pi
        with mock.patch.dict(__import__("os").environ,
                             {"SIESTA_MODELS_FILE": str(self._write_config("a"))}):
            pi._ROLE_CONFIG = pi._PROVIDERS = pi._CONFIG_LOADED_FROM = None
            args = pi.build_args("worker", "b", "u", thinking="off")
            self.assertEqual(args[args.index("--model") + 1], "model-a")
            self.assertEqual(args[args.index("--provider") + 1], "pysiesta-a")
            # user saves a new routing…
            self._write_config("b")
            pi._ROLE_CONFIG = pi._PROVIDERS = pi._CONFIG_LOADED_FROM = None
            args = pi.build_args("worker", "b", "u", thinking="off")
            self.assertEqual(args[args.index("--model") + 1], "model-b")
            self.assertEqual(args[args.index("--provider") + 1], "pysiesta-b")

    def test_effective_config_precedence(self):
        from siesta.pipeline import pi
        user = self._write_config("a")
        with mock.patch.dict(__import__("os").environ,
                             {"SIESTA_MODELS_FILE": str(user)}):
            pi._ROLE_CONFIG = pi._PROVIDERS = pi._CONFIG_LOADED_FROM = None
            self.assertEqual(pi._effective_config(), user)
            self.assertEqual(pi._role("planner")["provider"], "pysiesta-a")


if __name__ == "__main__":
    unittest.main()
