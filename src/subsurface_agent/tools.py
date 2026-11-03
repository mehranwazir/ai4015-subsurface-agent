"""Read-only scientific data plus allowlisted bounded artifact-producing tools."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pydantic import ValidationError

from .baseline import save_log_plot
from .common import clean_json, read_json, sha256
from .config import PRESETS, SystemConfig
from .contracts import CONTRACTS, Interval
from .data import ALIASES, FEATURES, TARGETS
from .errors import ToolError
from .faults import apply_fault
from .gaps import acceptance, grounding, verification


def canonical_curve(name: str) -> str:
    if name.upper() in FEATURES:
        return name.upper()
    lookup = {k.casefold(): v for k, v in ALIASES.items()}
    canonical = lookup.get(name.casefold())
    if canonical not in FEATURES:
        raise ToolError("UNKNOWN_CURVE", f"Unsupported input curve {name!r}; available: {FEATURES}")
    return canonical


def select_interval(frame: pd.DataFrame, request: Interval) -> pd.DataFrame:
    if request.well not in set(frame.WELLNUM):
        raise ToolError("UNKNOWN_WELL", f"Well {request.well} does not exist")
    start, end = request.start, request.end
    if request.unit == "m":
        start, end = start / 0.3048, end / 0.3048
    # Preserve inclusive boundaries under reversible ft/m floating-point conversion.
    mask = (frame.WELLNUM == request.well) & frame.DEPTH.between(start - 1e-8, end + 1e-8)
    result = frame.loc[mask].copy()
    if result.empty:
        raise ToolError("EMPTY_INTERVAL", "No samples in requested interval")
    return result


class ToolRuntime:
    def __init__(self, root: Path, run_dir: Path, *, omit_prediction_once: bool = False,
                 query: str = "", config: SystemConfig = PRESETS["phase1"], fault: str | None = None):
        self.config = config
        # `omit_prediction_once` is the Phase 1 name for the missing-file fault.
        self.fault = "missing_file" if omit_prediction_once else fault
        self.pending_fault, self.fault_applied = self.fault, False
        self.attempts: dict[str, int] = {}
        self.facts = grounding.extract_request_facts(query)
        self.root, self.run_dir = root.resolve(), run_dir.resolve()
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = read_json(root / "results" / "data_manifest.json")
        self.model_info = read_json(root / "models" / "model_manifest.json")
        model_path = root / "models" / "random_forest.joblib"
        if sha256(model_path) != self.model_info["model_sha256"]:
            raise ValueError("Model checksum mismatch; only load trusted locally trained models")
        # Only this package's locally trained, checksum-matched model is loaded.
        self.model = joblib.load(model_path)
        self.policy = acceptance.load_policy(root, self.model_info["model_sha256"]) if config.acceptance else None
        feature_path = root / "data" / "processed" / "features.csv"
        if sha256(feature_path) != self.manifest["processed_sha256"]["features.csv"]:
            raise ValueError("Feature-only data checksum mismatch")
        self.frame = pd.read_csv(feature_path)
        self.well_ranges = {int(w): (float(r["min"]), float(r["max"]))
                            for w, r in self.frame.groupby("WELLNUM").DEPTH.agg(["min", "max"]).iterrows()}
        self.slices: dict[str, pd.DataFrame] = {}
        self.predictions: dict[str, dict] = {}
        self.verified: set[str] = set()
        self.outputs: list[dict] = []
        self.inspected = False

    def dispatch(self, name: str, arguments: dict) -> dict:
        if name not in CONTRACTS:
            return {"ok": False, "error": "UNKNOWN_TOOL", "message": "Tool is not allowlisted", "recoverable": False}
        try:
            request = CONTRACTS[name].model_validate(arguments)
            # Clarifying or abstaining needs no data access; answers are checked in finish().
            if name not in ("inspect_dataset", "finish") and not self.inspected:
                raise ToolError("INSPECT_FIRST", "Call inspect_dataset before other tools", True)
            if self.config.grounding:
                if name == "inspect_interval":
                    grounding.check_interval(request, self.facts, self.well_ranges)
                elif name == "predict_properties":
                    grounding.check_prediction_request(self.facts)
                elif name == "finish" and request.status == "answer":
                    grounding.check_answer(self.facts)
            output = getattr(self, name)(**request.model_dump())
            result = {"ok": True, **clean_json(output)}
        except ValidationError as exc:
            if any(e["type"] == "missing" and e["loc"] == ("unit",) for e in exc.errors()):
                result = {"ok": False, "error": "MISSING_UNIT",
                          "message": "Depth unit not given. Use ft or m only if the user stated it; otherwise finish with clarify.",
                          "recoverable": True}
            else:
                result = {"ok": False, "error": "INVALID_ARGUMENTS", "message": str(exc), "recoverable": True}
        except ToolError as exc:
            result = {"ok": False, "error": exc.code, "message": str(exc), "recoverable": exc.recoverable}
        except (OSError, ValueError, KeyError) as exc:
            # No provider credentials are present in these tool errors.
            result = {"ok": False, "error": "TOOL_FAILURE", "message": str(exc), "recoverable": False}
        self.outputs.append({"tool": name, "arguments": arguments, "result": result})
        return result

    def prompt_context(self) -> str:
        """Configuration-dependent planner context; empty unless G1 grounding is enabled."""
        if not self.config.grounding:
            return ""
        return grounding.registry_context(self.frame, FEATURES, ALIASES, TARGETS)

    def inspect_dataset(self):
        self.inspected = True
        ranges = self.frame.groupby("WELLNUM").DEPTH.agg(["min", "max", "size"])
        return {"dataset": "SPWLA-2021-pinned", "source_commit": self.manifest["source_commit"],
                "wells": {str(int(i)): {"min_depth_ft": r["min"], "max_depth_ft": r["max"], "rows": int(r["size"])}
                          for i, r in ranges.iterrows()},
                "features": FEATURES, "aliases": ALIASES, "targets": TARGETS,
                "depth_unit": "ft", "target_unit": "fraction",
                "evaluation_test_wells": self.manifest["splits"]["test"]["wells"],
                "model_id": self.model_info["model_id"],
                "limits": "Only PHIF/SW/VSH prediction. No permeability, economics or production forecasting. Do not guess units/identifiers."}

    def inspect_interval(self, **arguments):
        request = Interval.model_validate(arguments)
        curves = [canonical_curve(c) for c in request.curves] if request.curves else FEATURES
        subset = select_interval(self.frame, request)
        identity = json.dumps(subset.sample_id.tolist(), separators=(",", ":"))
        slice_id = "slice-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
        self.slices[slice_id] = subset
        quality = np.isfinite(subset[FEATURES]).sum(axis=1) >= 4
        return {"slice_id": slice_id, "well": request.well, "rows": len(subset),
                "depth_min_ft": float(subset.DEPTH.min()), "depth_max_ft": float(subset.DEPTH.max()),
                "requested_curves": curves, "eligible_input_rows": int(quality.sum()),
                "input_coverage": float(quality.mean()),
                "missing_fraction": subset[curves].isna().mean().to_dict(),
                "summary": {c: {"mean": subset[c].mean(), "min": subset[c].min(), "max": subset[c].max()} for c in curves}}

    def predict_properties(self, slice_id: str):
        if slice_id not in self.slices:
            raise ToolError("UNKNOWN_SLICE", "Inspect the requested interval before predicting", True)
        subset = self.slices[slice_id]
        quality = np.isfinite(subset[FEATURES]).sum(axis=1) >= 4
        coverage = float(quality.mean())
        if quality.sum() < 10 or coverage < .6:
            raise ToolError("INSUFFICIENT_DATA", "Need at least 10 usable rows and 60% input coverage; abstain or ask for a suitable interval")
        eligible = subset.loc[quality].copy()
        prediction = self.model.predict(eligible[FEATURES])
        output = eligible[["sample_id", "WELLNUM", "DEPTH"]].copy()
        for i, target in enumerate(TARGETS):
            output[f"{target}_pred"] = prediction[:, i]
        identifier = hashlib.sha256((slice_id + self.model_info["model_sha256"]).encode()).hexdigest()[:16]
        prediction_id = "pred-" + identifier
        relative = f"{prediction_id}.csv"
        destination = self.run_dir / relative
        attempts = self.attempts.get(slice_id, 0) + 1
        if self.config.verification:
            verification.check_repair_budget(attempts - 1)
        self.attempts[slice_id] = attempts
        output.to_csv(destination, index=False)
        injected = None
        if self.pending_fault:
            apply_fault(self.pending_fault, destination, self.frame)
            injected, self.pending_fault, self.fault_applied = self.pending_fault, None, True
        self.predictions[prediction_id] = {"path": destination, "inputs": eligible, "slice_id": slice_id}
        self.verified.discard(prediction_id)
        result = {"prediction_id": prediction_id, "slice_id": slice_id,
                  "artifact": relative, "well": int(subset.WELLNUM.iloc[0]),
                  "rows": len(output), "input_coverage": coverage,
                  "model_id": self.model_info["model_id"],
                  "mean_prediction": {t: float(output[f"{t}_pred"].mean()) for t in TARGETS},
                  "test_labels_used": False}
        if self.policy:
            self.predictions[prediction_id]["evidence"] = acceptance.evidence(
                self.model, eligible, coverage, self.policy)
            result["evidence"] = self.predictions[prediction_id]["evidence"]
        if self.config.name == "phase1":
            # Recorded Phase 1 outputs exposed the simulated omission; later configurations hide faults.
            result["simulation_omitted_artifact"] = injected == "missing_file"
        return result

    def verify_predictions(self, prediction_id: str):
        if prediction_id not in self.predictions:
            raise ToolError("UNKNOWN_PREDICTION", "No prediction artifact with this ID", True)
        metadata = self.predictions[prediction_id]
        if not self.config.verification:
            # G2 switched off: the step accepts the artifact without inspecting it.
            self.verified.add(prediction_id)
            return {"prediction_id": prediction_id, "verified": True, "rows": len(metadata["inputs"]),
                    "scientific_accuracy_claim": False,
                    "meaning": "Execution/artifact consistency only; no reference target labels used"}
        details = verification.check_artifact(metadata["path"], metadata["inputs"], self.model)
        self.verified.add(prediction_id)
        return {"prediction_id": prediction_id, "verified": True, "rows": details["rows"],
                "sha256": sha256(metadata["path"]),
                "max_abs_recompute_difference": details["max_abs_recompute_difference"],
                "scientific_accuracy_claim": False,
                "meaning": "Execution/artifact consistency only; no reference target labels used"}

    def plot_logs(self, prediction_id: str):
        if self.config.verification and prediction_id not in self.verified:
            raise ToolError("VERIFY_FIRST", "Verify this prediction before plotting", True)
        frame = pd.read_csv(self.predictions[prediction_id]["path"])
        artifact = f"{prediction_id}.png"
        save_log_plot(frame, self.run_dir / artifact)
        return {"prediction_id": prediction_id, "artifact": artifact, "rows": len(frame)}

    def finish(self, status: str, reason: str):
        if status == "answer":
            if self.config.verification and self.predictions and set(self.predictions) - self.verified:
                raise ToolError("UNVERIFIED_RESULT", "Cannot answer with unverified predictions", True)
            if not self.inspected:
                raise ToolError("NO_EVIDENCE", "Inspect data before answering", True)
            if self.policy:
                acceptance.check_answer([m["evidence"] for m in self.predictions.values()])
        return {"status": status, "reason": reason, "verified_predictions": sorted(self.verified)}

    def audit(self) -> dict:
        """Offline record of injected faults and final artifact validity; never returned to the planner."""
        validity = {}
        for prediction_id, metadata in self.predictions.items():
            try:
                verification.check_artifact(metadata["path"], metadata["inputs"], self.model)
                validity[prediction_id] = "valid"
            except ToolError as exc:
                validity[prediction_id] = exc.code
        return {"fault": self.fault, "fault_applied": self.fault_applied, "artifacts": validity,
                "final_artifacts_valid": all(v == "valid" for v in validity.values()) if validity else None}
