"""Reproducible commands. All outputs are artifacts, not submission prose."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import replay_trace, run_agent
from .baseline import run_baseline
from .common import clean_json, project_root
from .data import download_data, prepare_data
from .evaluation import evaluate_cases
from .providers import GeminiProvider, ProviderError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="subsurface")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["download", "prepare", "baseline"]:
        sub.add_parser(name)
    agent = sub.add_parser("agent")
    agent.add_argument("query")
    agent.add_argument("--run-name")
    agent.add_argument("--model")
    agent.add_argument("--simulate-missing-artifact", action="store_true")
    replay = sub.add_parser("replay")
    replay.add_argument("result", type=Path)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--limit", type=int)
    evaluate.add_argument("--cases", nargs="+")
    evaluate.add_argument("--model")
    args = parser.parse_args(argv)
    root = project_root()
    try:
        if args.command == "download":
            output = download_data(root)
        elif args.command == "prepare":
            output = prepare_data(root)
        elif args.command == "baseline":
            output = run_baseline(root)
        elif args.command == "agent":
            output = run_agent(root, args.query, GeminiProvider(root, args.model), run_name=args.run_name,
                               omit_prediction_once=args.simulate_missing_artifact)
        elif args.command == "replay":
            output = replay_trace(root, args.result)
        else:
            output = evaluate_cases(root, GeminiProvider(root, args.model), limit=args.limit, selected=args.cases)
    except (OSError, ValueError, ProviderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(clean_json(output), indent=2, allow_nan=False))
    if output.get("status") == "failed" or output.get("all_match") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
