"""G1 request grounding: interval arguments must come from the user's own words, not the planner.

Live Phase 1 runs showed the planner filling in `unit="ft"` for a request that stated no unit. Typed
contracts cannot catch this because the planner supplies the field itself, so the arguments are
compared against facts extracted deterministically from the original request text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from ..contracts import Interval
from ..data import ALIASES, FEATURES
from ..errors import ToolError

UNIT_WORDS = {"ft": "ft", "feet": "ft", "foot": "ft", "m": "m",
              "meter": "m", "meters": "m", "metre": "m", "metres": "m"}
WELL = re.compile(r"\bwells?[\s#:-]*(?:no\.?|number|num|id)?[\s#:-]*(\d+)\b", re.I)
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
UNIT_WORD = re.compile(r"\b(ft|feet|foot|meters?|metres?)\b", re.I)
UNIT_AFTER_NUMBER = re.compile(r"\d\s*(m)\b", re.I)
TARGET_WORDS = {"porosity": "PHIF", "phif": "PHIF", "phi": "PHIF", "water saturation": "SW",
                "saturation": "SW", "sw": "SW", "shale volume": "VSH", "shale": "VSH", "vsh": "VSH"}
UNSUPPORTED_WORDS = {"permeability": "permeability", "perm": "permeability", "millidarcy": "permeability",
                     "production": "production forecasting", "forecast": "production forecasting",
                     "decline curve": "production forecasting", "npv": "economics",
                     "net present value": "economics", "economic": "economics", "revenue": "economics",
                     "lithology": "lithology", "facies": "lithology", "net pay": "net pay",
                     "reserves": "reserves", "oil in place": "reserves", "retrain": "model changes",
                     "re-train": "model changes", "tune": "model changes", "test labels": "test-label access"}
CURVE_WORDS = {**{f.lower(): f for f in FEATURES},
               **{k.lower(): v for k, v in ALIASES.items() if v in FEATURES}}


def _words(table: dict, text: str) -> set[str]:
    """Values whose word or phrase (optionally plural) occurs in the text as a whole word."""
    return {value for word, value in table.items()
            if re.search(r"(?<![\w-])" + re.escape(word) + r"(?:s|es)?(?![\w-])", text, re.I)}


@dataclass
class RequestFacts:
    wells: set[int] = field(default_factory=set)
    depths: list[float] = field(default_factory=list)
    units: set[str] = field(default_factory=set)
    targets: set[str] = field(default_factory=set)
    unsupported: set[str] = field(default_factory=set)
    curves: set[str] = field(default_factory=set)


def extract_request_facts(text: str) -> RequestFacts:
    facts = RequestFacts()
    well_spans = []
    for match in WELL.finditer(text):
        facts.wells.add(int(match.group(1)))
        well_spans.append(match.span(1))
    for match in NUMBER.finditer(text):
        if not any(start <= match.start() < end for start, end in well_spans):
            facts.depths.append(float(match.group().replace(",", "")))
    for match in [*UNIT_WORD.finditer(text), *UNIT_AFTER_NUMBER.finditer(text)]:
        facts.units.add(UNIT_WORDS[match.group(1).lower()])
    facts.targets = _words(TARGET_WORDS, text)
    facts.unsupported = _words(UNSUPPORTED_WORDS, text)
    facts.curves = _words(CURVE_WORDS, text)
    return facts


def _stated(value: float, depths: list[float]) -> bool:
    return any(abs(value - d) <= 1e-6 * max(1.0, abs(d)) for d in depths)


def check_interval(request: Interval, facts: RequestFacts, well_ranges: dict | None = None) -> None:
    """Raise a ToolError when an interval argument is not grounded in the request text."""
    if not facts.wells:
        raise ToolError("UNGROUNDED_WELL", "The request does not identify a well. Do not choose one; "
                        "finish with clarify and ask which well is meant.")
    if request.well not in facts.wells:
        raise ToolError("UNGROUNDED_WELL", f"Well {request.well} is not the well named in the request "
                        f"({sorted(facts.wells)}). Use the requested well.", recoverable=True)
    if not facts.units:
        raise ToolError("UNGROUNDED_UNIT", "The request does not state a depth unit (ft or m). Do not assume "
                        "one; finish with clarify and ask for the unit.")
    if request.unit not in facts.units:
        raise ToolError("UNGROUNDED_UNIT", f"The request states {sorted(facts.units)}, not {request.unit!r}. "
                        "Pass the depths in the stated unit; the tool converts them.", recoverable=True)
    for value in (request.start, request.end):
        if not _stated(value, facts.depths):
            raise ToolError("UNGROUNDED_DEPTH", f"Depth {value:g} {request.unit} is not a bound stated in the "
                            "request. Use the requested bounds exactly.", recoverable=True)
    named = {CURVE_WORDS[c.lower()] for c in request.curves if c.lower() in CURVE_WORDS}
    if request.curves and named != set(FEATURES) and not named <= facts.curves:
        raise ToolError("UNGROUNDED_CURVE", f"Curves {sorted(named - facts.curves)} were not named in the request. "
                        "Pass only the curves the user asked for, or omit curves to use all inputs.", recoverable=True)
    if well_ranges and request.well in well_ranges:
        low, high = well_ranges[request.well]
        factor = 1 / 0.3048 if request.unit == "m" else 1.0
        start, end = request.start * factor, request.end * factor
        if start < low - 1e-6 or end > high + 1e-6:
            raise ToolError("INTERVAL_OUT_OF_RANGE", f"Well {request.well} has data only from {low:.1f} to {high:.1f} "
                            f"ft; the request covers {start:.1f}-{end:.1f} ft. Do not shrink the interval silently; "
                            "finish with clarify or abstain.")


def check_prediction_request(facts: RequestFacts) -> None:
    """Block a prediction when the request asks only for quantities this system cannot produce."""
    if facts.unsupported and not facts.targets:
        raise ToolError("UNSUPPORTED_TARGET", f"The request asks for {sorted(facts.unsupported)}, which this "
                        "system cannot produce (only PHIF, SW and VSH). Finish with clarify.")


def check_answer(facts: RequestFacts) -> None:
    """Block an answer that would silently drop an unsupported part of the request."""
    if facts.unsupported:
        raise ToolError("UNSUPPORTED_TARGET", f"The request also asks for {sorted(facts.unsupported)}, which this "
                        "system cannot produce. Do not answer as if the request were complete; finish with "
                        "clarify and state which parts are supported.", recoverable=True)


def registry_context(frame: pd.DataFrame, features: list[str], aliases: dict, targets: list[str]) -> str:
    """Authoritative dataset facts and the grounding checklist, appended to the planner prompt."""
    ranges = frame.groupby("WELLNUM").DEPTH.agg(["min", "max"])
    wells = "; ".join(f"well {int(w)}: {r['min']:.1f}-{r['max']:.1f} ft" for w, r in ranges.iterrows())
    alias_text = ", ".join(f"{k}={v}" for k, v in aliases.items())
    return ("\nDATASET REGISTRY (authoritative): " + wells + ". Input curves: " + ", ".join(features) +
            ". Aliases: " + alias_text + ". Targets: " + ", ".join(targets) + " (fractions). Depth is stored in ft."
            "\nGROUNDING CHECKLIST: before inspect_interval, confirm the user's request itself states the well, "
            "the start depth, the end depth and the unit (ft or m). Use only values the user stated; never fill "
            "one in. If any is missing or ambiguous, finish with clarify and say what is missing. Pass curves only "
            "if the user named them. Only PHIF, SW and VSH can be predicted; if the request also asks for anything "
            "else (permeability, production, economics, retraining), finish with clarify naming what is unsupported.")
