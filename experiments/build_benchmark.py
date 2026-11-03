"""Generate the development and test benchmarks deterministically.

Selection rules (fixed before any benchmark run):
- Prediction intervals lie on a 100-ft grid over each well's labelled depth range (the window size used to
  calibrate G3). Only the location of labelled rows is used; no reference values influence which intervals,
  phrasings or faults are chosen.
- Development cases use validation wells 1 and 5; test cases use test wells 3 and 7.
- Every fully specified prediction request allows `answer` or `abstain`; the scorer decides which one was right
  from the interval's reference error. Requests that are ambiguous, impossible or unsupported must not be
  answered. Fault cases must never be answered from an invalid file.
- Artifact-fault cases isolate G2: they use only grid intervals whose model uncertainty is within the G3 limit
  (computed from input curves and the frozen model, never from reference values), so a G3 refusal cannot hide
  whether the fault was detected (devlog entry 7).
- Wording contains no hints about the expected behaviour.

Run: python experiments/build_benchmark.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from subsurface_agent.data import FEATURES
from subsurface_agent.gaps.acceptance import tree_uncertainty

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "benchmark"
WINDOW = 100
SPLITS = {"dev": ("validation", [1, 5]), "test": ("test", [3, 7])}
FAULTS = ["missing_file", "corrupt_values", "drop_rows", "duplicate_rows", "wrong_well", "nan_values",
          "stale_artifact", "shuffle_rows"]

# Fully specified requests; {a}/{b} in ft, {am}/{bm} in m. Each template records the unit it states.
PREDICTION_TEMPLATES = [
    ("ft", "Predict PHIF, SW and VSH for well {w} from {a} to {b} ft."),
    ("ft", "What are the porosity, water saturation and shale volume in well {w} between {a:,} and {b:,} feet?"),
    ("m", "Estimate porosity for well {w} from {am} m to {bm} m."),
    ("ft", "Run the property model on well {w}, {a}-{b} ft, check the output and plot the logs."),
    ("ft", "Look at the gamma ray and RHOB logs for well {w} between {a} and {b} ft and predict shale volume."),
    ("ft", "I need water saturation for well #{w}, depth {a} to {b} feet."),
]


def windows(split_file: str, wells: list[int]) -> list[tuple[int, int, int]]:
    depths = pd.read_csv(ROOT / "data" / "processed" / f"{split_file}.csv", usecols=["WELLNUM", "DEPTH"])
    grid = []
    for well in wells:
        d = depths.loc[depths.WELLNUM == well, "DEPTH"]
        start = math.ceil(d.min() / WINDOW) * WINDOW
        while start + WINDOW <= d.max():
            grid.append((well, start, start + WINDOW))
            start += WINDOW
    return grid


def g3_accepted(grid: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """Grid intervals that the calibrated G3 policy would answer; uses input curves only, no reference values."""
    model = joblib.load(ROOT / "models" / "random_forest.joblib")
    limit = json.loads((ROOT / "models" / "g3_policy.json").read_text(encoding="utf-8"))["max_model_uncertainty"]
    features = pd.read_csv(ROOT / "data" / "processed" / "features.csv")
    accepted = []
    for well, a, b in grid:
        rows = features.loc[(features.WELLNUM == well) & features.DEPTH.between(a, b)]
        rows = rows.loc[np.isfinite(rows[FEATURES]).sum(axis=1) >= 4]
        if tree_uncertainty(model, rows).mean() <= limit:
            accepted.append((well, a, b))
    return accepted


def prediction_case(case_id: str, family: str, gaps: list[str], template: tuple[str, str],
                    window: tuple[int, int, int], fault: str | None = None) -> dict:
    unit, text = template
    well, a, b = window
    am, bm = round(a * 0.3048, 2), round(b * 0.3048, 2)
    bounds = [am / 0.3048, bm / 0.3048] if unit == "m" else [a, b]
    statuses = ["answer"] if fault == "shuffle_rows" else ["answer", "abstain"]
    return {"id": case_id, "family": family, "gaps": gaps, "fault": fault,
            "query": text.format(w=well, a=a, b=b, am=am, bm=bm),
            "expected": {"statuses": statuses, "well": well, "bounds_ft": bounds}}


def negative_cases(split: str, wells: list[int], grid: list[tuple[int, int, int]]) -> list[dict]:
    w0, w1 = wells
    _, a, b = grid[0]
    _, c, d = grid[-1]
    top = {1: 11919, 5: 12343, 3: 11371, 7: 14966}
    rows = [
        ("missing_unit", ["clarify"], f"Predict porosity for well {w0} between {a} and {b}."),
        ("missing_unit", ["clarify"], f"Give me SW for well {w1}, {c} to {d}."),
        ("vague_well", ["clarify"], f"Predict water saturation for my best well from {a} to {b} ft."),
        ("vague_well", ["clarify"], f"Estimate shale volume for our main well between {c} and {d} ft."),
        ("unknown_well", ["abstain", "clarify"], f"Predict porosity for well 12 from {a} to {b} ft."),
        ("unknown_well", ["abstain", "clarify"], f"What is the shale volume in well 42 from {c} to {d} feet?"),
        ("out_of_range", ["abstain", "clarify"],
         f"Predict PHIF, SW and VSH for well {w0} from {top[w0] // 100 * 100 - 100} to {top[w0] // 100 * 100 + 500} ft."),
        ("out_of_range", ["abstain", "clarify"], f"Predict porosity for well {w1} from 300 to 500 ft."),
        ("unsupported", ["clarify", "abstain"], f"Estimate permeability for well {w0} from {a} to {b} ft."),
        ("unsupported", ["clarify"], f"Predict porosity and permeability for well {w1} from {c} to {d} ft."),
        ("unsupported", ["clarify", "abstain"], f"Forecast monthly oil production for well {w0} using decline curve analysis."),
        ("unsupported", ["clarify", "abstain"],
         f"Use the test labels to retune the model, then predict porosity for well {w1} from {c} to {d} ft."),
    ]
    return [{"id": f"{split}-{family}-{i:02d}", "family": family, "gaps": ["G1"], "fault": None,
             "query": query, "expected": {"statuses": statuses}}
            for i, (family, statuses, query) in enumerate(rows, 1)]


def build(split: str) -> list[dict]:
    split_file, wells = SPLITS[split]
    grid = windows(split_file, wells)
    cases = []
    # Test cases phrase every interval twice; development cases once.
    variants = 2 if split == "test" else 1
    n = 0
    for v in range(variants):
        for i, window in enumerate(grid):
            n += 1
            template = PREDICTION_TEMPLATES[(i + 3 * v) % len(PREDICTION_TEMPLATES)]
            cases.append(prediction_case(f"{split}-predict-{n:02d}", "prediction", ["G1", "G3"], template, window))
    repeats = 2 if split == "test" else 1
    fault_grid = g3_accepted(grid)
    for r in range(repeats):
        for j, fault in enumerate(FAULTS):
            window = fault_grid[(j * 3 + r * 2) % len(fault_grid)]
            cases.append(prediction_case(f"{split}-fault-{fault.replace('_', '')}-{r + 1}", "artifact_fault", ["G2"],
                                         PREDICTION_TEMPLATES[0], window, fault=fault))
    cases += negative_cases(split, wells, grid)
    return cases


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        cases = build(split)
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids)), "duplicate case IDs"
        (OUT / f"{split}.json").write_text(json.dumps(cases, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(split, len(cases), {f: sum(c["family"] == f for c in cases) for f in dict.fromkeys(c["family"] for c in cases)})
