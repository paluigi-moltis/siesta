# PySiesta 💤

**"Give me an idea, go take a siesta, come back to working code."**

PySiesta is a fork of [jairorodriguezarias/siesta](https://github.com/jairorodriguezarias/siesta)
— a local-first autonomous development pipeline, reborn as a cross-platform
(Linux/macOS/Windows) Python app with a Flet GUI, remote LLM provider support,
and `uv` packaging.

You give it a project idea, answer a few clarifying questions (in the GUI chat),
then walk away. When you come back, there's a git repository with working,
tested code that runs locally.

```bash
uv run pysiesta        # GUI
uv run pysiesta-cli "Build a CLI pomodoro timer in Python" --auto   # headless
```

## What's new in this fork

| Change | How |
|---|---|
| **Remote models** | Each pipeline role (planner / worker / consultant) routes through a configurable **provider**: type (`openai-compatible`, `anthropic`, `gemini`, `openai-responses`, `ollama`), endpoint URL, the **name of the env var holding the API key**, and the models it exposes. Providers are synced into the `pi` agent catalog, so the tool-calling worker can run on any remote API — not only local Ollama. |
| **Linux support** | Pure-Python pipeline, XDG config (`~/.config/siesta/`), data store at `~/.local/share/pysiesta/`, `xdg-open` for folders, no macOS-specific code paths. macOS and Windows work too. |
| **Flet GUI** | Idea input, chat-style Phase-0 interview, live pipeline log with phase progress, provider/role/theme/working-directory configuration. Dark and light mode. |
| **Persistent config** | Settings survive restarts in `~/.config/siesta/config.json` (theme, working directory) and `~/.config/siesta/models.json` (providers + role routing). API keys are **never stored** — only the env-var *names*. |
| **uv packaging** | Installable wheel with two entry points; skills and KB ship inside the package. |

## Installation

Prerequisites:

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- the [`pi`](https://github.com/mariozechner/pi-coding-agent) coding agent on PATH: `npm install -g @mariozechner/pi-coding-agent`
- at least one reachable provider (a local [Ollama](https://ollama.ai) daemon,
  or API keys for a remote provider)

```bash
git clone https://github.com/paluigi-moltis/siesta.git
cd siesta
uv sync            # creates .venv and installs pysiesta
uv run pysiesta    # launch the GUI
```

### Provider configuration (GUI or models.json)

Configure in the **Configure** tab, or edit the file directly. The effective
config lives at `~/.config/siesta/models.json` once saved:

```json
{
  "providers": {
    "my-openai": {
      "type": "openai-compatible",
      "endpoint": "https://api.openai.com/v1",
      "api_key_env": "OPENAI_API_KEY",
      "models": ["gpt-5.2"]
    },
    "claude": {
      "type": "anthropic",
      "endpoint": "https://api.anthropic.com",
      "api_key_env": "ANTHROPIC_API_KEY",
      "models": ["claude-sonnet-4-5"]
    },
    "gemini": {
      "type": "gemini",
      "endpoint": "https://generativelanguage.googleapis.com/v1beta",
      "api_key_env": "GEMINI_API_KEY",
      "models": ["gemini-2.5-pro"]
    },
    "ollama": {
      "type": "ollama",
      "endpoint": "http://localhost:11434/v1",
      "api_key_env": null,
      "models": ["gemma4:31b-cloud"],
      "compat": { "supportsDeveloperRole": false, "supportsReasoningEffort": false }
    }
  },
  "planner":   { "provider": "claude", "model": "claude-sonnet-4-5" },
  "worker":    { "provider": "my-openai", "model": "gpt-5.2" },
  "consultant":{ "provider": "gemini", "model": "gemini-2.5-pro" }
}
```

- `api_key_env` is the **name** of the environment variable that holds the
  key; the key itself never touches disk. Ollama needs no key.
- Saving from the GUI registers the providers with `pi`'s catalog
  (`~/.pi/agent/models.json`) under `pysiesta-<name>` ids and warns about
  env vars that are not set.
- Pre-fork configs with a bare `"provider": "ollama"` string keep working.

---

# LLM Provider Configuration — Full Reference

Everything about which models power the pipeline lives in one concept: a
**provider** describes *where* models are reachable, and **role routing**
decides *which* provider+model plays each of the three pipeline roles.

## Concepts

```
┌──────────────────────────────────────────────────────────────────┐
│  provider ("my-openai")                                          │
│  ├─ type:       which wire protocol to speak (see table below)   │
│  ├─ endpoint:   base URL of the API                              │
│  ├─ api_key_env NAME of the env var holding the secret key       │
│  └─ models:     the model ids this provider exposes              │
└──────────────────────────────────────────────────────────────────┘
                    ▲                ▲                ▲
        "my-openai::gpt-5.2"   "claude::..."    "ollama::..."
                    │                │                │
┌─────────────┐ ┌──────────────┐ ┌────────────────┐
│ planner     │ │ worker       │ │ consultant     │   ← role routing
│ spec, plan, │ │ writes code, │ │ resolves doubts│     (one provider::model
│ interviews  │ │ runs tools   │ │ proxy approval │      per role)
└─────────────┘ └──────────────┘ └────────────────┘
```

- **Providers** are endpoint definitions — reusable across roles.
- **Roles** are the pipeline's three agents. Each role binds to exactly one
  `provider::model` pair.
- The **worker** runs `pi` with tool-calling enabled (writes files, runs
  tests, commits). The planner and consultant run in `--no-tools` text
  mode — they only need to answer with protocol markers.

## Provider types

| Type | Wire protocol | Use for |
|---|---|---|
| `openai-compatible` | OpenAI Chat Completions (`/chat/completions`) | **The default choice.** Any endpoint speaking the OpenAI dialect: OpenAI, OpenRouter, Z.AI, Groq, Mistral, Together, Fireworks, DeepSeek, xAI, vLLM, LM Studio, llama.cpp server, Ollama's `/v1`… |
| `anthropic` | Anthropic Messages API | Claude models on the official API (or Anthropic-compatible gateways) |
| `gemini` | Google Generative AI API | Gemini / Gemma models on Google AI Studio or Vertex AI's generative API |
| `openai-responses` | OpenAI Responses API | OpenAI's newer Responses API — only if you specifically want it; most OpenAI-compatible endpoints are better served by `openai-compatible` |
| `ollama` | OpenAI Chat Completions + Ollama defaults | Local Ollama daemon or Ollama Cloud. Identical wire protocol to `openai-compatible` but with Ollama-friendly defaults (any-string API key, `compat` flags typically needed) |

### When to use which

- **Choosing between `openai-compatible` and `openai-responses`:** unless
  you know you need the Responses API (e.g. built-in web search tools or
  stateful conversations), use `openai-compatible`. It is the most widely
  compatible dialect and the one upstream `pi` handles best.
- **`anthropic` for Claude.** Do *not* route Claude through an
  `openai-compatible` shim unless the endpoint really is OpenAI-style —
  native Messages API support means correct tool-calling and thinking.
- **`gemini` for Google models.** Same reasoning: native protocol beats a
  compatibility shim.
- **`ollama` for anything local.** A local daemon needs no API key; most
  Ollama models reject the `developer` role and `reasoning_effort`
  parameters that OpenAI dialect clients send, which is why the default
  config sets `compat.supportsDeveloperRole: false` and
  `compat.supportsReasoningEffort: false`. Keep those flags unless you
  know your model accepts them.
- **Remote gateways (OpenRouter etc.):** `openai-compatible` + the
  gateway's `/v1` endpoint + a key env var. One provider can list models
  from many families — the gateway translates.

### Tool-calling requirement (worker role)

The worker role *must* use a model that emits **native tool calls**
(OpenAI `tool_calls` / Anthropic `tool_use` blocks) through its protocol.
Models that print tool calls as plain text will fail every code-writing
issue. Current good choices: GPT-4/5-class, Claude 3.5+, Gemini 2.x,
GLM-4.6/5.x, Qwen2.5-/3-coder (via a *fixed* Ollama ≥ 0.12), Kimi K2.
The planner/consultant roles have no such requirement — any model that
follows the marker protocol works, even small local ones.

## Provider fields

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | one of `openai-compatible`, `anthropic`, `gemini`, `openai-responses`, `ollama` |
| `endpoint` | yes* | base URL. Defaults exist for `anthropic`, `gemini`, `ollama`; custom/self-hosted types must set it |
| `api_key_env` | no | NAME of the env var holding the API key. `null` = no key (local daemons) |
| `models` | yes | list of model ids reachable through this provider |
| `context_window` | no | tokens; default `128000`. Used for pi compaction warnings — set it to the model's real served window |
| `max_tokens` | no | max output tokens; default `16384` |
| `compat` | no | pi compatibility overrides, e.g. `{"supportsDeveloperRole": false, "supportsReasoningEffort": false}` (typical for Ollama/self-hosted) |

### API keys — how they flow

1. You store keys as normal environment variables, e.g.
   `export OPENAI_API_KEY=sk-...` in your shell profile or `.env`.
2. Config files (and the GUI) reference only the **name**
   (`"api_key_env": "OPENAI_API_KEY"`).
3. On save/sync, PySiesta writes that *name* into pi's catalog
   (`~/.pi/agent/models.json`). **pi resolves the variable at request
   time** — the key value itself is never copied to disk by PySiesta.
4. Consequence: the env var must be set in the environment where a build
   runs (the GUI passes your environment to the pipeline subprocess).
   The GUI warns at save time about vars that are unset.

### Endpoints

The endpoint is the **base** URL — pi appends the protocol paths:

- OpenAI-style: `https://api.openai.com/v1` (chat completions)
- Anthropic: `https://api.anthropic.com`
- Gemini: `https://generativelanguage.googleapis.com/v1beta`
- Ollama local: `http://localhost:11434/v1`
- Ollama Cloud: your Ollama Cloud base URL + `/v1`
- OpenRouter: `https://openrouter.ai/api/v1`
- vLLM / LM Studio / llama.cpp: `http://<host>:<port>/v1`

## Role routing

```json
"planner":   { "provider": "claude",   "model": "claude-sonnet-4-5" },
"worker":    { "provider": "ollama",   "model": "gemma4:31b-cloud" },
"consultant":{ "provider": "my-openai", "model": "glm-5.2" }
```

- `provider` must be a key from your `providers` object; `model` must be
  listed in that provider's `models`.
- All three roles may share one provider (the default), or each may use a
  different one. A common cost-optimized split: strong reasoning model for
  planner/consultant, cheaper tool-capable model for the worker.
- The planner holds the interview/spec/plan protocol, the consultant owns
  resolution + proxy-approval markers (`APPROVED`, `RESOLUTION:`,
  `DIAGNOSIS:`) — both need reliable instruction-following more than they
  need tool support. If runs fail with "no usable spec" or unmarked proxy
  output, upgrade the planner/consultant model first.

## Where configuration lives (precedence)

1. `~/.config/siesta/models.json` — created when you press **Save
   configuration** in the GUI. **This is what every run uses.**
2. The packaged default (`src/siesta/config/models.json` in the repo) —
   used until a user config exists.
3. `SIESTA_MODELS_FILE=/path/to/models.json` — explicit override for
   testing/CI, wins over both.

The GUI's Configure tab writes the same file the headless CLI and the
pipeline subprocess read — save once, every launch picks it up.

## Full example — mixed local + remote

```json
{
  "providers": {
    "local-ollama": {
      "type": "ollama",
      "endpoint": "http://localhost:11434/v1",
      "api_key_env": null,
      "models": ["gemma4:31b-cloud", "glm-5.2:cloud"],
      "compat": { "supportsDeveloperRole": false,
                  "supportsReasoningEffort": false }
    },
    "openrouter": {
      "type": "openai-compatible",
      "endpoint": "https://openrouter.ai/api/v1",
      "api_key_env": "OPENROUTER_API_KEY",
      "models": ["anthropic/claude-sonnet-4.5", "deepseek/deepseek-chat"],
      "context_window": 200000
    },
    "google": {
      "type": "gemini",
      "endpoint": "https://generativelanguage.googleapis.com/v1beta",
      "api_key_env": "GEMINI_API_KEY",
      "models": ["gemini-2.5-pro"],
      "context_window": 1048576
    }
  },
  "planner":    { "provider": "google",      "model": "gemini-2.5-pro" },
  "worker":     { "provider": "local-ollama","model": "gemma4:31b-cloud" },
  "consultant": { "provider": "openrouter", "model": "anthropic/claude-sonnet-4.5" }
}
```

Then: `export GEMINI_API_KEY=... && export OPENROUTER_API_KEY=...` and
start a build. The GUI's Configure tab edits exactly this structure.

## Validating your configuration

- **GUI:** press *Save configuration* — validation runs before saving and
  the status line reports errors (unknown type, missing endpoint/models)
  plus unset key env vars.
- **CLI smoke test:** `pysiesta-cli --auto "tiny hello world in Python"`
  exercises every role within a couple of minutes.
- **Check registration:** `pi --list-models pysiesta` lists everything
  PySiesta registered with pi's catalog.

## How it works

```
You: "Build me a CLI pomodoro timer in Python"          (Build tab)
Phase 0: the planner interviews you in a chat           (you answer, then leave 💤)
Phase 1: the planner writes the spec                    (autonomous)
Phase 2: the planner breaks it into ordered issues      (autonomous)
Phase 3: the worker executes each issue (TDD,
         consultant on stuck, deep diagnosis, proxy)
Phase 4: review + human-proxy approval
Phase 5: verify it runs locally
Phase 6: final git commit
Phase 7: learns from the project                        (Run tab shows it all)
↓
You: come back. Working code. Git history. KB. 🎉
```

Model routing per role is deliberate: protocol roles (planner/consultant)
must hold text markers (`INTENT_FINALIZED:`, `APPROVED`, `VERIFY_PASSED:`);
the worker needs reliable **native tool calling** through `pi`. Any provider
combination works — all local, all remote, or mixed.

## The GUI

| Tab | What it does |
|---|---|
| **Build** | Type your idea, hit Start. The planner interviews you in chat bubbles; answer in the text field. *Finish interview now* lets the planner close out with sensible defaults. *Skip interview (--auto)* jumps straight to the pipeline. |
| **Run** | Live pipeline log, phase progress bar, Stop button, link to the projects folder. |
| **Configure** | Providers (type/endpoint/env-var/models), role routing dropdowns, working directory, dark/light. Saved across restarts. |

Generated projects land in the configured working directory
(`~/pysiesta-projects` by default via the GUI, `factory/projects/` for
headless runs without `SIESTA_PROJECTS_DIR`).

## Headless CLI

```bash
uv run pysiesta-cli "Build a CLI pomodoro timer in Python" --auto
uv run pysiesta-cli --resume "..."          # resume an interrupted run
SIESTA_PROJECTS_DIR=/tmp/out uv run pysiesta-cli --auto "..."   # custom output dir
```

Without a terminal, the interactive interview is unavailable — use `--auto`
or an `--intent-file` (GUI internals).

## Environment variables

| Variable | Purpose |
|---|---|
| `SIESTA_PROJECTS_DIR` | where generated projects go (GUI sets this from the configured working directory) |
| `SIESTA_CONFIG_HOME` | override `~/.config/siesta` |
| `SIESTA_DATA_HOME` | override `~/.local/share/pysiesta` (packaged skills/KB) |
| `SIESTA_PI_CATALOG` | override `~/.pi/agent/models.json` path |
| `SIESTA_PI_TIMEOUT` | per-call model timeout, seconds (default 1200) |
| `SIESTA_OLLAMA_HOST` | Ollama daemon probed for context-window warnings (default `http://localhost:11434`) |
| `SIESTA_MODELS_FILE` | explicit models.json override (wins over `~/.config/siesta/models.json`; see the provider reference) |

## Development

```bash
uv sync --group dev
uv run pytest tests/        # 203 tests: unit, integration (stub pi), GUI E2E
uv run ruff check src/ tests/
```

Project structure:

```
siesta/
├── src/siesta/
│   ├── pipeline/          # orchestrator (python3 -m siesta.pipeline)
│   │   ├── __main__.py    # checkpoint, phase dispatch, summary
│   │   ├── phases.py      # phase bodies 0-7
│   │   ├── pi.py          # single run_pi() wrapper — every model call
│   │   ├── providers.py   # provider registry + pi catalog sync
│   │   ├── learn.py       # per-issue + project learning
│   │   ├── kb.py          # KB graph store + CLI shim
│   │   ├── cli.py         # pysiesta-cli entry
│   │   └── text.py        # marker regexes + parsers
│   ├── gui/               # Flet app (pysiesta entry)
│   ├── config/            # default models.json
│   ├── skills/            # 5 factory skills (self-improving)
│   ├── kb/                # schema + global graph
│   └── agents_skills/     # 10 addyosmani skills
├── tests/                 # unit + stub-pi integration + GUI subprocess E2E
└── pyproject.toml         # uv/hatch build; entry points
```

## Safety features (inherited from upstream)

`stop.md` emergency stop · regression suite gating · degenerate-output guard ·
call timeouts · fail-closed approval markers · honest verify verdicts ·
idempotent resume · spec relevance guard · thinking escalation · deep
diagnosis · blocker logging · skill-update validation. See the
[upstream README](https://github.com/jairorodriguezarias/siesta#safety-features-inspired-by-santanderairalph)
for details.

## Acknowledgments

- [jairorodriguezarias/siesta](https://github.com/jairorodriguezarias/siesta) — the original Siesta
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — 10 production-grade agent skills
- [SantanderAI/ralph](https://github.com/SantanderAI/ralph) — safety patterns
- [mariozechner/pi-coding-agent](https://github.com/mariozechner/pi-coding-agent) — the coding agent runtime
- [Flet](https://flet.dev) — the GUI framework

## License

MIT — see [LICENSE](LICENSE).

## Change Log

### 0.1.0 (fork release)
- Restructured to `src/`-layout package `pysiesta` (import name `siesta`); skills, KB and default config ship as package data and unpack to `~/.local/share/pysiesta`.
- Provider registry (`providers.py`): typed providers (`openai-compatible`, `anthropic`, `gemini`, `openai-responses`, `ollama`) with endpoint + `api_key_env`; sync into pi's catalog so all roles — including the tool-calling worker — can run remotely.
- Flet GUI: chat interview (phase 0 in-GUI via `--intent-file` handoff), live run monitor, full configuration UI; theme and settings persist in `~/.config/siesta/`.
- Linux compatibility: XDG paths, `xdg-open`, interpreter-pinned KB shim (`python3 -m siesta.pipeline.kb`), no macOS assumptions.
- Packaging: `pysiesta` (GUI) and `pysiesta-cli` (headless) entry points; `uv lock`/`uv sync` workflow; wheel verified.
- Pipeline reads saved user config (`~/.config/siesta/models.json`) with correct precedence; API keys are passed to pi as env-var NAMES and resolved at request time.
- Tests: 203 passing — upstream suite ported + provider tests + GUI subprocess E2E with stub `pi`.
