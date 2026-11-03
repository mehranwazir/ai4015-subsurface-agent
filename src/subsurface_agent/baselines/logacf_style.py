"""B2: LogACF-style role-based agent (experiment E2), adapted to this project's tools and data.

Following the base paper's design of collaborating roles over shared knowledge and an executable workflow:
- Planner (LLM) reads the request and the shared dataset knowledge and submits one complete plan;
- Executor (code) runs the plan's steps in order with the same allowlisted tools as every other system;
- Reviewer (LLM) checks the execution log and a descriptive preview of the prediction file, then approves,
  requests one regeneration, or decides to clarify/abstain.
It has none of the deterministic G1/G2/G3 components: checking and correction rely on LLM review. Same model,
tools, data and budgets as the proposed system. This is an adaptation, not a reproduction of the authors' code.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from ..agent import add_usage, finalize_run, prepare_run_dir
from ..common import clean_json
from ..config import PRESETS
from ..data import ALIASES, FEATURES, TARGETS
from ..gaps.grounding import registry_context
from ..providers import ProviderError
from ..tools import ToolRuntime

STEPS = ["inspect_dataset", "inspect_interval", "predict_properties", "verify_predictions", "plot_logs"]
MAX_REDOS = 1

PLANNER = """You are the Planner in a role-based well-log analysis team. Read the user's request and the
shared knowledge, then submit exactly one complete plan with submit_plan. The Executor runs the steps in order:
inspect_dataset, inspect_interval, predict_properties, verify_predictions, plot_logs. When the plan inspects or
predicts, fill `interval` (well, start, end, unit ft or m, optional curves). Only PHIF, SW and VSH can be predicted.
If the request cannot or should not be executed, set decision to clarify or abstain, give no steps and explain."""

REVIEWER = """You are the Reviewer in a role-based well-log analysis team. Decide whether the executed plan
correctly answers the user's request, using the plan, the execution log and the preview of the prediction file.
approve: the outputs are consistent with the request. redo: a prediction file looks wrong or incomplete and should
be regenerated (allowed once). clarify: the request is ambiguous or asks for something unsupported. abstain: the
request cannot be answered reliably. Submit your decision with submit_review."""

PLAN_DECLARATION = {
    "name": "submit_plan", "description": "Submit the complete execution plan.",
    "parameters": {"type": "object", "required": ["decision", "steps", "reason"], "properties": {
        "decision": {"type": "string", "enum": ["execute", "clarify", "abstain"]},
        "steps": {"type": "array", "items": {"type": "string", "enum": STEPS}},
        "interval": {"type": "object", "properties": {
            "well": {"type": "integer"}, "start": {"type": "number"}, "end": {"type": "number"},
            "unit": {"type": "string", "enum": ["ft", "m"]},
            "curves": {"type": "array", "items": {"type": "string"}}}},
        "reason": {"type": "string"}}}}
REVIEW_DECLARATION = {
    "name": "submit_review", "description": "Submit the review decision.",
    "parameters": {"type": "object", "required": ["decision", "reason"], "properties": {
        "decision": {"type": "string", "enum": ["approve", "redo", "clarify", "abstain"]},
        "reason": {"type": "string"}}}}


def artifact_preview(runtime: ToolRuntime, prediction_id: str) -> dict:
    """Descriptive statistics of the saved file, as a human or LLM reviewer would look at it."""
    path = runtime.predictions[prediction_id]["path"]
    if not path.exists():
        return {"prediction_id": prediction_id, "file": "not found"}
    data = pd.read_csv(path)
    columns = [f"{t}_pred" for t in TARGETS]
    return {"prediction_id": prediction_id, "rows": len(data), "columns": list(data.columns),
            "wells": sorted(int(w) for w in data.WELLNUM.unique()),
            "depth_ft": [float(data.DEPTH.min()), float(data.DEPTH.max())],
            "missing_values": int(data[columns].isna().sum().sum()),
            "values": {c: {"min": float(data[c].min()), "max": float(data[c].max()), "mean": float(data[c].mean())}
                       for c in columns}}


def run_logacf_style(root: Path, query: str, provider, *, run_name: str | None = None,
                     fault: str | None = None) -> dict:
    run_id, run_dir = prepare_run_dir(root, run_name, "b2")
    runtime = ToolRuntime(root, run_dir, query=query, config=PRESETS["b2"], fault=fault)
    knowledge = registry_context(runtime.frame, FEATURES, ALIASES, TARGETS, checklist=False)
    trace, usage = [], {"prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    started, request_start = time.perf_counter(), getattr(provider, "request_count", None)
    version = getattr(provider, "model", "test-double")
    ids = {}

    def ask(role: str, system: str, text: str, declaration: dict) -> dict:
        nonlocal version
        reply = provider.generate(system, [{"role": "user", "parts": [{"text": text}]}], [declaration])
        version = reply.model_version
        add_usage(usage, reply)
        calls = [p["functionCall"] for p in reply.content.get("parts", []) if "functionCall" in p]
        output = calls[0].get("args", {}) if calls else {}
        trace.append(clean_json({"event": "role", "role": role, "output": output}))
        return output

    def call(name: str, arguments: dict) -> dict:
        result = runtime.dispatch(name, arguments)
        trace.append(clean_json({"event": "tool", "turn": len(trace) + 1, "name": name,
                                 "arguments": arguments, "result": result}))
        if result["ok"]:
            ids.update({k: result[k] for k in ("slice_id", "prediction_id") if k in result})
        return result

    def arguments(step: str, interval: dict) -> dict:
        if step == "inspect_interval":
            return {k: v for k, v in interval.items() if v is not None}
        if step == "predict_properties":
            return {"slice_id": ids.get("slice_id", "")}
        return {} if step == "inspect_dataset" else {"prediction_id": ids.get("prediction_id", "")}

    def review(plan: dict) -> dict:
        log = [e for e in trace if e["event"] == "tool"]
        preview = artifact_preview(runtime, ids["prediction_id"]) if ids.get("prediction_id") else None
        text = (f"User request: {query}\nPlan: {json.dumps(plan)}\nExecution log: {json.dumps(log)}\n"
                f"Prediction file preview: {json.dumps(preview)}")
        return ask("reviewer", REVIEWER + knowledge, text, REVIEW_DECLARATION)

    status, reason = "failed", "Planner did not return a plan"
    try:
        plan = ask("planner", PLANNER + knowledge, f"User request: {query}", PLAN_DECLARATION)
        steps = [s for s in plan.get("steps", []) if s in STEPS]
        if plan.get("decision") != "execute" or not steps:
            status = plan.get("decision") if plan.get("decision") in ("clarify", "abstain") else "abstain"
            reason = plan.get("reason") or "Planner submitted no executable steps"
        else:
            if steps[0] != "inspect_dataset":
                steps.insert(0, "inspect_dataset")
            for step in dict.fromkeys(steps):
                if not call(step, arguments(step, plan.get("interval") or {}))["ok"]:
                    break
            verdict, redos = review(plan), 0
            while verdict.get("decision") == "redo" and redos < MAX_REDOS and ids.get("slice_id"):
                redos += 1
                for step in ("predict_properties", "verify_predictions"):
                    call(step, arguments(step, {}))
                verdict = review(plan)
            decision = verdict.get("decision")
            status = {"approve": "answer", "clarify": "clarify", "abstain": "abstain"}.get(decision, "abstain")
            reason = verdict.get("reason") or "Reviewer gave no reason"
        call("finish", {"status": status, "reason": reason[:600]})
    except ProviderError as exc:
        status, reason = "failed", str(exc)
        trace.append({"event": "provider_error", "message": reason})
    errors = sum(1 for e in trace if e["event"] == "tool" and not e["result"]["ok"])
    calls = sum(1 for e in trace if e["event"] == "tool")
    return finalize_run(runtime, run_id, query, provider, version=version, status=status, reason=reason,
                        calls=calls, errors=errors, usage=usage, request_start=request_start, started=started,
                        trace=trace, fault_injection=fault)
