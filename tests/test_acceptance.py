import pandas as pd
import pytest

from subsurface_agent.common import read_json, write_json
from subsurface_agent.config import get_config
from subsurface_agent.gaps.acceptance import MAX_RISK, MAX_WINDOW_RMSE, choose_threshold, load_policy
from subsurface_agent.tools import ToolRuntime

QUERY = "Predict PHIF, SW and VSH for well 3 from 10600 to 10619.5 ft and verify the result."
INTERVAL = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}


def test_threshold_keeps_most_windows_while_bounding_bad_answers():
    windows = pd.DataFrame({"model_uncertainty": [.01, .02, .03, .04, .05],
                            "rmse": [.02, .03, .04, .09, .12]})
    chosen = choose_threshold(windows)
    assert chosen["max_model_uncertainty"] == .03 and chosen["coverage"] == .6
    assert chosen["risk"] <= MAX_RISK and MAX_WINDOW_RMSE == .05


def predicted(tiny_root, config, limit):
    policy_path = tiny_root / "models" / "g3_policy.json"
    write_json(policy_path, {**read_json(policy_path), "max_model_uncertainty": limit})
    runtime = ToolRuntime(tiny_root, tiny_root / f"run-{config}-{limit}", query=QUERY, config=get_config(config))
    runtime.dispatch("inspect_dataset", {})
    interval = runtime.dispatch("inspect_interval", INTERVAL)
    prediction = runtime.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    runtime.dispatch("verify_predictions", {"prediction_id": prediction["prediction_id"]})
    return runtime, prediction


def test_uncertain_prediction_cannot_be_reported_as_an_answer(tiny_root):
    runtime, prediction = predicted(tiny_root, "full", 0.0)
    assert prediction["evidence"]["decision"] == "abstain"
    answer = runtime.dispatch("finish", {"status": "answer", "reason": "Done"})
    assert (answer["error"], answer["recoverable"]) == ("LOW_EVIDENCE", False)
    assert runtime.dispatch("finish", {"status": "abstain", "reason": "Too uncertain"})["ok"]

    confident, prediction = predicted(tiny_root, "full", 1.0)
    assert prediction["evidence"]["decision"] == "answer"
    assert confident.dispatch("finish", {"status": "answer", "reason": "Done"})["ok"]


def test_without_g3_the_system_always_answers(tiny_root):
    runtime, prediction = predicted(tiny_root, "no_g3", 0.0)
    assert "evidence" not in prediction
    assert runtime.dispatch("finish", {"status": "answer", "reason": "Done"})["ok"]


def test_policy_must_match_the_model(tiny_root):
    policy_path = tiny_root / "models" / "g3_policy.json"
    write_json(policy_path, {**read_json(policy_path), "model_sha256": "other"})
    with pytest.raises(ValueError, match="different model"):
        load_policy(tiny_root, read_json(tiny_root / "models" / "model_manifest.json")["model_sha256"])


def test_evidence_rule_is_in_the_prompt_only_when_g3_is_on(tiny_root):
    rule = "EVIDENCE RULE"
    on = ToolRuntime(tiny_root, tiny_root / "ctx-on", query=QUERY, config=get_config("full"))
    off = ToolRuntime(tiny_root, tiny_root / "ctx-off", query=QUERY, config=get_config("no_g3"))
    assert rule in on.prompt_context() and rule not in off.prompt_context()
    assert "GROUNDING CHECKLIST" in off.prompt_context()
