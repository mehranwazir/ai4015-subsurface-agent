import numpy as np
import pandas as pd
import pytest

from subsurface_agent.baseline import keyed_score, prediction_metrics
from subsurface_agent.data import TARGETS
from subsurface_agent.tools import ToolRuntime


def prediction(runtime):
    assert runtime.dispatch("inspect_dataset", {})["ok"]
    interval = runtime.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"})
    predicted = runtime.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    return interval, predicted


def test_metric_has_known_error_and_rejects_nonfinite():
    truth = np.array([[0., 0., 0.], [1., 1., 1.]])
    result = prediction_metrics(truth, truth + .1)
    assert result["macro_target_rmse"] == pytest.approx(.1)
    with pytest.raises(ValueError, match="Nonfinite"):
        prediction_metrics(truth, truth * np.nan)


def test_scoring_joins_keys_and_rejects_wrong_identity():
    truth = pd.DataFrame({"sample_id": ["a", "b"], "WELLNUM": [3, 3], "DEPTH": [1., 2.],
                          "PHIF": [.1, .2], "SW": [.3, .4], "VSH": [.2, .1]})
    predictions = truth.rename(columns={t: f"{t}_pred" for t in TARGETS}).iloc[::-1]
    assert keyed_score(truth, predictions)["macro_target_rmse"] == 0
    wrong = predictions.copy(); wrong.loc[wrong.index[0], "WELLNUM"] = 9
    with pytest.raises(ValueError, match="identity mismatch"):
        keyed_score(truth, wrong)


def test_tool_allowlist_and_feature_only_boundary(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run")
    assert not set(TARGETS) & set(runtime.frame)
    result = runtime.dispatch("run_python", {"code": "read secret"})
    assert result["error"] == "UNKNOWN_TOOL"
    assert runtime.dispatch("predict_properties", {"slice_id": "slice-0000000000000000"})["error"] == "INSPECT_FIRST"


def test_prediction_must_be_verified_before_answer(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run")
    _, predicted = prediction(runtime)
    assert runtime.dispatch("finish", {"status": "answer", "reason": "Done"})["error"] == "UNVERIFIED_RESULT"
    assert runtime.dispatch("verify_predictions", {"prediction_id": predicted["prediction_id"]})["verified"]
    assert runtime.dispatch("finish", {"status": "answer", "reason": "Done"})["ok"]


def test_corrupt_prediction_is_detected_without_target_labels(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run")
    _, result = prediction(runtime)
    ref = runtime.predictions[result["prediction_id"]]
    data = pd.read_csv(ref["path"]); data.loc[0, "PHIF_pred"] = .999
    data.to_csv(ref["path"], index=False)
    assert runtime.dispatch("verify_predictions", {"prediction_id": result["prediction_id"]})["error"] == "RECOMPUTE_MISMATCH"


def test_missing_artifact_can_be_repaired_by_repeat_execution(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run", omit_prediction_once=True)
    interval, result = prediction(runtime)
    assert runtime.dispatch("verify_predictions", {"prediction_id": result["prediction_id"]})["error"] == "MISSING_ARTIFACT"
    repaired = runtime.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    assert runtime.dispatch("verify_predictions", {"prediction_id": repaired["prediction_id"]})["verified"]


def test_tiny_interval_abstains_and_does_not_extrapolate(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run")
    runtime.dispatch("inspect_dataset", {})
    interval = runtime.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10600.1, "unit": "ft"})
    assert runtime.dispatch("predict_properties", {"slice_id": interval["slice_id"]})["error"] == "INSUFFICIENT_DATA"


def test_changed_feature_or_model_is_rejected(tiny_root):
    path = tiny_root / "data" / "processed" / "features.csv"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        ToolRuntime(tiny_root, tiny_root / "run")
