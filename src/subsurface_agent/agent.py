"""One bounded native-tool agent with explicit state and replayable event records."""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from .common import clean_json, read_json, utc_now, write_json
from .contracts import function_declarations
from .providers import ProviderError
from .tools import ToolRuntime

SYSTEM = """You coordinate a well-log RESEARCH prototype. Use the tools; never invent numbers.
First inspect_dataset, then inspect_interval for the exact requested well and bounds.
DEPTH is feet; meters are converted by the interval tool. Never guess unspecified units or ambiguous wells.
Use only PHIF (porosity), SW (water saturation), VSH (shale volume). Permeability, economics,
production forecasting, changing the model or fitting on test labels are unsupported: finish clarify.
Use predict_properties for prediction requests, then verify_predictions; plot_logs only if requested.
For simple data/curve inspection, inspect_interval is enough. For schema listing, inspect_dataset is enough.
If a tool says a prediction file is missing, predict again for the same slice and verify again.
Do not repeat nonrecoverable errors. Finish abstain on insufficient/missing data or nonexistent wells/intervals.
Ask clarification for missing depth units, ambiguous well identity, or unsupported quantities.
Only finish answer after the requested tool operations succeed. Finish reasons must be concise;
do not invent metrics, ground truth, calibration, engineering recommendations, or successful repairs.
No web browsing, arbitrary code, filesystem paths, or target labels are available.
"""


def run_agent(root: Path, query: str, provider, *, run_name: str | None = None,
              max_turns: int = 10, max_calls: int = 14, max_errors: int = 3,
              omit_prediction_once: bool = False) -> dict:
    run_id = run_name or f"agent-{uuid.uuid4().hex[:10]}"
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise ValueError("Run name must contain only letters/numbers/dash/underscore")
    run_dir = root / "results" / "runs" / run_id
    if (run_dir / "result.json").exists():
        raise ValueError("Run already exists; use a new run name to preserve evidence")
    runtime = ToolRuntime(root, run_dir, omit_prediction_once=omit_prediction_once)
    contents = [{"role": "user", "parts": [{"text": query}]}]
    trace = []; usage = {"prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    status, reason = "failed", "Execution budget exhausted"
    calls = errors = 0
    started = time.perf_counter()
    version = getattr(provider, "model", "test-double")
    for turn in range(max_turns):
        try:
            reply = provider.generate(SYSTEM, contents, function_declarations())
        except ProviderError as exc:
            reason = str(exc)
            trace.append({"event": "provider_error", "message": reason})
            break
        version = reply.model_version
        usage["prompt_tokens"] += reply.usage.get("promptTokenCount", 0)
        usage["output_tokens"] += reply.usage.get("candidatesTokenCount", 0)
        usage["thinking_tokens"] += reply.usage.get("thoughtsTokenCount", 0)
        contents.append(reply.content)  # Preserve provider signatures between native-tool turns.
        function_calls = [p["functionCall"] for p in reply.content.get("parts", []) if "functionCall" in p]
        if not function_calls:
            reason = "Provider did not return a native function call"
            break
        responses = []
        should_stop = False
        for call in function_calls:
            if calls >= max_calls or errors >= max_errors:
                reason = "Tool/error budget exhausted"
                should_stop = True
                break
            name, arguments = call.get("name", ""), call.get("args", {})
            if not isinstance(arguments, dict):
                arguments = {"invalid_arguments": str(arguments)}
            result = runtime.dispatch(name, arguments)
            calls += 1; errors += int(not result["ok"])
            event = {"event": "tool", "turn": turn + 1, "name": name, "arguments": arguments, "result": result}
            trace.append(clean_json(event))
            function_response = {"name": name, "response": clean_json(result)}
            if "id" in call:
                function_response["id"] = call["id"]
            responses.append({"functionResponse": function_response})
            if name == "finish" and result["ok"]:
                status, reason = result["status"], result["reason"]
                should_stop = True
                break
        if should_stop:
            break
        contents.append({"role": "user", "parts": responses})
    estimate = None
    if os.getenv("INPUT_USD_PER_MILLION") and os.getenv("OUTPUT_USD_PER_MILLION"):
        estimate = (usage["prompt_tokens"] * float(os.environ["INPUT_USD_PER_MILLION"]) +
                    (usage["output_tokens"] + usage["thinking_tokens"]) * float(os.environ["OUTPUT_USD_PER_MILLION"])) / 1e6
    result = {"run_id": run_id, "created_utc": utc_now(), "query": query,
              "provider": type(provider).__name__, "model_version": version,
              "status": status, "reason": reason, "tool_calls": calls, "tool_errors": errors,
              "provider_requests": getattr(provider, "request_count", None), "usage": usage,
              "latency_seconds": time.perf_counter() - started, "estimated_cost_usd": estimate,
              "billing_cost_usd": None, "cost_note": "No invoice queried; estimates only when explicit price inputs are supplied",
              "source_commit": runtime.manifest["source_commit"],
              "model_sha256": runtime.model_info["model_sha256"],
              "fault_injection": "omit_prediction_once" if omit_prediction_once else None,
              "verified_predictions": sorted(runtime.verified), "trace": trace}
    write_json(run_dir / "result.json", result)
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in trace:
            handle.write(json.dumps(clean_json(event), allow_nan=False) + "\n")
    return result


def replay_trace(root: Path, result_path: Path, *, replay_name: str | None = None) -> dict:
    saved = read_json(result_path)
    runtime = ToolRuntime(root, root / "results" / "runs" / (replay_name or f"replay-{uuid.uuid4().hex[:8]}"),
                          omit_prediction_once=saved.get("fault_injection") == "omit_prediction_once")
    if runtime.model_info["model_sha256"] != saved["model_sha256"] or runtime.manifest["source_commit"] != saved["source_commit"]:
        raise ValueError("Replay model/data version differs")
    checks = []
    for event in saved["trace"]:
        if event["event"] != "tool":
            continue
        actual = clean_json(runtime.dispatch(event["name"], event["arguments"]))
        checks.append({"tool": event["name"], "matches": actual == event["result"]})
    output = {"source_run": saved["run_id"], "checks": checks,
              "all_match": bool(checks) and all(c["matches"] for c in checks), "llm_called": False}
    write_json(runtime.run_dir / "replay.json", output)
    return output
