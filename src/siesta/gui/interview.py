"""GUI-side Phase-0 interview — the pipeline never talks to a terminal.

Runs the interview-me protocol turn by turn: each turn calls the planner
once (`pi -p --no-tools`, interview-me skill) with the transcript so far.
A reply containing `INTENT_FINALIZED:` ends the interview; anything else is
shown to the user as the agent's question. Runs in a worker thread; UI
updates hop back through Flet's event loop via callbacks.
"""
import threading

from siesta.pipeline import pi, text
from siesta.pipeline.phases import CLOSEOUT_PROMPT, INTERVIEW_PROMPT

MAX_TURNS = 12


class InterviewSession:
    """Blocking turn loop — drive it from a thread, feed answers via ask()."""

    def __init__(self, idea: str):
        self.idea = idea
        self.transcript: list[dict] = [{"role": "human", "text": idea}]
        self.intent: str | None = None
        self._answers: list = []
        self._wake = threading.Event()

    # ── UI side ──

    def answer(self, text: str | None) -> None:
        """Called from the UI thread when the user replies (or gives up)."""
        self._answers.append(text)
        self._wake.set()

    def wait_answer(self):
        self._wake.wait()
        self._wake.clear()
        return self._answers[-1] if self._answers else None

    # ── thread side ──

    def run(self, say, finish) -> None:
        """say(str) shows an agent message; finish() closes the chat."""
        body = INTERVIEW_PROMPT.format(idea=self.idea)
        transcript = ""
        for turn in range(MAX_TURNS):
            transcript = "\n\n".join(
                f"{m['role'].upper()}: {m['text']}" for m in self.transcript)
            user = ("Conduct the interview now. Ask your first question."
                    if turn == 0 else
                    f"{transcript}\n\nContinue the interview: either ask the "
                    f"next single question, or output INTENT_FINALIZED:")
            reply = pi.run_pi("planner", body, user,
                              skills=(pi.SKILLS / "interview-me",),
                              tools="no")
            marker = text.INTENT.search(reply)
            if marker:
                self.intent = marker.group(1).strip()
                say(self.intent)
                finish()
                return
            question = reply.strip()
            if not question:
                break               # degenerate answer — bail to closeout
            say(question)
            self.transcript.append({"role": "agent", "text": question})
            answer = self.wait_answer()
            if answer is None:      # user gave up
                break
            self.transcript.append({"role": "human", "text": answer})
        # Not finalized in-band: one closeout attempt, else raw idea
        closeout = pi.run_pi(
            "planner",
            CLOSEOUT_PROMPT.format(idea=self.idea,
                                   transcript=text.head(transcript, 100)),
            "Close out the interview now",
            skills=(pi.SKILLS / "interview-me",), tools="no")
        marker = text.INTENT.search(closeout)
        self.intent = (marker.group(1).strip() if marker
                       else f"{self.idea} (interview ended early; defaults chosen)")
        say(self.intent)
        finish()

    def record_to(self, out_path) -> None:
        """Persist the transcript + final intent for the pipeline's phase 0."""
        lines = [f"{m['role'].upper()}: {m['text']}" for m in self.transcript]
        lines.append(f"INTENT_FINALIZED: {self.intent}")
        out_path.write_text("\n\n".join(lines) + "\n")
