"""Resumable experiment runner and summaries (E1-E6).

Runs every (repeat, system, case) combination as its own saved run named `<experiment>-<system>-<case>-r<repeat>`.
A completed run is never repeated, so an interrupted batch resumes where it stopped. A run that ended in a
provider failure (quota, network) is kept under a `-providerfail-N` name and retried. The batch stops at the first
provider failure so a quota limit does not burn through the remaining cases.
"""
from __future__ import annotations

import statistics
from pathlib import Path

import pandas as pd

from .agent import run_agent
from .baselines.fixed_pipeline import run_fixed_pipeline
from .baselines.logacf_style import run_logacf_style
from .common import read_json, utc_now, write_json
from .config import get_config
from .scoring import Scorer, metrics

SYSTEMS = ("b0", "b2", "full", "no_g1", "no_g2", "no_g3")
DETERMINISTIC = {"b0"}
# With scope "own-gap", each ablation runs only on the cases of the gap whose component it removes (E5).
ABLATED_GAP = {"no_g1": "G1", "no_g2": "G2", "no_g3": "G3"}


def cases_for(system: str, cases: list[dict], scope: str) -> list[dict]:
    if scope == "own-gap" and system in ABLATED_GAP:
        return [c for c in cases if ABLATED_GAP[system] in c.get("gaps", [])]
    return cases


def run_id(experiment: str, system: str, case_id: str, repeat: int) -> str:
    return f"{experiment}-{system}-{case_id}-r{repeat}"


def run_system(root: Path, system: str, case: dict, provider, name: str) -> dict:
    fault = case.get("fault")
    if system == "b0":
        return run_fixed_pipeline(root, case["query"], run_name=name, fault=fault)
    if system == "b2":
        return run_logacf_style(root, case["query"], provider, run_name=name, fault=fault)
    return run_agent(root, case["query"], provider, run_name=name, config=get_config(system), fault=fault)


def provider_failed(result: dict) -> bool:
    return result["status"] == "failed" and any(e.get("event") == "provider_error" for e in result["trace"])


def _set_aside(run_dir: Path) -> None:
    attempt = 1
    while run_dir.with_name(f"{run_dir.name}-providerfail-{attempt}").exists():
        attempt += 1
    run_dir.rename(run_dir.with_name(f"{run_dir.name}-providerfail-{attempt}"))


def run_experiment(root: Path, experiment: str, cases_path: Path, systems: list[str], repeats: int,
                   provider, *, scope: str = "all", log=print) -> dict:
    if scope not in ("all", "own-gap"):
        raise ValueError("scope must be 'all' or 'own-gap'")
    cases = read_json(cases_path)
    runs = root / "logs" / "runs"
    done = skipped = 0
    for repeat in range(1, repeats + 1):
        for system in systems:
            if system not in SYSTEMS:
                raise ValueError(f"Unknown system {system!r}")
            if system in DETERMINISTIC and repeat > 1:
                continue
            for case in cases_for(system, cases, scope):
                name = run_id(experiment, system, case["id"], repeat)
                path = runs / name / "result.json"
                if path.exists():
                    if not provider_failed(read_json(path)):
                        skipped += 1
                        continue
                    _set_aside(path.parent)
                if provider is not None:
                    provider.seed = repeat
                result = run_system(root, system, case, provider, name)
                log(f"{name}: {result['status']} ({result['tool_calls']} calls, {result['latency_seconds']:.1f} s)")
                if provider_failed(result):
                    log(f"Stopped on provider failure: {result['reason']}. Rerun the same command to resume.")
                    return {"experiment": experiment, "completed": False, "new_runs": done, "skipped": skipped,
                            "stopped_on": name, "reason": result["reason"]}
                done += 1
    return {"experiment": experiment, "completed": True, "new_runs": done, "skipped": skipped}


def summarize(root: Path, experiment: str, cases_path: Path, systems: list[str] | None = None,
              runs_dir: Path | None = None) -> dict:
    """Score every saved run of an experiment; write per-run rows and mean/std across repeats."""
    # Runs are read from logs/runs by default; the committed copy in logs/evidence/<experiment> re-scores the
    # reported results from a fresh clone.
    runs_dir = runs_dir or root / "logs" / "runs"
    cases, scorer = read_json(cases_path), Scorer(root, runs_dir)
    rows = []
    for system in systems or SYSTEMS:
        for case in cases:
            for path in sorted(runs_dir.glob(f"{experiment}-{system}-{case['id']}-r*/result.json")):
                result = read_json(path)
                if provider_failed(result):
                    continue
                repeat = int(path.parent.name.rsplit("-r", 1)[1])
                rows.append({"system": system, "repeat": repeat, "run_id": result["run_id"],
                             **scorer.score(case, result)})
    if not rows:
        raise ValueError(f"No completed runs found for experiment {experiment!r}")
    table = pd.DataFrame(rows)
    out = root / "results" / "experiments" / experiment
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "runs.csv", index=False)
    summary = {}
    for system, group in table.groupby("system", sort=False):
        per_repeat = [metrics(g) for _, g in group.groupby("repeat")]
        summary[system] = {"repeats": len(per_repeat), "metrics": {}}
        for key in per_repeat[0]:
            values = [m[key] for m in per_repeat if m[key] is not None]
            summary[system]["metrics"][key] = {
                "mean": statistics.fmean(values) if values else None,
                "std": statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)}
    flat = [{"system": s, "repeats": v["repeats"], "metric": k, **m}
            for s, v in summary.items() for k, m in v["metrics"].items()]
    pd.DataFrame(flat).to_csv(out / "summary.csv", index=False)
    record = {"created_utc": utc_now(), "experiment": experiment, "cases_file": str(cases_path),
              "runs_scored": len(table), "systems": summary}
    write_json(out / "summary.json", record)
    return record
