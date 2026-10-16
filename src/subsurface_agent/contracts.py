"""Validated public interfaces. Tool arguments never include filesystem paths."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Empty(Contract):
    pass


class Interval(Contract):
    well: int = Field(ge=0)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    unit: Literal["ft", "m"] = "ft"
    curves: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def ordered(self):
        if self.start >= self.end:
            raise ValueError("start must be below end")
        return self


class SliceRef(Contract):
    slice_id: str = Field(pattern=r"^slice-[0-9a-f]{16}$")


class PredictionRef(Contract):
    prediction_id: str = Field(pattern=r"^pred-[0-9a-f]{16}$")


class Finish(Contract):
    status: Literal["answer", "clarify", "abstain"]
    reason: str = Field(min_length=1, max_length=600)


CONTRACTS = {"inspect_dataset": Empty, "inspect_interval": Interval,
             "predict_properties": SliceRef, "verify_predictions": PredictionRef,
             "plot_logs": PredictionRef, "finish": Finish}

DESCRIPTIONS = {
    "inspect_dataset": "Inspect actual available wells, curves, units, targets, and split policy. Call this first.",
    "inspect_interval": "Load a single well/depth interval; normalize ft/m and known curve aliases. No target labels are exposed. Use unit ft or m, never guess missing units.",
    "predict_properties": "Predict PHIF, SW and VSH for a previously inspected slice using the frozen Random Forest. No fitting or test labels. Returns an artifact ID.",
    "verify_predictions": "Verify a prediction artifact's identity, finiteness, ranges, and agreement with deterministic recomputation. Missing artifact is recoverable by predicting again.",
    "plot_logs": "Plot an already verified prediction artifact. No labels or hidden reference data are used.",
    "finish": "Finish: answer only after requested actions succeed; clarify ambiguity/unsupported requests; abstain on insufficient data. An answer involving predictions requires verification.",
}


def function_declarations() -> list[dict]:
    """Translate our flat Pydantic contracts to Gemini's Schema subset."""
    def schema_subset(value):
        if isinstance(value, list):
            return [schema_subset(v) for v in value]
        if not isinstance(value, dict):
            return value
        unsupported = {"title", "additionalProperties", "default", "pattern", "minLength", "maxLength"}
        return {k: schema_subset(v) for k, v in value.items() if k not in unsupported}
    declarations = []
    for name, model in CONTRACTS.items():
        declaration = {"name": name, "description": DESCRIPTIONS[name]}
        if model is not Empty:
            declaration["parameters"] = schema_subset(model.model_json_schema())
        declarations.append(declaration)
    return declarations
