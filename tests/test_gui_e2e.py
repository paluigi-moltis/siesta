"""E2E: GUI-launched pipeline subprocess (with stub pi) completes all phases.

Drives PipelineProcess exactly like the GUI does: start() + watch(), waits
for the done/failed state, asserts the project artifacts exist and the
final state is 'done'.
"""
import os
import shutil
import tempfile
import threading
import unittest
import unittest.mock as mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
FACTORY_SRC = SRC / "siesta"

STUB = r"""#!/bin/bash
printf '%s\n' "$*" >> "${FAKE_PI_LOG:-/dev/null}"
model="" prev=""
for a in "$@"; do [ "$prev" = "--model" ] && model="$a"; prev="$a"; done
case "$model" in
  planner-model)
    case "$*" in
      *"spec-driven-development"*)
        printf '# Spec\n\nA tiny todo CLI in Python.\nStores tasks in memory, runs offline.\n' ;;
      *"planning-and-task-breakdown"*)
        printf '# Issues\n\n## Issue #1: Add hello\nWrite hello.\n\n## Issue #2: Add bye\nWrite bye.\n' ;;
      *"interview-me"*) echo "INTENT_FINALIZED: a tiny todo cli" ;;
      *) echo "INTENT_FINALIZED: a tiny todo cli" ;;
    esac ;;
  consultant-model)
    case "$*" in
      *"factory-learner"*)
        echo "PROJECT_LEARNING:\n  Project: stub\n  Actions:\n    LEARNING: stub learning — detail" ;;
      *"Evaluate if this review meets"*) echo "APPROVED: meets the definition of done" ;;
      *"A worker requests approval"*) echo "APPROVED: aligned with the intent recorded in the KB" ;;
      *) echo "RESOLUTION: split the work and use the standard library\nAPPROACH: take the simplest path" ;;
    esac ;;
  worker-model)
    case "$*" in
      *"QA engineer"*) echo "VERIFY_PASSED: static verification complete" ;;
      *"code-reviewer"*) echo "REVIEW_PASSED: no issues found" ;;
      *) echo "ISSUE_OK: implemented the change with tests; the suite passes." ;;
    esac ;;
  *) echo "ok" ;;
esac
"""


class TestGuiPipelineE2E(unittest.TestCase):
    def test_subprocess_run_completes(self):
        from siesta.gui.app import PipelineProcess

        tmp = Path(tempfile.mkdtemp(prefix="pysiesta-e2e-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for name in ("config", "kb", "skills", "agents_skills"):
            shutil.copytree(FACTORY_SRC / name, tmp / "factory" / name)
        # point models.json at stub model names
        import json
        mfile = tmp / "factory/config/models.json"
        models = json.loads(mfile.read_text())
        for role in ("planner", "worker", "consultant"):
            models[role]["model"] = f"{role}-model"
        mfile.write_text(json.dumps(models))

        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "pi"
        stub.write_text(STUB)
        stub.chmod(0o755)

        workdir = tmp / "workdir"
        env = os.environ | {
            "SIESTA_FACTORY": str(tmp / "factory"),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_PI_LOG": str(tmp / "pi_calls.log"),
            "PYTHONPATH": str(SRC),
        }

        proc_obj = PipelineProcess()
        proc_obj.on_output = lambda line: None
        state_holder = {"state": "idle"}
        done = threading.Event()

        def on_state(state):
            state_holder["state"] = state
            if state in ("done", "failed"):
                done.set()
        proc_obj.on_state = on_state

        # start() uses os.environ; patch it for the child
        with mock.patch.dict(os.environ, env, clear=False):
            proc_obj.start("build a tiny todo cli", auto=True,
                           workdir=str(workdir))
            proc_obj.watch()
            self.assertTrue(done.wait(timeout=60),
                            f"pipeline did not finish; log tail: "
                            f"{proc_obj.output[-10:]}")

        self.assertEqual(state_holder["state"], "done",
                         "\n".join(proc_obj.output[-30:]))
        projects = list((workdir).iterdir())
        self.assertTrue(projects, "no project created in working dir")
        proj = projects[0]
        self.assertTrue((proj / ".pipeline-checkpoint").exists())
        self.assertEqual(
            (proj / ".pipeline-checkpoint").read_text().strip(), "complete")
        # planner was actually invoked through the stub
        log_text = (tmp / "pi_calls.log").read_text()
        self.assertIn("planner-model", log_text)
        self.assertIn("worker-model", log_text)


if __name__ == "__main__":
    unittest.main()
