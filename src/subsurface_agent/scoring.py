"""Independent scoring of benchmark runs. Uses observable trace events, the offline oracle and reference labels;
never the system's own success claims. Reference labels are read here only, never by any system under test.

A benchmark case:
    {"id": "...", "family": "missing_unit", "gaps": ["G1"], "query": "...", "fault": null,
     "expected": {"statuses": ["clarify"], "well": 3, "bounds_ft": [10600, 11000]}}

For prediction cases the scorer also computes the interval's reference error: the frozen model's mean property
RMSE on the labelled rows of the requested interval. It separates justified abstentions (error above the
acceptance requirement) from false refusals, which the systems themselves cannot see.
"""
from __future__ import annotations

import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .data import FEATURES, SPLITS, TARGETS
from .gaps.acceptance import MAX_WINDOW_RMSE

FT_PER_M = 1 / 0.3048
FAULT_CODES = {"MISSING_ARTIFACT", "ARTIFACT_SCHEMA", "ARTIFACT_IDENTITY", "NONFINITE_RESULT",
               "BOUNDS_VIOLATION", "RECOMPUTE_MISMATCH"}


def mean_rmse(truth: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean([math.sqrt(float(np.mean((truth[:, i] - predicted[:, i]) ** 2)))
                          for i in range(len(TARGETS))]))


def _tools(result: dict) -> list[dict]:
    return [e for e in result["trace"] if e.get("event") == "tool"]


def final_prediction_id(result: dict) -> str | None:
    predicted = [e["result"]["prediction_id"] for e in _tools(result)
                 if e["name"] == "predict_properties" and e["result"].get("ok")]
    return predicted[-1] if predicted else None


def arguments_correct(result: dict, expected: dict) -> bool | None:
    """Whether every successful interval call used the expected well and bounds (None if not applicable)."""
    if "well" not in expected or "bounds_ft" not in expected:
        return None
    calls = [e for e in _tools(result) if e["name"] == "inspect_interval" and e["result"].get("ok")]
    if not calls:
        return None
    low, high = expected["bounds_ft"]
    for event in calls:
        args = event["arguments"]
        factor = FT_PER_M if args.get("unit") == "m" else 1.0
        if (args.get("well") != expected["well"] or abs(args["start"] * factor - low) > 1e-3
                or abs(args["end"] * factor - high) > 1e-3):
            return False
    return True


class Scorer:
    def __init__(self, root: Path):
        self.root = root
        processed = root / "data" / "processed"
        frames = [pd.read_csv(processed / f"{s}.csv") for s in ("validation", "test") if (processed / f"{s}.csv").exists()]
        allowed = set(SPLITS["validation"]) | set(SPLITS["test"])
        self.labels = pd.concat(frames).loc[lambda f: f.WELLNUM.isin(allowed)] if frames else None
        self.model = joblib.load(root / "models" / "random_forest.joblib")
        self._interval_cache: dict[str, float | None] = {}

    def interval_error(self, case: dict) -> float | None:
        """Reference error of the requested interval, if the case names one with at least ten labelled rows."""
        expected = case["expected"]
        if case["id"] in self._interval_cache:
            return self._interval_cache[case["id"]]
        error = None
        if self.labels is not None and "answer" in expected["statuses"] and "bounds_ft" in expected:
            low, high = expected["bounds_ft"]
            rows = self.labels.loc[(self.labels.WELLNUM == expected["well"]) & self.labels.DEPTH.between(low, high)]
            rows = rows.loc[np.isfinite(rows[FEATURES]).sum(axis=1) >= 4]
            if len(rows) >= 10:
                error = mean_rmse(rows[TARGETS].to_numpy(), self.model.predict(rows[FEATURES]))
        self._interval_cache[case["id"]] = error
        return error

    def answer_error(self, result: dict) -> float | None:
        """Error of the file the system actually reported, against reference labels."""
        prediction_id = final_prediction_id(result)
        if prediction_id is None or self.labels is None or result["oracle"].get("final_artifacts_valid") is False:
            return None
        path = self.root / "logs" / "runs" / result["run_id"] / f"{prediction_id}.csv"
        if not path.exists():
            return None
        merged = pd.read_csv(path).merge(self.labels, on=["sample_id", "WELLNUM", "DEPTH"], how="inner")
        if len(merged) < 10:
            return None
        return mean_rmse(merged[TARGETS].to_numpy(), merged[[f"{t}_pred" for t in TARGETS]].to_numpy())

    def score(self, case: dict, result: dict) -> dict:
        expected, status = case["expected"], result["status"]
        should_answer = "answer" in expected["statuses"]
        answered, refused = status == "answer", status in ("clarify", "abstain")
        fault = case.get("fault")
        harmful = bool(fault) and fault != "shuffle_rows"
        valid = result["oracle"].get("final_artifacts_valid")
        interval_error = self.interval_error(case) if not fault else None
        answer_error = self.answer_error(result) if answered else None
        detected = any(e["result"].get("error") in FAULT_CODES for e in _tools(result))
        reviewed = any(e.get("event") == "role" and e["role"] == "reviewer" and e["output"].get("decision") == "redo"
                       for e in result["trace"])
        # Task correctness: an allowed disposition, no answer resting on an invalid artifact, no reported answer
        # worse than the acceptance requirement, and, when a case allows either answering or abstaining, the
        # choice that the interval's reference error supports.
        correct = status in expected["statuses"] and not (answered and valid is False)
        if correct and interval_error is not None and {"answer", "abstain"} <= set(expected["statuses"]):
            correct = answered if interval_error <= MAX_WINDOW_RMSE else refused
        if correct and answer_error is not None and answer_error > MAX_WINDOW_RMSE:
            correct = False
        return {
            "case_id": case["id"], "family": case.get("family"), "gaps": ",".join(case.get("gaps", [])),
            "fault": fault, "status": status, "expected": "/".join(expected["statuses"]),
            "task_correct": correct, "disposition_correct": status in expected["statuses"],
            "answered": answered, "refused": refused, "should_answer": should_answer,
            "unwarranted_answer": answered and not should_answer,
            "arguments_correct": arguments_correct(result, expected),
            # G2: an answer resting on an invalid artifact is a silent error; a valid answer after a fault, a repair.
            "fault_detected": (detected or reviewed) if harmful else None,
            "silent_error": answered and valid is False,
            "repaired": (answered and valid is True) if harmful else None,
            # G3: interval_error is what answering would have cost; answer_error is what was actually reported.
            "interval_error": interval_error, "answer_error": answer_error,
            "bad_answer": None if answer_error is None else answer_error > MAX_WINDOW_RMSE,
            "failed": status == "failed",
            # Active latency excludes waits imposed by request pacing or rate limits (absent in older runs).
            "latency_seconds": result.get("active_latency_seconds", result["latency_seconds"]),
            "provider_requests": result.get("provider_requests") or 0,
            "prompt_tokens": result["usage"]["prompt_tokens"], "output_tokens": result["usage"]["output_tokens"],
            "tool_calls": result["tool_calls"], "tool_errors": result["tool_errors"],
        }


def _rate(rows: pd.DataFrame, column: str, where: pd.Series | None = None) -> float | None:
    values = (rows if where is None else rows.loc[where])[column].dropna()
    return float(values.astype(float).mean()) if len(values) else None


def metrics(rows: pd.DataFrame) -> dict:
    """Metrics for one system and one repeat. Each rate's denominator is the subset named in its description."""
    clean_prediction = rows.should_answer & rows.fault.isna() & rows.interval_error.notna()
    good, poor = clean_prediction & (rows.interval_error <= MAX_WINDOW_RMSE), clean_prediction & (rows.interval_error > MAX_WINDOW_RMSE)
    harmful = rows.fault.notna() & (rows.fault != "shuffle_rows")
    g1 = rows.gaps.str.contains("G1")
    return {
        "cases": len(rows),
        "task_success": _rate(rows, "task_correct"),                                           # all cases
        "disposition_accuracy": _rate(rows, "disposition_correct"),                             # all cases
        "g1_task_success": _rate(rows, "task_correct", g1),                                     # G1 cases
        "g1_unwarranted_answer_rate": _rate(rows, "unwarranted_answer", g1 & ~rows.should_answer),
        "argument_accuracy": _rate(rows, "arguments_correct"),                                  # interval calls
        "g2_detection_rate": _rate(rows, "fault_detected", harmful),                            # harmful faults
        "g2_silent_error_rate": _rate(rows, "silent_error", harmful),
        "g2_repair_rate": _rate(rows, "repaired", harmful),
        "g2_false_alarm_rate": _rate(rows, "refused", rows.fault == "shuffle_rows"),            # benign control
        "g3_coverage": _rate(rows, "answered", clean_prediction),                               # answerable cases
        "g3_selective_error": _rate(rows, "bad_answer", clean_prediction & rows.answered),      # answers given
        "g3_false_refusal_rate": _rate(rows, "refused", good),                                  # good intervals
        "g3_justified_abstention_rate": _rate(rows, "refused", poor),                           # poor intervals
        "provider_failure_rate": _rate(rows, "failed"),
        "mean_latency_seconds": _rate(rows, "latency_seconds"),
        "mean_provider_requests": _rate(rows, "provider_requests"),
        "mean_prompt_tokens": _rate(rows, "prompt_tokens"),
        "mean_tool_calls": _rate(rows, "tool_calls"),
    }
