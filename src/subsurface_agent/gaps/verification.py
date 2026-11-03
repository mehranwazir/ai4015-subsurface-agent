"""G2 artifact verification and bounded repair.

The verifier checks a saved prediction file against the inputs it was produced from: schema, sample/well/depth
identity, finite values, declared bounds and agreement with a frozen-model recomputation. It uses no reference
labels, so it establishes execution consistency, not geological correctness.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..data import FEATURES, TARGETS
from ..errors import ToolError

KEYS = ["sample_id", "WELLNUM", "DEPTH"]
COLUMNS = [f"{t}_pred" for t in TARGETS]
# Regenerations allowed per slice before the planner must stop instead of retrying.
REPAIR_LIMIT = 2


def check_artifact(path: Path, inputs: pd.DataFrame, model) -> dict:
    """Raise a recoverable ToolError describing the first inconsistency, or return check details."""
    if not path.exists():
        raise ToolError("MISSING_ARTIFACT", "Prediction CSV missing; repeat predict_properties for the same slice", True)
    actual = pd.read_csv(path)
    if set(KEYS + COLUMNS) != set(actual.columns):
        raise ToolError("ARTIFACT_SCHEMA", "Prediction column schema differs", True)
    if actual.sample_id.duplicated().any() or set(actual.sample_id) != set(inputs.sample_id):
        raise ToolError("ARTIFACT_IDENTITY", "Prediction sample identity differs", True)
    aligned = inputs.merge(actual, on=KEYS, validate="one_to_one")
    if len(aligned) != len(inputs):
        raise ToolError("ARTIFACT_IDENTITY", "Prediction well/depth identity differs", True)
    values = aligned[COLUMNS].to_numpy()
    if not np.isfinite(values).all():
        raise ToolError("NONFINITE_RESULT", "Prediction contains NaN/infinite values", True)
    if ((values < 0) | (values > 1)).any():
        raise ToolError("BOUNDS_VIOLATION", "Prediction outside declared fraction range", True)
    reference = model.predict(aligned[FEATURES])
    max_difference = float(np.max(np.abs(values - reference)))
    if not np.allclose(values, reference, rtol=1e-10, atol=1e-12):
        raise ToolError("RECOMPUTE_MISMATCH", "Stored prediction differs from frozen-model recomputation", True)
    return {"rows": len(actual), "max_abs_recompute_difference": max_difference}


def check_repair_budget(attempts: int) -> None:
    if attempts > REPAIR_LIMIT:
        raise ToolError("REPAIR_LIMIT", f"This slice was regenerated {REPAIR_LIMIT} times without a valid artifact; "
                        "stop and finish with abstain.")
