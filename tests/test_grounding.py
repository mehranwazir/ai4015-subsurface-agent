import pytest

from subsurface_agent.agent import run_agent
from subsurface_agent.config import PRESETS, get_config
from subsurface_agent.contracts import Interval
from subsurface_agent.errors import ToolError
from subsurface_agent.gaps.grounding import check_interval, extract_request_facts
from subsurface_agent.providers import ProviderReply
from subsurface_agent.tools import ToolRuntime

NO_UNIT = "Predict porosity for well 3 between 10600 and 10619.5."


def test_request_facts_are_extracted_from_text():
    facts = extract_request_facts("Predict porosity for well 3 from 10,600 to 11,000 ft.")
    assert facts.wells == {3} and facts.depths == [10600, 11000] and facts.units == {"ft"}
    metres = extract_request_facts("Well #7 between 3230.88m and 3352.8 metres")
    assert metres.wells == {7} and metres.units == {"m"} and metres.depths == [3230.88, 3352.8]
    vague = extract_request_facts("Predict porosity for my best well between depths 10600 and 11000")
    assert vague.wells == set() and vague.units == set()


@pytest.mark.parametrize("query, arguments, code, recoverable", [
    (NO_UNIT, {"unit": "ft"}, "UNGROUNDED_UNIT", False),
    ("Predict PHIF for my best well from 10600 to 10619.5 ft", {}, "UNGROUNDED_WELL", False),
    ("Predict PHIF for well 5 from 10600 to 10619.5 ft", {}, "UNGROUNDED_WELL", True),
    ("Predict PHIF for well 3 from 3230.88 to 3236.82 m", {}, "UNGROUNDED_UNIT", True),
    ("Predict PHIF for well 3 from 10600 to 10650 ft", {}, "UNGROUNDED_DEPTH", True),
])
def test_ungrounded_interval_arguments_are_rejected(query, arguments, code, recoverable):
    request = Interval(**{"well": 3, "start": 10600, "end": 10619.5, "unit": "ft", **arguments})
    with pytest.raises(ToolError) as caught:
        check_interval(request, extract_request_facts(query))
    assert (caught.value.code, caught.value.recoverable) == (code, recoverable)


def test_grounded_interval_passes_in_either_stated_unit():
    check_interval(Interval(well=3, start=10600, end=10619.5, unit="ft"),
                   extract_request_facts("Predict PHIF for well 3 from 10,600 to 10,619.5 feet"))
    check_interval(Interval(well=3, start=3230.88, end=3236.82, unit="m"),
                   extract_request_facts("PHIF for well 3 between 3230.88 and 3236.82 meters"))


def test_switch_controls_check_and_prompt_context(tiny_root):
    arguments = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
    for name, blocked in [("full", True), ("no_g1", False)]:
        runtime = ToolRuntime(tiny_root, tiny_root / name, query=NO_UNIT, config=get_config(name))
        runtime.dispatch("inspect_dataset", {})
        result = runtime.dispatch("inspect_interval", arguments)
        assert (result.get("error") == "UNGROUNDED_UNIT") is blocked
        assert ("GROUNDING CHECKLIST" in runtime.prompt_context()) is blocked
    with pytest.raises(ValueError, match="Unknown configuration"):
        get_config("missing")


class GuessingProvider:
    """Test double reproducing the observed live behaviour: it fills in unit='ft' unprompted."""
    model = "scripted-unit-test"
    request_count = 0

    def generate(self, system, contents, declarations):
        self.request_count += 1
        last = [p["functionResponse"]["response"] for p in contents[-1]["parts"] if "functionResponse" in p]
        if len(contents) == 1:
            name, args = "inspect_dataset", {}
        elif len(contents) == 3:
            name, args = "inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
        elif last and not last[-1]["ok"]:
            name, args = "finish", {"status": "clarify", "reason": "Which depth unit?"}
        else:
            name, args = "finish", {"status": "answer", "reason": "Inspected"}
        return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)


def test_full_system_turns_a_guessed_unit_into_clarification(tiny_root):
    full = run_agent(tiny_root, NO_UNIT, GuessingProvider(), run_name="g1-full", config=PRESETS["full"])
    ablated = run_agent(tiny_root, NO_UNIT, GuessingProvider(), run_name="g1-off", config=PRESETS["no_g1"])
    assert full["status"] == "clarify" and full["config"] == "full"
    assert any(e["result"].get("error") == "UNGROUNDED_UNIT" for e in full["trace"])
    assert ablated["status"] == "answer" and ablated["config_flags"]["grounding"] is False
