"""Provider registry: validation, catalog sync, env-var resolution."""
import json
import os
import unittest
import unittest.mock as mock
from pathlib import Path
from tempfile import TemporaryDirectory

from siesta.pipeline import providers
from siesta.pipeline.providers import (
    ProviderError,
    check_env_vars,
    load_providers,
    provider_to_catalog_entry,
    sync_to_pi_catalog,
)


def sample(pid="remote", **over):
    entry = {"type": "openai-compatible",
             "endpoint": "https://api.example.com/v1",
             "api_key_env": "EXAMPLE_API_KEY",
             "models": ["model-a", "model-b"]}
    entry.update(over)
    return {pid: entry}


class LoadProviders(unittest.TestCase):
    def test_full_entry_normalizes(self):
        p = load_providers({"providers": sample()})["remote"]
        self.assertEqual(p["type"], "openai-compatible")
        self.assertEqual(p["endpoint"], "https://api.example.com/v1")
        self.assertEqual(p["api_key_env"], "EXAMPLE_API_KEY")
        self.assertEqual(p["models"], ["model-a", "model-b"])

    def test_trailing_slash_stripped_from_endpoint(self):
        p = load_providers({"providers": sample(endpoint="https://x.io/v1/")})["remote"]
        self.assertEqual(p["endpoint"], "https://x.io/v1")

    def test_unknown_type_rejected(self):
        with self.assertRaises(ProviderError):
            load_providers({"providers": sample(type="carrier-pigeon")})

    def test_missing_endpoint_rejected_for_custom_type(self):
        entry = sample()
        del entry["remote"]["endpoint"]
        with self.assertRaises(ProviderError):
            load_providers({"providers": entry})

    def test_missing_models_rejected(self):
        with self.assertRaises(ProviderError):
            load_providers({"providers": sample(models=[])})

    def test_legacy_ollama_string_accepted(self):
        p = load_providers({"providers": {"ollama": "ollama"}})["ollama"]
        self.assertEqual(p["type"], "ollama")
        self.assertEqual(p["endpoint"], providers.DEFAULT_ENDPOINTS["ollama"])

    def test_legacy_unknown_string_rejected(self):
        with self.assertRaises(ProviderError):
            load_providers({"providers": {"ollama": "ollama", "x": "x"}})


class CatalogEntry(unittest.TestCase):
    def test_api_type_mapping(self):
        cases = {"openai-compatible": "openai-completions",
                 "anthropic": "anthropic-messages",
                 "gemini": "google-generative-ai",
                 "openai-responses": "openai-responses",
                 "ollama": "openai-completions"}
        for ptype, api in cases.items():
            entry = provider_to_catalog_entry(
                "p", sample(type=ptype, api_key_env=None)["remote"])
            self.assertEqual(entry["api"], api)

    def test_env_key_passed_as_name_not_value(self):
        # pi resolves the env var at request time; the catalog stores the
        # NAME so the key value never lands on disk in the catalog.
        with TemporaryDirectory() as d:
            catalog = Path(d) / "models.json"
            with mock.patch.dict(os.environ, {"EXAMPLE_API_KEY": "sk-123"}):
                sync_to_pi_catalog(sample(), catalog)
            entry = json.loads(catalog.read_text())["providers"]["pysiesta-remote"]
            self.assertEqual(entry["apiKey"], "EXAMPLE_API_KEY")
            self.assertNotIn("sk-123", catalog.read_text())

    def test_unset_env_key_still_registers(self):
        # registration is lazy: pi resolves at request time, so an unset
        # var only fails the run, not the sync
        entry = provider_to_catalog_entry("p", sample()["remote"])
        self.assertEqual(entry["apiKey"], "EXAMPLE_API_KEY")

    def test_ollama_needs_no_key(self):
        entry = provider_to_catalog_entry("p", sample(api_key_env=None)["remote"])
        self.assertTrue(entry["apiKey"])


class Sync(unittest.TestCase):
    def test_sync_preserves_foreign_entries_and_replaces_own(self):
        with TemporaryDirectory() as d:
            catalog = Path(d) / "models.json"
            catalog.write_text(json.dumps({"providers": {
                "ollama": {"baseUrl": "http://localhost:11434/v1", "models": []}}}))
            with mock.patch.dict(os.environ, {"EXAMPLE_API_KEY": "k1"}):
                sync_to_pi_catalog(sample(), catalog)
                first = json.loads(catalog.read_text())
                self.assertIn("ollama", first["providers"])
                self.assertIn("pysiesta-remote", first["providers"])
                # re-sync with a different provider set: old pysiesta-* gone
                sync_to_pi_catalog(sample("other"), catalog)
                second = json.loads(catalog.read_text())
                self.assertNotIn("pysiesta-remote", second["providers"])
                self.assertIn("pysiesta-other", second["providers"])

    def test_check_env_vars_reports_missing_only(self):
        with mock.patch.dict(os.environ, {"SET_VAR": "x"}, clear=True):
            missing = check_env_vars({
                "a": {"api_key_env": "SET_VAR"},
                "b": {"api_key_env": "UNSET_VAR"},
                "c": {"api_key_env": None},
            })
            self.assertEqual(missing, ["UNSET_VAR"])


if __name__ == "__main__":
    unittest.main()
