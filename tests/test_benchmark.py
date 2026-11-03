import json
import re
from pathlib import Path

import pytest

from subsurface_agent.faults import FAULTS

BENCHMARK = Path(__file__).resolve().parents[1] / "experiments" / "benchmark"
HINTS = re.compile(r"\b(clarif|abstain|refuse|ask me|if unsupported|if the file|verify the file)", re.I)


@pytest.mark.parametrize("split, wells", [("dev", {1, 5}), ("test", {3, 7})])
def test_benchmark_is_well_formed_split_safe_and_hint_free(split, wells):
    cases = json.loads((BENCHMARK / f"{split}.json").read_text(encoding="utf-8"))
    assert len({c["id"] for c in cases}) == len(cases)
    for case in cases:
        expected = case["expected"]
        assert set(expected["statuses"]) <= {"answer", "clarify", "abstain"}
        assert case["fault"] in (None, *FAULTS)
        assert not HINTS.search(case["query"]), case["query"]
        if "well" in expected:
            assert expected["well"] in wells and expected["bounds_ft"][0] < expected["bounds_ft"][1]
    assert {c["fault"] for c in cases if c["fault"]} == set(FAULTS)


def test_test_benchmark_covers_every_gap():
    cases = json.loads((BENCHMARK / "test.json").read_text(encoding="utf-8"))
    for gap in ("G1", "G2", "G3"):
        assert sum(gap in c["gaps"] for c in cases) >= 10
