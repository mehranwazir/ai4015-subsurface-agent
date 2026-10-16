"""Fixed train-only preprocessing, mean comparator, and held-out-well scoring."""
from __future__ import annotations

import platform
import time
from importlib.metadata import version
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.pipeline import make_pipeline

from .common import read_json, sha256, utc_now, write_json
from .data import FEATURES, TARGETS


def prediction_metrics(truth: np.ndarray, prediction: np.ndarray) -> dict:
    if truth.shape != prediction.shape or truth.ndim != 2 or truth.shape[1] != 3:
        raise ValueError("Expected matching (rows, 3) reference/prediction arrays")
    if not np.isfinite(truth).all() or not np.isfinite(prediction).all():
        raise ValueError("Nonfinite reference or prediction")
    if len(truth) < 2:
        raise ValueError("At least two rows required for evaluation")
    scores = {}
    for i, target in enumerate(TARGETS):
        scores[target] = {"rmse": float(np.sqrt(np.mean((truth[:, i] - prediction[:, i]) ** 2))),
                          "mae": float(mean_absolute_error(truth[:, i], prediction[:, i])),
                          "r2": float(r2_score(truth[:, i], prediction[:, i])) if np.var(truth[:, i]) > 0 else None}
    return {"rows": len(truth), "targets": scores,
            "macro_target_rmse": float(np.mean([s["rmse"] for s in scores.values()])),
            "out_of_bounds_prediction_values": int(((prediction < 0) | (prediction > 1)).sum())}


def keyed_score(truth: pd.DataFrame, predictions: pd.DataFrame) -> dict:
    """One-to-one semantic join, independent of row order; no silent dropping."""
    keys = ["sample_id", "WELLNUM", "DEPTH"]
    for data in [truth, predictions]:
        if data.duplicated(keys).any() or data.sample_id.duplicated().any():
            raise ValueError("Duplicate prediction/reference identity")
    if set(truth.sample_id) != set(predictions.sample_id):
        raise ValueError("Prediction and reference sample sets differ")
    merged = truth[keys + TARGETS].merge(predictions, on=keys, validate="one_to_one")
    if len(merged) != len(truth):
        raise ValueError("Well/depth identity mismatch")
    predcols = [f"{target}_pred" for target in TARGETS]
    return prediction_metrics(merged[TARGETS].to_numpy(), merged[predcols].to_numpy())


def save_log_plot(frame: pd.DataFrame, destination: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(10, 6), sharey=True)
    for ax, target in zip(axes, TARGETS):
        ax.plot(frame[f"{target}_pred"], frame.DEPTH, label="Prediction", linewidth=1)
        if target in frame:
            ax.plot(frame[target], frame.DEPTH, label="Reference", alpha=.7, linewidth=.8)
        ax.set_xlabel(f"{target} (fraction)"); ax.grid(alpha=.25)
    axes[0].set_ylabel("Measured depth (ft)"); axes[0].invert_yaxis()
    axes[0].legend(fontsize=8)
    fig.suptitle(f"Well {int(frame.WELLNUM.iloc[0])}: research prediction")
    fig.tight_layout(rect=[0, 0, 1, .95]); destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=140, bbox_inches="tight"); plt.close(fig)


def run_baseline(root: Path) -> dict:
    manifest = read_json(root / "results" / "data_manifest.json")
    processed = root / "data" / "processed"
    for name, expected in manifest["processed_sha256"].items():
        if sha256(processed / name) != expected:
            raise ValueError(f"Prepared data changed: {name}")
    frames = {split: pd.read_csv(processed / f"{split}.csv") for split in ["train", "validation", "test"]}
    groups = [set(frame.WELLNUM) for frame in frames.values()]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("Well leakage between splits")
    train = frames["train"]
    started = time.perf_counter()
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                          RandomForestRegressor(n_estimators=80, max_depth=10,
                                                min_samples_leaf=3, n_jobs=1, random_state=42))
    model.fit(train[FEATURES], train[TARGETS])
    mean = make_pipeline(SimpleImputer(strategy="median"), DummyRegressor(strategy="mean"))
    mean.fit(train[FEATURES], train[TARGETS])
    fit_seconds = time.perf_counter() - started
    model_dir = root / "models"; model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_dir / "random_forest.joblib")
    info = {"model_id": "rf80-depth10-seed42-v1", "features": FEATURES, "targets": TARGETS,
            "model_sha256": sha256(model_dir / "random_forest.joblib"),
            "train_wells": manifest["splits"]["train"]["wells"],
            "fit_seconds": fit_seconds, "data_archive_sha256": manifest["archive_sha256"]}
    write_json(model_dir / "model_manifest.json", info)
    results = {"created_utc": utc_now(), "model": info,
               "versions": {n: version(n) for n in ["numpy", "pandas", "scikit-learn", "joblib", "matplotlib", "pydantic", "requests"]},
               "python": platform.python_version(), "platform": platform.platform(), "splits": {},
               "protocol": "Fixed hyperparameters; no test-based model selection; custom whole-well split, not paper/competition reproduction"}
    for split in ["validation", "test"]:
        frame = frames[split]
        scores = {}
        for name, estimator in [("mean", mean), ("random_forest", model)]:
            predicted = estimator.predict(frame[FEATURES])
            artifact = frame[["sample_id", "WELLNUM", "DEPTH"]].copy()
            for i, target in enumerate(TARGETS):
                artifact[f"{target}_pred"] = predicted[:, i]
            destination = root / "results" / f"{split}_{name}_predictions.csv"
            artifact.to_csv(destination, index=False)
            scores[name] = {"pooled": keyed_score(frame, artifact), "per_well": {}}
            for well in sorted(frame.WELLNUM.unique()):
                ref = frame.loc[frame.WELLNUM == well]
                pred = artifact.loc[artifact.WELLNUM == well]
                scores[name]["per_well"][str(int(well))] = keyed_score(ref, pred)
            scores[name]["macro_well_rmse"] = float(np.mean([s["macro_target_rmse"] for s in scores[name]["per_well"].values()]))
        results["splits"][split] = scores
    test = frames["test"]
    predictions = pd.read_csv(root / "results" / "test_random_forest_predictions.csv")
    combined = test.merge(predictions, on=["sample_id", "WELLNUM", "DEPTH"], validate="one_to_one")
    for well, group in combined.groupby("WELLNUM"):
        save_log_plot(group, root / "results" / "figures" / f"test_well_{int(well)}.png")
    write_json(root / "results" / "baseline_metrics.json", results)
    return results
