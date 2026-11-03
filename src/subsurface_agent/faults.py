"""Controlled artifact faults for G2 experiments. A fault is applied once, to the first prediction file of a run.

The planner is never told that a fault was injected; the run's offline `oracle` record says which fault was
applied and whether the final artifacts were valid. `shuffle_rows` is a benign control: the keyed file stays
correct, so a verifier that flags it is raising a false alarm.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

FAULTS = ("missing_file", "corrupt_values", "drop_rows", "duplicate_rows", "wrong_well",
          "nan_values", "stale_artifact", "shuffle_rows")
BENIGN = {"shuffle_rows"}


def apply_fault(kind: str, path: Path, frame: pd.DataFrame) -> None:
    """Alter the prediction CSV at `path`; `frame` is the feature table used to build a stale interval."""
    if kind not in FAULTS:
        raise ValueError(f"Unknown fault {kind!r}")
    if kind == "missing_file":
        path.unlink()
        return
    data = pd.read_csv(path)
    step = max(1, len(data) // 10)
    if kind == "corrupt_values":
        # Plausible values that stay within [0, 1], so only recomputation can detect them.
        rows = data.index[::step]
        data.loc[rows, "PHIF_pred"] = (data.loc[rows, "PHIF_pred"] + 0.05).clip(0, 1)
    elif kind == "drop_rows":
        data = data.iloc[: len(data) - step]
    elif kind == "duplicate_rows":
        data = pd.concat([data, data.head(5)], ignore_index=True)
    elif kind == "wrong_well":
        data["WELLNUM"] = data["WELLNUM"] + 1
    elif kind == "nan_values":
        data.loc[data.index[::step][:5], "SW_pred"] = np.nan
    elif kind == "stale_artifact":
        # Same values attached to a different interval of the same well, as if an old file were reused.
        well = frame.loc[frame.WELLNUM == data.WELLNUM.iloc[0]].sort_values("DEPTH")
        later = well.loc[well.DEPTH > data.DEPTH.max()]
        other = later if len(later) >= len(data) else well.loc[well.DEPTH < data.DEPTH.min()].tail(len(data))
        other = other.head(len(data))
        data = data.iloc[: len(other)].copy()
        data["sample_id"], data["DEPTH"] = other.sample_id.to_numpy(), other.DEPTH.to_numpy()
    elif kind == "shuffle_rows":
        data = data.sample(frac=1, random_state=0)
    data.to_csv(path, index=False)
