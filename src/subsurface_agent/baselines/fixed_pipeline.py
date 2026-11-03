"""B0: fixed, non-agentic pipeline (experiment E1).

A conventional script: rule-based parsing of the request, then always inspect -> predict -> report. It has no
LLM, cannot ask questions, never verifies or repairs artifacts, and applies a script default (feet) when the
request gives no unit. Errors from the tools are reported as a refusal.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..agent import finalize_run, prepare_run_dir
from ..common import clean_json
from ..config import PRESETS
from ..gaps.grounding import WELL, extract_request_facts
from ..tools import ToolRuntime


def parse_request(query: str) -> dict | None:
    """First well number, first two depth values (ordered) and the stated unit, defaulting to feet."""
    facts = extract_request_facts(query)
    well = WELL.search(query)
    if well is None or len(facts.depths) < 2:
        return None
    start, end = sorted(facts.depths[:2])
    return {"well": int(well.group(1)), "start": start, "end": end,
            "unit": "m" if facts.units == {"m"} else "ft"}


def run_fixed_pipeline(root: Path, query: str, *, run_name: str | None = None, fault: str | None = None) -> dict:
    run_id, run_dir = prepare_run_dir(root, run_name, "b0")
    runtime = ToolRuntime(root, run_dir, query=query, config=PRESETS["b0"], fault=fault)
    trace, started = [], time.perf_counter()

    def call(name: str, arguments: dict) -> dict:
        result = runtime.dispatch(name, arguments)
        trace.append(clean_json({"event": "tool", "turn": len(trace) + 1, "name": name,
                                 "arguments": arguments, "result": result}))
        return result

    call("inspect_dataset", {})
    status, reason = "abstain", "Could not parse a well and two depths from the request"
    interval = parse_request(query)
    if interval is not None:
        inspected = call("inspect_interval", interval)
        predicted = call("predict_properties", {"slice_id": inspected["slice_id"]}) if inspected["ok"] else inspected
        if predicted["ok"]:
            status, reason = "answer", (f"Predicted PHIF, SW and VSH for well {interval['well']} from "
                                        f"{interval['start']:g} to {interval['end']:g} {interval['unit']}")
        else:
            reason = f"{predicted['error']}: {predicted['message']}"
    call("finish", {"status": status, "reason": reason})
    errors = sum(not e["result"]["ok"] for e in trace)
    return finalize_run(runtime, run_id, query, None, version="none", status=status, reason=reason,
                        calls=len(trace), errors=errors, usage={"prompt_tokens": 0, "output_tokens": 0,
                                                                "thinking_tokens": 0},
                        request_start=None, started=started, trace=trace, fault_injection=fault)
