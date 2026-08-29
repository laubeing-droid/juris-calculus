#!/usr/bin/env python3
"""Command line entry for the V4 remediation runner.

Commands:
  lint-plan  validate a 3.0 task plan without executing it
  run        execute a validated plan in dependency order, stop at the first
             failure, and write one JSON run log
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.remediation.plan import PlanError, load_plan
from tools.remediation.runner import EXIT_OK, EXIT_TASK_FAILED, run_plan

DEFAULT_PLAN = Path("remediation/v4/tasks.v3.json")
DEFAULT_LOG = Path("remediation/v4/runs/latest-run.json")
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remediate-v4", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint = subparsers.add_parser("lint-plan", help="validate a task plan")
    lint.add_argument("--plan", type=Path, default=DEFAULT_PLAN)

    run = subparsers.add_parser("run", help="execute a task plan")
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--through", default=None, metavar="TASK_ID",
                     help="stop after this task id (inclusive)")
    run.add_argument("--log", type=Path, default=DEFAULT_LOG,
                     help="run log JSON path for this execution")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")
    args = build_parser().parse_args(argv)
    plan_path = args.plan if Path(args.plan).is_absolute() else Path.cwd() / args.plan
    try:
        plan = load_plan(plan_path)
    except PlanError as exc:
        for problem in exc.problems:
            print(f"plan problem: {problem}", file=sys.stderr)
        return EXIT_USAGE
    if args.command == "lint-plan":
        print(f"plan OK: {len(plan.tasks)} tasks in {plan_path}")
        return EXIT_OK
    log_path = args.log if Path(args.log).is_absolute() else Path.cwd() / args.log
    try:
        return run_plan(plan, root=Path.cwd(), log_path=log_path, through=args.through)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
