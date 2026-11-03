"""G3 evidence-based acceptance: answer only when observable evidence suggests the prediction is reliable.

Evidence for a predicted interval:
- input coverage (share of rows with at least four usable curves);
- model uncertainty: per-row standard deviation of the forest's tree predictions, averaged over PHIF/SW/VSH
  and over the interval;
- out-of-range share: rows with any input outside the training wells' 0.5-99.5% range (reported only).

The uncertainty threshold is calibrated on the validation wells only: sliding depth windows are scored against
their reference labels, and the threshold keeps the largest share of windows answerable while the share of
accepted windows whose mean property RMSE exceeds `max_window_rmse` stays at or below `max_risk`. On the
validation wells the out-of-range share did not track window error, so it is reported but not used to decide.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from ..common import read_json, sha256, utc_now, write_json
from ..data import FEATURES, SPLITS, TARGETS
from ..errors import ToolError

POLICY_PATH = Path("models") / "g3_policy.json"
# Declared before calibration: an acceptable answer has mean property RMSE <= 0.05 (fraction units), and at
# most 5% of accepted validation windows may break that requirement.
MAX_WINDOW_RMSE, MAX_RISK = 0.05, 0.05
WINDOW_FT, STEP_FT, MIN_ROWS = 100.0, 25.0, 40


def tree_uncertainty(model, features: pd.DataFrame) -> np.ndarray:
    """Per-row spread of the individual trees' predictions, averaged over the three targets."""
    transformed = model[:-1].transform(features[FEATURES])
    trees = np.stack([tree.predict(transformed) for tree in model[-1].estimators_])
    return trees.std(axis=0).mean(axis=1)


def out_of_range_share(features: pd.DataFrame, low: dict, high: dict) -> float:
    values = features[FEATURES]
    outside = (values.lt(pd.Series(low)) | values.gt(pd.Series(high))) & values.notna()
    return float(outside.any(axis=1).mean())


def evidence(model, features: pd.DataFrame, coverage: float, policy: dict) -> dict:
    uncertainty = float(tree_uncertainty(model, features).mean())
    result = {"input_coverage": coverage, "model_uncertainty": uncertainty,
              "out_of_range_share": out_of_range_share(features, policy["input_low"], policy["input_high"]),
              "max_model_uncertainty": policy["max_model_uncertainty"]}
    result["decision"] = "answer" if uncertainty <= policy["max_model_uncertainty"] else "abstain"
    return result


def check_answer(evidences: list[dict]) -> None:
    weak = [e for e in evidences if e["decision"] != "answer"]
    if weak:
        raise ToolError("LOW_EVIDENCE", f"Model uncertainty {weak[0]['model_uncertainty']:.4f} exceeds the calibrated "
                        f"limit {weak[0]['max_model_uncertainty']:.4f} for this interval; the prediction is not "
                        "reliable enough to report. Finish with abstain and give this reason.")


def validation_windows(model, validation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for well, group in validation.groupby("WELLNUM"):
        group = group.sort_values("DEPTH")
        uncertainty = tree_uncertainty(model, group)
        predicted = model.predict(group[FEATURES])
        for start in np.arange(group.DEPTH.min(), group.DEPTH.max() - WINDOW_FT / 2, STEP_FT):
            mask = group.DEPTH.between(start, start + WINDOW_FT).to_numpy()
            if mask.sum() < MIN_ROWS:
                continue
            error = np.sqrt(((group.loc[mask, TARGETS].to_numpy() - predicted[mask]) ** 2).mean(axis=0)).mean()
            rows.append({"well": int(well), "start_ft": float(start), "rows": int(mask.sum()),
                         "model_uncertainty": float(uncertainty[mask].mean()), "rmse": float(error)})
    return pd.DataFrame(rows)


def choose_threshold(windows: pd.DataFrame) -> dict:
    best = {"max_model_uncertainty": 0.0, "coverage": 0.0, "risk": 0.0}
    for limit in sorted(windows.model_uncertainty.unique()):
        accepted = windows.loc[windows.model_uncertainty <= limit]
        risk = float((accepted.rmse > MAX_WINDOW_RMSE).mean())
        coverage = len(accepted) / len(windows)
        if risk <= MAX_RISK and coverage > best["coverage"]:
            best = {"max_model_uncertainty": float(limit), "coverage": coverage, "risk": risk}
    return best


def calibrate(root: Path) -> dict:
    """Fit the G3 policy from training-well input ranges and validation-well windows; never reads test labels."""
    processed = root / "data" / "processed"
    model = joblib.load(root / "models" / "random_forest.joblib")
    train, validation = pd.read_csv(processed / "train.csv"), pd.read_csv(processed / "validation.csv")
    if set(validation.WELLNUM) != set(SPLITS["validation"]):
        raise ValueError("Calibration must use exactly the validation wells")
    windows = validation_windows(model, validation)
    chosen = choose_threshold(windows)
    base_risk = float((windows.rmse > MAX_WINDOW_RMSE).mean())
    policy = {"created_utc": utc_now(), "model_sha256": sha256(root / "models" / "random_forest.joblib"),
              "calibration_wells": SPLITS["validation"], "window_ft": WINDOW_FT, "step_ft": STEP_FT,
              "min_rows": MIN_ROWS, "windows": len(windows), "max_window_rmse": MAX_WINDOW_RMSE,
              "max_risk": MAX_RISK, **chosen, "risk_if_always_answer": base_risk,
              "spearman_uncertainty_rmse": float(windows.model_uncertainty.corr(windows.rmse, method="spearman")),
              "input_low": train[FEATURES].quantile(.005).to_dict(),
              "input_high": train[FEATURES].quantile(.995).to_dict()}
    write_json(root / POLICY_PATH, policy)
    return policy


def load_policy(root: Path, model_sha256: str) -> dict:
    path = root / POLICY_PATH
    if not path.exists():
        raise ValueError("G3 policy missing; run `python -m subsurface_agent calibrate-g3`")
    policy = read_json(path)
    if policy["model_sha256"] != model_sha256:
        raise ValueError("G3 policy was calibrated for a different model; rerun calibrate-g3")
    return policy
