import joblib
import numpy as np
import pandas as pd

from subsurface_agent.common import read_json, write_json
from subsurface_agent.data import FEATURES, TARGETS
from subsurface_agent.experiments import run_experiment, summarize
from subsurface_agent.providers import ProviderError, ProviderReply

INTERVAL = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
CASES = [
    {"id": "clean", "family": "clean", "gaps": ["G1", "G3"], "fault": None,
     "query": "Predict PHIF, SW and VSH for well 3 from 10600 to 10619.5 ft and verify the result.",
     "expected": {"statuses": ["answer"], "well": 3, "bounds_ft": [10600, 10619.5]}},
    {"id": "nounit", "family": "missing_unit", "gaps": ["G1"], "fault": None,
     "query": "Predict porosity for well 3 between 10600 and 10619.5.", "expected": {"statuses": ["clarify"]}},
    {"id": "corrupt", "family": "artifact_fault", "gaps": ["G2"], "fault": "corrupt_values",
     "query": "Predict PHIF, SW and VSH for well 3 from 10600 to 10619.5 ft and verify the result.",
     "expected": {"statuses": ["answer", "abstain"], "well": 3, "bounds_ft": [10600, 10619.5]}},
]


class PlannerDouble:
    """Test double: always tries the same interval (guessing ft), repairs on artifact errors, clarifies when
    the interval call is refused."""
    model = "scripted-unit-test"

    def __init__(self):
        self.request_count, self.seed = 0, None

    def generate(self, system, contents, declarations):
        self.request_count += 1
        if len(contents) == 1:
            name, args = "inspect_dataset", {}
        else:
            last = contents[-1]["parts"][-1]["functionResponse"]
            tool, response = last["name"], last["response"]
            if tool == "inspect_dataset":
                name, args = "inspect_interval", INTERVAL
            elif tool == "inspect_interval" and not response["ok"]:
                name, args = "finish", {"status": "clarify", "reason": "Which unit?"}
            elif tool == "inspect_interval":
                self.slice_id = response["slice_id"]
                name, args = "predict_properties", {"slice_id": self.slice_id}
            elif tool == "predict_properties":
                name, args = "verify_predictions", {"prediction_id": response["prediction_id"]}
            elif not response["ok"]:
                name, args = "predict_properties", {"slice_id": self.slice_id}
            else:
                name, args = "finish", {"status": "answer", "reason": "Verified"}
        return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)


class FailingProvider(PlannerDouble):
    def generate(self, *args):
        raise ProviderError("Gemini HTTP 429: RESOURCE_EXHAUSTED")


def setup(tiny_root):
    """Reference labels for the fixture well: frozen-model predictions plus 0.01 offsets (mean RMSE 0.01)."""
    features = pd.read_csv(tiny_root / "data" / "processed" / "features.csv")
    model = joblib.load(tiny_root / "models" / "random_forest.joblib")
    labels = features.copy()
    labels[TARGETS] = model.predict(features[FEATURES]) + 0.01
    labels.to_csv(tiny_root / "data" / "processed" / "test.csv", index=False)
    write_json(tiny_root / "experiments" / "cases.json", CASES)
    return tiny_root / "experiments" / "cases.json"


def test_runner_resumes_and_summary_scores_every_gap(tiny_root):
    cases = setup(tiny_root)
    first = run_experiment(tiny_root, "t", cases, ["b0", "full", "no_g2"], 2, PlannerDouble(), log=lambda *_: None)
    assert first == {"experiment": "t", "completed": True, "new_runs": 15, "skipped": 0}
    again = run_experiment(tiny_root, "t", cases, ["b0", "full", "no_g2"], 2, PlannerDouble(), log=lambda *_: None)
    assert again["new_runs"] == 0 and again["skipped"] == 15

    summary = summarize(tiny_root, "t", cases)["systems"]
    m = {s: {k: v["mean"] for k, v in summary[s]["metrics"].items()} for s in summary}
    assert summary["b0"]["repeats"] == 1 and summary["full"]["repeats"] == 2
    assert m["full"]["task_success"] == 1.0 and m["full"]["g2_silent_error_rate"] == 0.0
    assert m["full"]["g2_repair_rate"] == 1.0 and m["full"]["g2_detection_rate"] == 1.0
    assert m["b0"]["g2_silent_error_rate"] == 1.0 and m["b0"]["g1_unwarranted_answer_rate"] == 1.0
    assert m["no_g2"]["g2_silent_error_rate"] == 1.0
    assert abs(m["full"]["g3_coverage"] - 1.0) < 1e-12 and m["full"]["g3_selective_error"] == 0.0
    runs = pd.read_csv(tiny_root / "results" / "experiments" / "t" / "runs.csv")
    clean = runs.loc[(runs.system == "full") & (runs.case_id == "clean")]
    assert np.allclose(clean.interval_error, 0.01) and np.allclose(clean.answer_error, 0.01)


def test_provider_failure_stops_the_batch_and_is_retried_later(tiny_root):
    cases = setup(tiny_root)
    stopped = run_experiment(tiny_root, "f", cases, ["full"], 1, FailingProvider(), log=lambda *_: None)
    assert stopped["completed"] is False and stopped["stopped_on"] == "f-full-clean-r1"
    resumed = run_experiment(tiny_root, "f", cases, ["full"], 1, PlannerDouble(), log=lambda *_: None)
    assert resumed["completed"] and resumed["new_runs"] == 3
    kept = tiny_root / "logs" / "runs" / "f-full-clean-r1-providerfail-1" / "result.json"
    assert read_json(kept)["status"] == "failed"
    assert summarize(tiny_root, "f", cases)["runs_scored"] == 3


class ThrottledDouble(PlannerDouble):
    """Test double that reports five seconds of pacing per request, as the paced Gemini provider does."""
    throttle_seconds = 0.0

    def generate(self, *args):
        self.throttle_seconds += 5.0
        return super().generate(*args)


def test_pacing_waits_are_excluded_from_active_latency(tiny_root):
    setup(tiny_root)
    write_json(tiny_root / "experiments" / "one.json", CASES[:1])
    run_experiment(tiny_root, "p", tiny_root / "experiments" / "one.json", ["full"], 1, ThrottledDouble(),
                   log=lambda *_: None)
    result = read_json(tiny_root / "logs" / "runs" / "p-full-clean-r1" / "result.json")
    assert result["throttle_seconds"] == 5.0 * result["provider_requests"]
    assert abs(result["active_latency_seconds"] - (result["latency_seconds"] - result["throttle_seconds"])) < 1e-9


def test_own_gap_scope_runs_each_ablation_only_on_its_gap(tiny_root):
    cases = setup(tiny_root)
    result = run_experiment(tiny_root, "s", cases, ["full", "no_g1", "no_g2"], 1, PlannerDouble(), scope="own-gap",
                            log=lambda *_: None)
    assert result["new_runs"] == 3 + 2 + 1
    names = sorted(p.name for p in (tiny_root / "logs" / "runs").glob("s-*"))
    assert names == ["s-full-clean-r1", "s-full-corrupt-r1", "s-full-nounit-r1",
                     "s-no_g1-clean-r1", "s-no_g1-nounit-r1", "s-no_g2-corrupt-r1"]


def test_explicit_env_file_overrides_and_must_exist(tiny_root, monkeypatch):
    import os
    import pytest
    from subsurface_agent.common import load_env
    monkeypatch.setenv("GEMINI_API_KEY", "from-shell")
    (tiny_root / ".env.keyB").write_text("GEMINI_API_KEY=from-file-b\n", encoding="utf-8")
    load_env(tiny_root, tiny_root / ".env.keyB")
    assert os.environ["GEMINI_API_KEY"] == "from-file-b"
    with pytest.raises(ValueError, match="not found"):
        load_env(tiny_root, tiny_root / ".env.missing")


def test_summary_can_rescore_runs_saved_in_another_folder(tiny_root):
    import shutil
    cases = setup(tiny_root)
    run_experiment(tiny_root, "m", cases, ["full"], 1, PlannerDouble(), log=lambda *_: None)
    original = summarize(tiny_root, "m", cases)
    saved = tiny_root / "logs" / "evidence" / "m"
    for run in (tiny_root / "logs" / "runs").glob("m-*"):
        shutil.copytree(run, saved / run.name)
        shutil.rmtree(run)
    rescored = summarize(tiny_root, "m", cases, runs_dir=saved)
    assert rescored["runs_scored"] == original["runs_scored"] == 3
    assert rescored["systems"] == original["systems"]


def test_answer_error_reads_the_prediction_file_from_the_given_folder(tiny_root):
    import shutil
    from subsurface_agent.scoring import Scorer
    cases = setup(tiny_root)
    run_experiment(tiny_root, "e", cases, ["full"], 1, PlannerDouble(), log=lambda *_: None)
    result = read_json(tiny_root / "logs" / "runs" / "e-full-clean-r1" / "result.json")
    moved = tiny_root / "elsewhere"
    shutil.copytree(tiny_root / "logs" / "runs", moved)
    shutil.rmtree(tiny_root / "logs" / "runs")
    assert Scorer(tiny_root).answer_error(result) is None
    assert abs(Scorer(tiny_root, moved).answer_error(result) - 0.01) < 1e-9
