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
- Tests: 203 passing — upstream suite ported + provider tests + GUI subprocess E2E with stub `pi`.
