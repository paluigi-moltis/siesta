"""Headless CLI entry — `pysiesta-cli "<idea>" [--auto] [--resume]`.

Same pipeline as the GUI, but the interview (when not --auto) streams to
the terminal. GUI users never need this; it exists for automation/CI.
"""
import argparse

from siesta.pipeline import pi


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pysiesta-cli",
        description="Siesta 💤 headless pipeline — give an idea, come back "
                    "to working code.")
    parser.add_argument("--auto", action="store_true",
                        help="skip the interview; use the idea as the intent")
    parser.add_argument("--resume", action="store_true",
                        help="skip phases already completed per checkpoint")
    parser.add_argument("idea", nargs="?")
    args = parser.parse_args(argv)
    if not args.idea:
        parser.error('missing idea — e.g. pysiesta-cli "build a pomodoro CLI"')
    import json

    from siesta.pipeline.providers import check_env_vars, load_providers
    try:
        missing = check_env_vars(load_providers(
            json.loads(pi.CONFIG.read_text())))
    except Exception:
        missing = []
    if missing:
        pi.warn("API-key env vars not set: " + ", ".join(missing))
    pi.sync_providers()
    from siesta.pipeline import __main__ as pipeline_main
    pipeline_main.main(
        (["--auto"] if args.auto else []) +
        (["--resume"] if args.resume else []) + [args.idea])


if __name__ == "__main__":
    main()
