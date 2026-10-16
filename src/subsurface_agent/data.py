"""Pinned public data acquisition and a declared whole-well evaluation cohort."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import pandas as pd

from .common import sha256, utc_now, write_json

SOURCE_COMMIT = "0ffc94f702feab81f6eb1f4d453e19754a557305"
BASE_URL = f"https://raw.githubusercontent.com/pddasig/Machine-Learning-Competition-2021/{SOURCE_COMMIT}/"
ARCHIVE_SHA256 = "816d45f63f374892986c4a23f785bb027b15c90e00a2c304cbce8a85e6416d35"
FEATURES = ["GR", "CALI", "DEN", "NEU", "RDEP", "RMED", "DTC"]
TARGETS = ["PHIF", "SW", "VSH"]
SPLITS = {"train": [0, 2, 4, 6, 8], "validation": [1, 5], "test": [3, 7]}
ALIASES = {"gamma ray": "GR", "gamma": "GR", "caliper": "CALI", "CAL": "CALI",
           "density": "DEN", "RHOB": "DEN", "neutron": "NEU", "NPHI": "NEU",
           "sonic": "DTC", "DT": "DTC", "porosity": "PHIF", "PHI": "PHIF",
           "water saturation": "SW", "shale volume": "VSH"}


def download_data(root: Path) -> dict:
    raw = root / "data" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ["data.zip", "README.md", "SPWLA_2021_ML_Tutorial.ipynb"]:
        destination = raw / name
        if not destination.exists():
            with urlopen(BASE_URL + name, timeout=90) as response:
                destination.write_bytes(response.read())
    if sha256(raw / "data.zip") != ARCHIVE_SHA256:
        raise ValueError("Pinned data.zip checksum mismatch; refuse to use changed data")
    with zipfile.ZipFile(raw / "data.zip") as archive:
        for name in ["train.csv", "test.csv"]:
            # Read exact known members; never extract arbitrary archive paths.
            (raw / name).write_bytes(archive.read(name))
    return {"source_commit": SOURCE_COMMIT, "archive_sha256": ARCHIVE_SHA256}


def load_raw(root: Path, filename: str = "train.csv") -> pd.DataFrame:
    if filename not in {"train.csv", "test.csv"}:
        raise ValueError("Unsupported source file")
    path = root / "data" / "raw" / filename
    frame = pd.read_csv(path).replace(-9999, np.nan)
    required = ["WELLNUM", "DEPTH", *FEATURES]
    if missing := set(required) - set(frame):
        raise ValueError(f"Missing source columns: {sorted(missing)}")
    if frame["WELLNUM"].isna().any() or frame["DEPTH"].isna().any():
        raise ValueError("Missing well/depth identity")
    if frame.duplicated(["WELLNUM", "DEPTH"]).any():
        raise ValueError("Duplicate well/depth keys")
    frame.insert(0, "sample_id", [f"{filename[:-4]}:{i}" for i in range(len(frame))])
    return frame


def valid_label_mask(frame: pd.DataFrame) -> pd.Series:
    targets = frame[TARGETS]
    finite = np.isfinite(targets).all(axis=1)
    bounded = targets.ge(0).all(axis=1) & targets.le(1).all(axis=1)
    inputs = np.isfinite(frame[FEATURES]).sum(axis=1) >= 4
    return finite & bounded & inputs


def prepare_data(root: Path) -> dict:
    raw = root / "data" / "raw"
    if sha256(raw / "data.zip") != ARCHIVE_SHA256:
        raise ValueError("Source archive checksum mismatch")
    with zipfile.ZipFile(raw / "data.zip") as archive:
        for name in ["train.csv", "test.csv"]:
            if hashlib.sha256(archive.read(name)).hexdigest() != sha256(raw / name):
                raise ValueError(f"Extracted {name} differs from pinned archive")
    frame = load_raw(root)
    all_wells = sorted(frame.WELLNUM.unique().tolist())
    if all_wells != sorted(sum(SPLITS.values(), [])):
        raise ValueError("Declared well split does not match the pinned source")
    mask = valid_label_mask(frame)
    eligible = frame.loc[mask].copy()
    finite = np.isfinite(frame[TARGETS]).all(axis=1)
    bounded = frame[TARGETS].ge(0).all(axis=1) & frame[TARGETS].le(1).all(axis=1)
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    # This feature-only file is the sole table exposed to the agent's runtime.
    frame[["sample_id", "WELLNUM", "DEPTH", *FEATURES]].to_csv(processed / "features.csv", index=False)
    split_counts = {}
    for split, wells in SPLITS.items():
        subset = eligible.loc[eligible.WELLNUM.isin(wells)]
        subset[["sample_id", "WELLNUM", "DEPTH", *FEATURES, *TARGETS]].to_csv(processed / f"{split}.csv", index=False)
        split_counts[split] = {"wells": wells, "rows": len(subset),
                               "per_well": subset.groupby("WELLNUM").size().to_dict()}
    source_test = load_raw(root, "test.csv")
    manifest = {
        "created_utc": utc_now(), "source_commit": SOURCE_COMMIT,
        "source_url": BASE_URL + "data.zip", "archive_sha256": ARCHIVE_SHA256,
        "train_csv_sha256": sha256(raw / "train.csv"), "raw_training_rows": len(frame),
        "raw_training_wells": all_wells, "raw_competition_test_rows": len(source_test),
        "raw_competition_test_wells": sorted(source_test.WELLNUM.unique().tolist()),
        "complete_finite_target_rows": int(finite.sum()),
        "complete_target_rows_outside_0_1": int((finite & ~bounded).sum()),
        "cohort_rows": int(mask.sum()),
        "selection_rule": "finite targets in [0,1] and at least 4/7 finite input curves; no clipping",
        "split_policy": "Prespecified whole-well 5/2/2 split; no test-guided tuning",
        "splits": split_counts, "features": FEATURES, "targets": TARGETS,
        "depth_unit": "ft", "depth_unit_source": BASE_URL + "SPWLA_2021_ML_Tutorial.ipynb",
        "unit_caveat": "Tutorial labels DTC ns/ft; this appears inconsistent with typical log units. No DTC conversion is performed.",
        "target_reference": "Petrophysicist interpreted reference values, not perfect physical truth",
        "competition_score_claim": False,
        "competition_test_policy": "Not scored: organizer labels lack identity keys; use held-out labeled training wells instead",
        "license_notice": "Creative Commons Attribution-NonCommercial-ShareAlike; version not specified in README",
        "processed_sha256": {p.name: sha256(p) for p in processed.glob("*.csv")},
    }
    write_json(root / "results" / "data_manifest.json", manifest)
    return manifest
