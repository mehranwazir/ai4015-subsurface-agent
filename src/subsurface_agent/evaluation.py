"""Manually labeled initial workflow cases; no LLM-as-judge scoring."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

from .agent import run_agent
from .common import read_json, utc_now, write_json


def score_case(case: dict, result: dict) -> dict:
    tools = [e for e in result["trace"] if e.get("event") == "tool"]
    succeeded = [e for e in tools if e["result"].get("ok")]
    expected = case["expected"]
    checks = {"disposition": result["status"] in expected["statuses"]}
    calls = {e["name"] for e in succeeded}
    checks["required_tools"] = set(expected.get("tools", [])).issubset(calls)
    inspections = [e for e in succeeded if e["name"] == "inspect_interval"]
    if "well" in expected:
        checks["well"] = bool(inspections) and all(e["result"]["well"] == expected["well"] for e in inspections)
    if "bounds_ft" in expected:
        low, high = expected["bounds_ft"]
        checks["interval"] = bool(inspections) and all(
            low - 1e-6 <= e["result"]["depth_min_ft"] <= high and
            low <= e["result"]["depth_max_ft"] <= high + 1e-6 for e in inspections)
        # Ensure the requested boundary values were preserved, not just an arbitrary contained interval.
        for event in inspections:
            args = event["arguments"]
            factor = 1 / .3048 if args.get("unit", "ft") == "m" else 1
            checks["interval"] &= abs(args["start"] * factor - low) < 1e-4 and abs(args["end"] * factor - high) < 1e-4
    if expected.get("no_prediction"):
        checks["no_prediction"] = "predict_properties" not in calls
    if expected.get("recovery"):
        checks["recovery"] = any(e["result"].get("error") == "MISSING_ARTIFACT" for e in tools) and bool(result["verified_predictions"])
    return {"case_id": case["id"], "passed": all(checks.values()), "checks": checks,
            "status": result["status"], "run_id": result["run_id"],
            "latency_seconds": result["latency_seconds"], "usage": result["usage"],
            "tool_calls": result["tool_calls"], "reason": result["reason"]}


def evaluate_cases(root: Path, provider, *, limit: int | None = None, selected: list[str] | None = None) -> dict:
    cases = read_json(root / "evaluation" / "cases.json")
    if selected:
        cases = [c for c in cases if c["id"] in selected]
        if set(selected) != {c["id"] for c in cases}:
            raise ValueError("Unknown evaluation case ID")
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise ValueError("No cases selected")
    batch = "eval-" + uuid.uuid4().hex[:8]
    records = []
    for index, case in enumerate(cases):
        result = run_agent(root, case["query"], provider, run_name=f"{batch}-{case['id']}",
                           omit_prediction_once=case.get("fault") == "omit_prediction_once")
        record = score_case(case, result)
        records.append(record)
        print(f"{case['id']}: {record['status']}, passed={record['passed']}, calls={record['tool_calls']}", flush=True)
        # A provider failure should not trigger more paid/quota requests automatically.
        if result["status"] == "failed" and any(e["event"] == "provider_error" for e in result["trace"]):
            break
    summary = {"created_utc": utc_now(), "batch_id": batch, "provider": type(provider).__name__,
               "model": getattr(provider, "model", "test-double"), "requested_case_count": len(cases),
               "executed_case_count": len(records), "passed": sum(r["passed"] for r in records),
               "pass_rate": sum(r["passed"] for r in records) / len(records), "cases": records,
               "limitations": "Initial convenience smoke suite; single run per prompt; not statistically validated; no gap ablation results"}
    write_json(root / "results" / "agent_evaluation.json", summary)
    return summary
