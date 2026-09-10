"""PySiesta GUI — Flet front end for the Siesta pipeline.

Tabs:
  Build      idea input + chat-style Phase-0 interview, then launch
  Run        live pipeline log, phase progress, result summary
  Configure  providers (type/endpoint/api-key env var/models), per-role
             routing, theme, working directory — persisted across restarts
             in ~/.config/siesta/

The Phase-0 interview runs here (chat bubbles), turn by turn, through the
same planner calls the terminal interview makes. The finished transcript is
handed to the pipeline subprocess via --intent-file, so the pipeline itself
never touches a terminal.

Runs on Linux, macOS and Windows; the packaged skills/KB land in
~/.local/share/pysiesta on first launch.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import flet as ft

from siesta import config_store
from siesta.gui.interview import InterviewSession
from siesta.pipeline.providers import PROVIDER_API_MAP, check_env_vars

ROLES = ("planner", "worker", "consultant")
PROVIDER_TYPES = sorted(set(PROVIDER_API_MAP) - {"ollama"}) + ["ollama"]

PHASE_TOTAL = 8  # phases 0..7


class PipelineProcess:
    """The `python -m siesta.pipeline` subprocess + streamed output."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.output: list[str] = []
        self.state = "idle"
        self.on_output = None            # callback(str line)  # noqa: RUF012
        self.on_state = None             # callback(state str)  # noqa: RUF012

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _emit(self, line: str) -> None:
        self.output.append(line)
        if self.on_output:
            try:
                self.on_output(line)
            except Exception:
                pass

    def _set_state(self, state: str) -> None:
        self.state = state
        if self.on_state:
            try:
                self.on_state(state)
            except Exception:
                pass

    def start(self, idea: str, *, auto: bool, workdir: str,
              intent_file: Path | None = None) -> None:
        if self.running():
            raise RuntimeError("pipeline already running")
        env = os.environ.copy()
        if workdir:
            Path(workdir).expanduser().mkdir(parents=True, exist_ok=True)
            env["SIESTA_PROJECTS_DIR"] = str(Path(workdir).expanduser())
        argv = [sys.executable, "-m", "siesta.pipeline"]
        if auto:
            argv.append("--auto")
        if intent_file is not None:
            argv += ["--intent-file", str(intent_file)]
        argv.append(idea)
        self.output.clear()
        self.proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, cwd=workdir or None,
            bufsize=1, errors="replace")

    def watch(self) -> None:
        """Drain stdout in a thread; call once, right after start()."""
        proc = self.proc
        if proc is None:
            return

        def drain():
            try:
                for line in proc.stdout:
                    self._emit(line.rstrip("\n"))
            finally:
                rc = proc.wait()
                self._set_state("done" if rc == 0 else "failed")

        threading.Thread(target=drain, daemon=True).start()

    def stop(self) -> None:
        if self.running():
            self.proc.kill()
            self._emit("── pipeline stopped by user ──")


class PySiestaApp:
    """Root application: one page, three tabs, persistent configuration."""

    def __init__(self, page: ft.Page):
        self.page = page
        self.cfg = config_store.load()
        self.pipe = PipelineProcess()
        self.session: InterviewSession | None = None
        self.mode = "idle"     # idle | interviewing | running

        # ── Build tab ──
        self.idea_field = ft.Ref[ft.TextField]()
        self.chat_column = ft.Ref[ft.Column]()
        self.chat_scroll = ft.Ref[ft.Column]()
        self.chat_input = ft.Ref[ft.TextField]()
        self.chat_input_row = ft.Ref[ft.Row]()
        self.build_status = ft.Ref[ft.Text]()
        self.auto_switch = ft.Ref[ft.Switch]()
        self.start_button = ft.Ref[ft.ElevatedButton]()

        # ── Run tab ──
        self.log_view = ft.Ref[ft.ListView]()
        self.progress_bar = ft.Ref[ft.ProgressBar]()
        self.progress_label = ft.Ref[ft.Text]()
        self.stop_button = ft.Ref[ft.ElevatedButton]()

        # ── Configure tab ──
        self.theme_switch = ft.Ref[ft.Switch]()
        self.workdir_field = ft.Ref[ft.TextField]()
        self.role_dropdowns: dict[str, ft.Ref[ft.Dropdown]] = {}
        self.provider_rows = ft.Ref[ft.Column]()
        self.config_status = ft.Ref[ft.Text]()
        self._provider_editors: list[dict] = []
        self.tabs_ref = ft.Ref[ft.Tabs]()

    # ─────────────────────────── lifecycle ───────────────────────────

    async def main(self) -> None:
        self.page.title = "PySiesta 💤"
        self.page.padding = 0
        self._apply_theme()
        # both callbacks fire on the subprocess drain thread — marshal
        # every UI mutation onto the page's event loop (Flet thread safety)
        async def _run_output(line: str):
            self._on_pipeline_output(line)

        async def _run_state(state: str):
            self._on_pipeline_state(state)

        self.pipe.on_output = lambda line: self.page.run_task(_run_output, line)
        self.pipe.on_state = lambda state: self.page.run_task(_run_state, state)
        self.page.add(self._build_root())
        self.page.update()
        self._log("Welcome to PySesta 💤 — configure providers, then build.")

    def _apply_theme(self) -> None:
        self.page.theme_mode = (ft.ThemeMode.DARK
                                if self.cfg.get("theme", "dark") == "dark"
                                else ft.ThemeMode.LIGHT)

    def _build_root(self) -> ft.Tabs:
        # IMPORTANT: hold a strong local ref while building — ft.Ref stores
        # only a weak reference, so a control referenced solely through a
        # Ref is garbage-collected the moment the constructor expression ends.
        root = ft.Tabs(
            ref=self.tabs_ref,
            length=3,
            selected_index=0,
            animation_duration=200,
            expand=True,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(tabs=[
                        ft.Tab(label="Build", icon=ft.Icons.LIGHTBULB_OUTLINE),
                        ft.Tab(label="Run", icon=ft.Icons.PLAY_CIRCLE_OUTLINE),
                        ft.Tab(label="Configure",
                               icon=ft.Icons.SETTINGS_OUTLINED),
                    ]),
                    ft.TabBarView(expand=True, controls=[
                        self._build_tab(),
                        self._run_tab(),
                        self._configure_tab(),
                    ]),
                ],
            ),
        )
        self.tabs_ref.current = root
        return root

    def _switch_tab(self, index: int) -> None:
        self.tabs_ref.current.selected_index = index
        self.page.update()

    # ─────────────────────────── build tab ───────────────────────────

    def _build_tab(self) -> ft.Control:
        # strong local refs first (ft.Ref is weak-only; see _build_root)
        chat = ft.Column(spacing=8)
        scroll = ft.Column([chat], scroll=ft.ScrollMode.AUTO, expand=True)
        self.chat_column.current = chat
        self.chat_scroll.current = scroll
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Your idea", size=18, weight=ft.FontWeight.BOLD),
                    ft.Switch(label="Skip interview (--auto)",
                              ref=self.auto_switch),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.TextField(
                    ref=self.idea_field,
                    multiline=True, min_lines=3, max_lines=6,
                    hint_text="e.g. Build me a CLI pomodoro timer in Python",
                    border_radius=8),
                ft.Row([
                    ft.ElevatedButton(
                        "Start", ref=self.start_button,
                        icon=ft.Icons.PLAY_ARROW,
                        on_click=self._on_start),
                    ft.Text("", ref=self.build_status, size=12,
                            italic=True, expand=True),
                ]),
                ft.Divider(),
                ft.Row([
                    ft.Text("Interview", size=16, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.TextButton("Finish interview now",
                                  on_click=self._on_finish_interview,
                                  tooltip="Let the planner close out the "
                                          "interview with sensible defaults"),
                ]),
                ft.Container(content=self.chat_scroll.current, expand=True),
                ft.Row(
                    [ft.TextField(ref=self.chat_input, expand=True,
                                  hint_text="Answer the agent…",
                                  on_submit=self._on_chat_send),
                     ft.IconButton(ft.Icons.SEND_ROUNDED,
                                   on_click=self._on_chat_send)],
                    ref=self.chat_input_row, visible=False),
            ], expand=True, spacing=10),
            padding=20, expand=True)

    async def _on_start(self, e=None) -> None:
        idea = (self.idea_field.current.value or "").strip()
        if not idea:
            self._set_build_status("Enter an idea first.")
            return
        if self.pipe.running() or self.mode != "idle":
            self._set_build_status("A build is already in progress.")
            return
        auto = bool(self.auto_switch.current.value)
        if auto:
            self._set_build_status("Pipeline started (auto) — see Run tab.")
            self._launch(idea, auto=True, intent_file=None)
            return
        # interactive interview in the GUI
        self.mode = "interviewing"
        self.start_button.current.disabled = True
        self.chat_input_row.current.visible = True
        self.chat_column.current.controls.clear()
        self.session = InterviewSession(idea)
        self._set_build_status("Interview running — answer below.")
        self._chat_bubble("agent", None)  # placeholder for first question
        threading.Thread(target=self._interview_thread,
                         args=(self.session, idea), daemon=True).start()

    def _interview_thread(self, session: InterviewSession, idea: str) -> None:
        # UI mutations from a worker thread must be marshalled onto the
        # page's event loop (Flet is not thread-safe) — page.run_task
        # schedules the coroutine on the UI thread.
        async def _ui(fn, *args):
            fn(*args)

        def say(msg: str | None) -> None:
            self.page.run_task(_ui, self._chat_bubble, "agent", msg)

        def finish() -> None:
            self.page.run_task(_ui, self._after_interview, session, idea)

        session.run(say, finish)

    def _after_interview(self, session: InterviewSession, idea: str) -> None:
        if session.intent:
            with tempfile.NamedTemporaryFile("w", suffix=".txt",
                                             delete=False) as fh:
                intent_path = Path(fh.name)
            session.record_to(intent_path)
            self._chat_bubble("system",
                              "Intent finalized — starting the pipeline. "
                              "Watch the Run tab. You can leave now. 💤")
            self._launch(idea, auto=False, intent_file=intent_path)
        else:
            self.mode = "idle"
            self.start_button.current.disabled = False
            self.chat_input_row.current.visible = False
            self._chat_bubble("system",
                              "Interview ended without a final intent.")
            self._set_build_status("Interview failed — try again.")

    async def _on_chat_send(self, e=None) -> None:
        value = (self.chat_input.current.value or "").strip()
        if not value or self.session is None or self.mode != "interviewing":
            return
        self.chat_input.current.value = ""
        self._chat_bubble("human", value)
        self.session.answer(value)

    async def _on_finish_interview(self, e=None) -> None:
        if self.session is not None and self.mode == "interviewing":
            self.session.answer(None)

    def _chat_bubble(self, role: str, msg: str | None) -> None:
        col = self.chat_column.current
        if col is None:
            return
        dark = self.cfg.get("theme", "dark") == "dark"
        if role == "human":
            col.controls.append(ft.Container(
                content=ft.Text(msg or "", size=13, selectable=True),
                bgcolor=ft.Colors.BLUE_700 if not dark else ft.Colors.BLUE_900,
                color=ft.Colors.WHITE, border_radius=10, padding=10,
                margin=ft.margin.only(left=60, right=0, bottom=6)))
        elif role == "agent":
            if msg is not None:
                col.controls.append(ft.Container(
                    content=ft.Text(msg, size=13, selectable=True),
                    bgcolor=(ft.Colors.SURFACE_CONTAINER_HIGHEST
                             if hasattr(ft.Colors, "SURFACE_CONTAINER_HIGHEST")
                             else None),
                    border_radius=10, padding=10,
                    margin=ft.margin.only(left=0, right=60, bottom=6)))
        else:  # system
            col.controls.append(ft.Container(
                content=ft.Text(msg or "", size=12, italic=True),
                margin=ft.margin.only(bottom=6)))
        self.page.update()

    def _set_build_status(self, msg: str) -> None:
        self.build_status.current.value = msg
        self.page.update()

    # ─────────────────────────── run tab ───────────────────────────

    def _run_tab(self) -> ft.Control:
        log = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        self.log_view.current = log
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Pipeline", size=18, weight=ft.FontWeight.BOLD),
                    ft.Text("", ref=self.progress_label, size=13,
                            expand=True),
                    ft.ElevatedButton("Stop", ref=self.stop_button,
                                      icon=ft.Icons.STOP, visible=False,
                                      on_click=self._on_stop),
                ]),
                ft.ProgressBar(value=0, ref=self.progress_bar, bar_height=6),
                ft.Container(
                    content=self.log_view.current, expand=True,
                    border_radius=8, padding=8,
                    bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.ON_SURFACE)),
                ft.TextButton("Open projects folder",
                              icon=ft.Icons.FOLDER_OPEN,
                              on_click=self._on_open_workdir),
            ], expand=True, spacing=10),
            padding=20, expand=True)

    def _launch(self, idea: str, *, auto: bool,
                intent_file: Path | None) -> None:
        self.mode = "running"
        try:
            self.pipe.start(idea, auto=auto,
                            workdir=self.cfg.get("working_dir", ""),
                            intent_file=intent_file)
        except Exception as ex:
            self.mode = "idle"
            self.start_button.current.disabled = False
            self._set_build_status(f"Failed to start pipeline: {ex}")
            return
        self.pipe.watch()
        self.stop_button.current.visible = True
        self.progress_bar.current.value = None
        self.progress_label.current.value = "Starting…"
        self._log(f"── pipeline launched: {idea[:60]} ──")
        self._switch_tab(1)

    def _on_pipeline_output(self, line: str) -> None:
        self._log(line)
        stripped = line.strip()
        if stripped.startswith("══━─ Phase") and ":" in stripped:
            self.progress_label.current.value = stripped.strip("═━─ ")[:90]
            digits = "".join(ch for ch in stripped[:16] if ch.isdigit())
            if digits:
                self.progress_bar.current.value = \
                    (int(digits[0]) + 1) / PHASE_TOTAL
        self.page.update()

    def _on_pipeline_state(self, state: str) -> None:
        if state in ("done", "failed"):
            ok = state == "done"
            self.mode = "idle"
            self._log("── pipeline finished OK ──" if ok
                      else "── pipeline FAILED — see log above ──")
            self.progress_bar.current.value = 1.0 if ok else 0.0
            self.progress_label.current.value = (
                "Done — project built. 💤" if ok
                else "Failed — check the log.")
            self.stop_button.current.visible = False
            self.start_button.current.disabled = False
            self.chat_input_row.current.visible = False
            if self.page:
                self.page.update()

    def _log(self, line: str) -> None:
        if self.log_view.current is None:
            return
        self.log_view.current.controls.append(
            ft.Text(line, size=12, font_family="monospace",
                    selectable=True))
        if len(self.log_view.current.controls) > 2000:
            del self.log_view.current.controls[:500]

    async def _on_stop(self, e=None) -> None:
        self.pipe.stop()

    async def _on_open_workdir(self, e=None) -> None:
        wd = self.cfg.get("working_dir", "") or str(
            Path.home() / "pysiesta-projects")
        Path(wd).mkdir(parents=True, exist_ok=True)
        self._open_folder(wd)

    def _open_folder(self, path: str) -> None:
        try:
            system = platform.system()
            if system == "Linux":
                subprocess.Popen(["xdg-open", path])
            elif system == "Darwin":
                subprocess.Popen(["open", path])
            else:
                os.startfile(path)  # type: ignore[attr-defined]
        except OSError:
            self._log(f"Could not open folder: {path}")

    # ─────────────────────────── configure tab ───────────────────────────

    def _configure_tab(self) -> ft.Control:
        self._provider_editors = []
        providers = self._effective_models().get("providers", {})
        rows = ft.Column(
            [self._provider_editor_row(pid, p) for pid, p in providers.items()],
            spacing=12)
        self.provider_rows.current = rows

        role_cells = []
        for role in ROLES:
            dd_ref = ft.Ref[ft.Dropdown]()
            self.role_dropdowns[role] = dd_ref
            role_cells.append(self._role_cell(role))

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Configuration", size=18,
                            weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.Switch(label="Dark mode", ref=self.theme_switch,
                              value=self.cfg.get("theme", "dark") == "dark",
                              on_change=self._on_theme),
                ]),
                ft.TextField(
                    ref=self.workdir_field,
                    label="Working directory (where generated projects land)",
                    value=self.cfg.get("working_dir", ""),
                    hint_text=str(Path.home() / "pysiesta-projects"),
                    on_blur=self._on_workdir_save),
                ft.Text("Settings persist in " + str(config_store.config_dir()),
                        size=12, italic=True),
                ft.Divider(),
                ft.Text("Role routing", size=16, weight=ft.FontWeight.BOLD),
                ft.Text("Which provider/model plays each pipeline role.",
                        size=12),
                ft.Column(role_cells, spacing=8),
                ft.Divider(),
                ft.Row([
                    ft.Text("Providers", size=16, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.TextButton("Add provider", icon=ft.Icons.ADD,
                                  on_click=self._on_add_provider),
                ]),
                self.provider_rows.current,
                ft.Row([
                    ft.ElevatedButton("Save configuration",
                                      icon=ft.Icons.SAVE,
                                      on_click=self._on_save_config),
                    ft.Text("", ref=self.config_status, size=12,
                            italic=True, expand=True),
                ]),
            ], expand=True, scroll=ft.ScrollMode.AUTO, spacing=10),
            padding=20, expand=True)

    def _role_cell(self, role: str) -> ft.Control:
        models = self._effective_models()
        routing = models.get(role, {})
        current = f"{routing.get('provider', 'ollama')}::{routing.get('model', '')}"
        options = [f"{pid}::{m}"
                   for pid, p in models.get("providers", {}).items()
                   for m in p.get("models", [])]
        dd = ft.Dropdown(
            label=f"{role}", value=current if current in options else None,
            options=[ft.dropdown.Option(o) for o in options])
        self.role_dropdowns[role].current = dd
        return dd

    def _provider_editor_row(self, pid: str, p: dict) -> ft.Control:
        editors = {
            "name": ft.TextField(label="Name", value=pid, width=150),
            "type": ft.Dropdown(label="Type", value=p.get("type"),
                                width=200,
                                options=[ft.dropdown.Option(t)
                                         for t in PROVIDER_TYPES]),
            "endpoint": ft.TextField(label="Endpoint URL",
                                     value=p.get("endpoint", ""),
                                     width=340),
            "api_key_env": ft.TextField(
                label="API key env var",
                value=p.get("api_key_env") or "", width=190,
                hint_text="e.g. OPENAI_API_KEY"),
            "models": ft.TextField(label="Models (comma-separated ids)",
                                   value=", ".join(p.get("models", [])),
                                   expand=True),
        }
        self._provider_editors.append(editors)
        return ft.Container(
            content=ft.Column([
                ft.Row([editors["name"], editors["type"],
                        editors["api_key_env"]], spacing=8, wrap=True),
                ft.Row([editors["endpoint"]], spacing=8, wrap=True),
                ft.Row([editors["models"]], spacing=8, wrap=True),
            ], spacing=6),
            border=ft.Border.all(1, ft.Colors.with_opacity(0.2,
                                                           ft.Colors.ON_SURFACE)),
            border_radius=8, padding=10)

    def _effective_models(self) -> dict:
        """User-saved models.json, else the packaged default."""
        mf = config_store.models_file()
        if mf.exists():
            try:
                return json.loads(mf.read_text())
            except (OSError, ValueError):
                pass
        from siesta.pipeline.pi import CONFIG
        return json.loads(CONFIG.read_text())

    def _collect_models(self) -> dict:
        providers = {}
        for ed in self._provider_editors:
            pid = (ed["name"].value or "").strip()
            if not pid:
                continue
            providers[pid] = {
                "type": ed["type"].value or "openai-compatible",
                "endpoint": (ed["endpoint"].value or "").strip(),
                "api_key_env": (ed["api_key_env"].value or "").strip() or None,
                "models": [m.strip() for m in (ed["models"].value or "").split(",")
                           if m.strip()],
            }
        models: dict = {"providers": providers}
        base = self._effective_models()
        for role in ROLES:
            val = self.role_dropdowns[role].current.value or ""
            if "::" in val:
                pid, model = val.split("::", 1)
                prev = base.get(role, {})
                models[role] = {"provider": pid, "model": model,
                                "role": prev.get("role", ""),
                                "skills": prev.get("skills", [])}
        models["fallback"] = base.get("fallback", {})
        return models

    async def _on_add_provider(self, e=None) -> None:
        providers = self._effective_models().get("providers", {})
        providers[f"new-provider-{len(providers) + 1}"] = {
            "type": "openai-compatible",
            "endpoint": "", "api_key_env": None, "models": []}
        self._provider_editors = []
        self.provider_rows.current.controls = [
            self._provider_editor_row(pid, p) for pid, p in providers.items()]
        self.page.update()

    async def _on_theme(self, e=None) -> None:
        dark = bool(self.theme_switch.current.value)
        self.cfg["theme"] = "dark" if dark else "light"
        config_store.save({"theme": self.cfg["theme"]})
        self._apply_theme()
        self.page.update()

    async def _on_workdir_save(self, e=None) -> None:
        wd = (self.workdir_field.current.value or "").strip()
        self.cfg["working_dir"] = wd
        config_store.save({"working_dir": wd})

    async def _on_save_config(self, e=None) -> None:
        try:
            models = self._collect_models()
            from siesta.pipeline.providers import load_providers
            normalized = load_providers(models)   # validation
            config_store.save_models(models)
            # re-resolve routing in this process + sync pi's catalog;
            # the pipeline subprocess reads the same saved file on launch
            import siesta.pipeline.pi as pi
            pi._ROLE_CONFIG = None
            pi._PROVIDERS = None
            pi._CONFIG_LOADED_FROM = None
            pi.sync_providers()
            missing = check_env_vars(normalized)
            msg = "Configuration saved ✓ (providers registered with pi)."
            if missing:
                msg += (f" ⚠ env var(s) not set: {', '.join(missing)} — "
                        "set them before starting a build")
            self.config_status.current.value = msg
        except Exception as ex:
            self.config_status.current.value = f"Error: {ex}"
        self.page.update()


def main() -> None:
    ft.run(lambda page: PySiestaApp(page).main())


if __name__ == "__main__":
    main()
