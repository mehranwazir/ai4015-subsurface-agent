"""Reproducible commands. All outputs are artifacts, not submission prose."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import replay_trace, run_agent
from .baseline import run_baseline
from .common import clean_json, project_root
from .config import PRESETS, get_config
from .data import download_data, prepare_data
from .baselines.fixed_pipeline import run_fixed_pipeline
from .baselines.logacf_style import run_logacf_style
from .faults import FAULTS
from .gaps.acceptance import calibrate
from .evaluation import evaluate_cases
from .experiments import SYSTEMS, run_experiment, summarize
from .providers import GeminiProvider, ProviderError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="subsurface")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["download", "prepare", "baseline", "calibrate-g3"]:
        sub.add_parser(name)
    agent = sub.add_parser("agent")
    agent.add_argument("query")
    agent.add_argument("--run-name")
    agent.add_argument("--model")
    agent.add_argument("--simulate-missing-artifact", action="store_true")
    agent.add_argument("--config", default="full", choices=sorted(PRESETS))
    agent.add_argument("--fault", choices=FAULTS, help="inject one artifact fault into the first prediction file")
    replay = sub.add_parser("replay")
    replay.add_argument("result", type=Path)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--limit", type=int)
    evaluate.add_argument("--cases", nargs="+")
    evaluate.add_argument("--model")
    evaluate.add_argument("--config", default="full", choices=sorted(PRESETS))
    experiment = sub.add_parser("experiment", help="run systems x cases x repeats; resumes where it stopped")
    experiment.add_argument("--name", required=True)
    experiment.add_argument("--cases", type=Path, required=True)
    experiment.add_argument("--systems", nargs="+", default=list(SYSTEMS), choices=SYSTEMS)
    experiment.add_argument("--repeats", type=int, default=3)
    experiment.add_argument("--model")
    experiment.add_argument("--temperature", type=float, default=1.0)
    experiment.add_argument("--min-interval", type=float, default=4.5,
                            help="seconds between Gemini requests (free tier: about 15 per minute)")
    experiment.add_argument("--env-file", type=Path,
                            help="credentials file in the project folder (default .env), e.g. .env.keyB")
    experiment.add_argument("--scope", choices=["all", "own-gap"], default="all",
                            help="own-gap: each ablation runs only on the cases of its own gap")
    experiment.add_argument("--rate-limit-waits", type=int, default=10,
                            help="one-minute waits allowed on HTTP 429 before the batch stops")
    summary = sub.add_parser("summarize", help="score saved runs of an experiment")
    summary.add_argument("--name", required=True)
    summary.add_argument("--cases", type=Path, required=True)
    summary.add_argument("--systems", nargs="+", choices=SYSTEMS)
    summary.add_argument("--runs-dir", type=Path, help="folder of saved runs (default logs/runs), e.g. logs/evidence/final")
    web = sub.add_parser("web", help="open the local web interface (saved runs, results and live runs)")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    root = project_root()
    if args.command == "web":
        from .web import serve
        serve(root, port=args.port, open_browser=not args.no_browser)
        return 0
    try:
        if args.command == "download":
            output = download_data(root)
        elif args.command == "prepare":
            output = prepare_data(root)
        elif args.command == "baseline":
            output = run_baseline(root)
        elif args.command == "calibrate-g3":
            output = calibrate(root)
        elif args.command == "agent" and args.config == "b0":
            output = run_fixed_pipeline(root, args.query, run_name=args.run_name, fault=args.fault)
        elif args.command == "agent" and args.config == "b2":
            output = run_logacf_style(root, args.query, GeminiProvider(root, args.model), run_name=args.run_name,
                                      fault=args.fault)
        elif args.command == "agent":
            output = run_agent(root, args.query, GeminiProvider(root, args.model), run_name=args.run_name,
                               omit_prediction_once=args.simulate_missing_artifact, config=get_config(args.config),
                               fault=args.fault)
        elif args.command == "replay":
            output = replay_trace(root, args.result)
        elif args.command == "experiment":
            needs_llm = set(args.systems) - {"b0"}
            provider = GeminiProvider(root, args.model, temperature=args.temperature, min_interval=args.min_interval,
                                      env_file=args.env_file,
                                      rate_limit_waits=args.rate_limit_waits) if needs_llm else None
            output = run_experiment(root, args.name, args.cases, args.systems, args.repeats, provider,
                                    scope=args.scope)
            if output["completed"]:
                output["summary"] = summarize(root, args.name, args.cases, args.systems)
        elif args.command == "summarize":
            output = summarize(root, args.name, args.cases, args.systems,
                               runs_dir=root / args.runs_dir if args.runs_dir else None)
        else:
            output = evaluate_cases(root, GeminiProvider(root, args.model), limit=args.limit, selected=args.cases,
                                    config=get_config(args.config))
    except (OSError, ValueError, ProviderError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(clean_json(output), indent=2, allow_nan=False))
    if output.get("status") == "failed" or output.get("all_match") is False or output.get("completed") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
