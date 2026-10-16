"""Small synthetic fixtures for software tests; never reported as research data."""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from subsurface_agent.common import sha256, write_json
from subsurface_agent.data import FEATURES, TARGETS


@pytest.fixture
def tiny_root(tmp_path: Path) -> Path:
    rng = np.random.default_rng(11)
    x = pd.DataFrame(rng.uniform(1, 3, (40, len(FEATURES))), columns=FEATURES)
    frame = x.copy()
    frame.insert(0, "DEPTH", np.arange(40) * .5 + 10600)
    frame.insert(0, "WELLNUM", 3)
    frame.insert(0, "sample_id", [f"train:{i}" for i in range(40)])
    path = tmp_path / "data" / "processed" / "features.csv"
    path.parent.mkdir(parents=True)
    frame.to_csv(path, index=False)
    y = rng.uniform(.1, .9, (40, 3))
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                          RandomForestRegressor(n_estimators=3, max_depth=3, n_jobs=1, random_state=1))
    model.fit(x, y)
    modelpath = tmp_path / "models" / "random_forest.joblib"
    modelpath.parent.mkdir(parents=True)
    joblib.dump(model, modelpath)
    write_json(modelpath.parent / "model_manifest.json", {
        "model_id": "synthetic-test-model", "model_sha256": sha256(modelpath),
        "features": FEATURES, "targets": TARGETS})
    write_json(tmp_path / "results" / "data_manifest.json", {
        "source_commit": "synthetic-test-fixture", "splits": {"test": {"wells": [3]}},
        "processed_sha256": {"features.csv": sha256(path)}})
    return tmp_path
