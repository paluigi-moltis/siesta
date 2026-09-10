"""Provider registry — remote (and local) model providers for PySiesta.

Each entry in config/models.json's "providers" object describes one endpoint:

    "glm-cloud": {
        "type": "openai-compatible",      # see PROVIDER_API_MAP
        "endpoint": "https://api.z.ai/api/coding/paas/v4",
        "api_key_env": "ZAI_API_KEY",     # name of the env var holding the key
        "models": ["glm-5.2"]             # models exposed through this provider
    }

A role routes to `"provider": "glm-cloud", "model": "glm-5.2"`. The legacy
single-string form ("provider": "ollama") is still accepted and mapped to a
localhost Ollama entry, so pre-fork configs keep working.

sync_to_pi_catalog() writes the entries into pi's user catalog
(~/.pi/agent/models.json) so the `pi` CLI can address every provider —
that is what lets the tool-calling worker run on a remote API.
"""
import json
import os
from pathlib import Path

# pi "api" types (docs/models.md). Keys are the user-facing "type" values.
PROVIDER_API_MAP = {
    "openai-compatible": "openai-completions",
    "openai-responses": "openai-responses",
    "anthropic": "anthropic-messages",
    "gemini": "google-generative-ai",
    "ollama": "openai-completions",
}

DEFAULT_ENDPOINTS = {
    "ollama": "http://localhost:11434/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}

# Sensible defaults for models declared without explicit metadata.
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_MAX_TOKENS = 16_384

PI_CATALOG = Path(os.environ.get("SIESTA_PI_CATALOG",
                                 Path.home() / ".pi" / "agent" / "models.json"))


class ProviderError(ValueError):
    """Invalid provider configuration."""


def _legacy_provider(name: str) -> dict:
    """Pre-fork configs use bare \"provider\": \"ollama\" — keep them working."""
    if name != "ollama":
        raise ProviderError(
            f"Unknown provider {name!r}: models.json providers must declare "
            f"type/endpoint/api_key_env (or use the legacy \"ollama\" string)")
    return {"type": "ollama", "endpoint": DEFAULT_ENDPOINTS["ollama"],
            "api_key_env": None, "models": []}


def _normalize(pid: str, entry: dict) -> dict:
    ptype = entry.get("type", "openai-compatible")
    if ptype not in PROVIDER_API_MAP:
        raise ProviderError(
            f"Provider {pid!r}: unknown type {ptype!r} — expected one of "
            f"{sorted(set(PROVIDER_API_MAP) - {'ollama'})}")
    endpoint = entry.get("endpoint") or DEFAULT_ENDPOINTS.get(ptype)
    if not endpoint:
        raise ProviderError(f"Provider {pid!r}: 'endpoint' is required")
    api_key_env = entry.get("api_key_env")
    models = entry.get("models", [])
    if not isinstance(models, list) or not models:
        raise ProviderError(
            f"Provider {pid!r}: 'models' must list at least one model id")
    norm = {"type": ptype, "endpoint": str(endpoint).rstrip("/"),
            "api_key_env": api_key_env, "models": models}
    if entry.get("context_window"):
        norm["context_window"] = int(entry["context_window"])
    if entry.get("max_tokens"):
        norm["max_tokens"] = int(entry["max_tokens"])
    if "compat" in entry:
        norm["compat"] = entry["compat"]
    return norm


def load_providers(config: dict) -> dict[str, dict]:
    """providers section from a parsed models.json → normalized dict."""
    section = config.get("providers", {})
    out: dict[str, dict] = {}
    for pid, entry in section.items():
        out[pid] = _legacy_provider(pid) if isinstance(entry, str) \
            else _normalize(pid, entry)
    return out


def _resolve_key(provider: dict) -> str:
    """Resolve a provider's API key from its named env var (or a placeholder).

    Kept for callers that need the concrete value; the catalog itself only
    ever stores the env-var NAME.
    """
    env = provider.get("api_key_env")
    if not env:
        return "ollama"          # local daemons accept any non-empty key
    return os.environ.get(env, "")


def check_env_vars(providers: dict[str, dict]) -> list[str]:
    """Env vars that are named but unset — the GUI shows these as warnings."""
    missing = []
    for pid, p in providers.items():
        env = p.get("api_key_env")
        if env and not os.environ.get(env):
            missing.append(env)
    return missing


def provider_to_catalog_entry(pid: str, provider: dict) -> dict:
    """Normalized provider → an entry for pi's ~/.pi/agent/models.json.

    The API key is passed as the ENV-VAR NAME (pi resolves it at request
    time), so keys only need to exist where `pi` actually runs and are
    never copied into the catalog file. An unset variable still
    registers — check_env_vars() surfaces that at save time.
    """
    api_key_env = provider.get("api_key_env")
    ctx = provider.get("context_window", DEFAULT_CONTEXT_WINDOW)
    mt = provider.get("max_tokens", DEFAULT_MAX_TOKENS)
    entry = {
        "name": f"PySiesta {pid}",
        "baseUrl": provider["endpoint"],
        "api": PROVIDER_API_MAP[provider["type"]],
        "apiKey": api_key_env or "ollama",
        "models": [{
            "id": m,
            "name": m,
            "reasoning": False,
            "input": ["text"],
            "contextWindow": ctx,
            "maxTokens": mt,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        } for m in provider["models"]],
    }
    if "compat" in provider:
        entry["compat"] = provider["compat"]
    return entry


def sync_to_pi_catalog(providers: dict[str, dict],
                       catalog: Path = PI_CATALOG) -> Path:
    """Merge PySiesta providers into pi's user catalog (idempotent).

    Existing non-pysiesta entries are preserved; a previous pysiesta sync is
    fully replaced so removed providers disappear. Each run syncs only the
    providers actually referenced by the role routing.
    """
    payload = {}
    if catalog.exists():
        try:
            payload = json.loads(catalog.read_text())
        except (OSError, ValueError):
            payload = {}
    all_providers = payload.get("providers", {})
    for stale in [k for k in all_providers if k.startswith("pysiesta-")]:
        del all_providers[stale]
    for pid, provider in providers.items():
        all_providers[f"pysiesta-{pid}"] = provider_to_catalog_entry(pid, provider)
    payload["providers"] = all_providers
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text(json.dumps(payload, indent=2) + "\n")
    return catalog
