import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from subsurface_agent.baseline import adopt_reference_model
from subsurface_agent.common import read_json, write_json
from subsurface_agent.contracts import function_declarations
from subsurface_agent.data import FEATURES, exact_feature_overlap
from subsurface_agent.evaluation import evaluate_cases
from subsurface_agent.tools import ToolRuntime
from test_agent import ScriptedProvider


def test_missing_depth_unit_is_rejected_not_assumed(tiny_root):
    schema = {d["name"]: d for d in function_declarations()}["inspect_interval"]["parameters"]
    assert "unit" in schema["required"]
    runtime = ToolRuntime(tiny_root, tiny_root / "run")
    runtime.dispatch("inspect_dataset", {})
    result = runtime.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10610})
    assert result["error"] == "MISSING_UNIT"
    assert not runtime.slices


def test_reference_model_is_kept_when_refit_reproduces_predictions(tiny_root):
    model_dir = tiny_root / "models"
    probe = pd.read_csv(tiny_root / "data" / "processed" / "features.csv")[FEATURES]
    reference = joblib.load(model_dir / "random_forest.joblib")
    y = reference.predict(probe)

    def fit(seed):
        model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                              RandomForestRegressor(n_estimators=3, max_depth=3, n_jobs=1, random_state=seed))
        return model.fit(probe, y)

    adopted = adopt_reference_model(model_dir, reference, probe)
    assert adopted is not None and adopted[1]["model_id"] == "synthetic-test-model"
    assert adopt_reference_model(model_dir, fit(seed=99), probe) is None
    (model_dir / "random_forest.joblib").write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum mismatch"):
        adopt_reference_model(model_dir, reference, probe)


def test_evaluation_batches_never_overwrite_recorded_evidence(tiny_root):
    recorded = tiny_root / "results" / "agent_evaluation.json"
    write_json(recorded, {"recorded": "phase-1"})
    write_json(tiny_root / "evaluation" / "cases.json", [
        {"id": "predict", "query": "Predict well 3 from 10600 to 10619.5 ft",
         "expected": {"statuses": ["answer"], "well": 3, "tools": ["predict_properties", "verify_predictions"]}}])
    first = evaluate_cases(tiny_root, ScriptedProvider())
    second = evaluate_cases(tiny_root, ScriptedProvider())
    assert first["path"] != second["path"]
    assert read_json(tiny_root / first["path"])["passed"] == 1
    assert read_json(recorded) == {"recorded": "phase-1"}


def test_exact_feature_overlap_counts_identical_vectors_including_missing():
    train = pd.DataFrame({f: [1., 2.] for f in FEATURES})
    train.loc[1, "DTC"] = np.nan
    test = pd.DataFrame({f: [2., 3.] for f in FEATURES})
    test.loc[0, "DTC"] = np.nan
    assert exact_feature_overlap(train, test) == 1
    test.loc[0, "GR"] = 2.0000001
    assert exact_feature_overlap(train, test) == 0
