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


def grounded_runtime(tiny_root, query, name="full"):
    runtime = ToolRuntime(tiny_root, tiny_root / f"run-{name}", query=query, config=get_config(name))
    runtime.dispatch("inspect_dataset", {})
    return runtime


def test_unsupported_quantities_cannot_be_answered_silently(tiny_root):
    only = grounded_runtime(tiny_root, "Predict permeability for well 3 from 10600 to 10619.5 ft")
    interval = only.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"})
    blocked = only.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    assert (blocked["error"], blocked["recoverable"]) == ("UNSUPPORTED_TARGET", False)
    assert only.dispatch("finish", {"status": "clarify", "reason": "Permeability is unsupported"})["ok"]

    mixed = grounded_runtime(tiny_root, "Predict porosity and permeability for well 3 from 10600 to 10619.5 ft")
    interval = mixed.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"})
    predicted = mixed.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    mixed.dispatch("verify_predictions", {"prediction_id": predicted["prediction_id"]})
    answer = mixed.dispatch("finish", {"status": "answer", "reason": "Done"})
    assert (answer["error"], answer["recoverable"]) == ("UNSUPPORTED_TARGET", True)

    ablated = grounded_runtime(tiny_root, "Predict permeability for well 3 from 10600 to 10619.5 ft", "no_g1")
    interval = ablated.dispatch("inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"})
    assert ablated.dispatch("predict_properties", {"slice_id": interval["slice_id"]})["ok"]


def test_curves_must_be_named_and_intervals_must_lie_inside_the_well(tiny_root):
    query = "Inspect gamma ray and RHOB for well 3 from 10600 to 10619.5 ft"
    runtime = grounded_runtime(tiny_root, query)
    base = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
    assert runtime.dispatch("inspect_interval", {**base, "curves": ["gamma ray", "RHOB"]})["ok"]
    assert runtime.dispatch("inspect_interval", base)["ok"]
    assert runtime.dispatch("inspect_interval", {**base, "curves": ["NEU"]})["error"] == "UNGROUNDED_CURVE"
    beyond = grounded_runtime(tiny_root, "Inspect well 3 from 10600 to 10700 ft")
    result = beyond.dispatch("inspect_interval", {**base, "end": 10700})
    assert (result["error"], result["recoverable"]) == ("INTERVAL_OUT_OF_RANGE", False)
    assert grounded_runtime(tiny_root, "Inspect well 3 from 10600 to 10700 ft", "no_g1").dispatch(
        "inspect_interval", {**base, "end": 10700})["ok"]


def test_clarify_needs_no_inspection_but_an_answer_does(tiny_root):
    runtime = ToolRuntime(tiny_root, tiny_root / "run-direct", query="Predict permeability for well 3",
                          config=get_config("full"))
    assert runtime.dispatch("finish", {"status": "clarify", "reason": "Permeability is unsupported"})["ok"]
    fresh = ToolRuntime(tiny_root, tiny_root / "run-direct-2", query="List wells", config=get_config("full"))
    assert fresh.dispatch("finish", {"status": "answer", "reason": "Done"})["error"] == "NO_EVIDENCE"
