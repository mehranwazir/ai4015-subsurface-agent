from subsurface_agent.agent import replay_trace
from subsurface_agent.baselines.fixed_pipeline import parse_request, run_fixed_pipeline
from subsurface_agent.baselines.logacf_style import run_logacf_style
from subsurface_agent.providers import ProviderReply

QUERY = "Predict PHIF, SW and VSH for well 3 from 10600 to 10619.5 ft and verify the result."
INTERVAL = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}


def test_b0_parses_requests_with_a_script_default_for_units():
    assert parse_request(QUERY) == INTERVAL
    assert parse_request("Porosity for well 3 between 11000 and 10600")["unit"] == "ft"
    assert parse_request("Porosity for well 3 between 3230.88 and 3352.8 m")["unit"] == "m"
    assert parse_request("Porosity for my best well from 10600 to 11000 ft") is None


def test_b0_answers_fixed_requests_but_cannot_clarify_verify_or_repair(tiny_root):
    clean = run_fixed_pipeline(tiny_root, QUERY, run_name="b0-clean")
    assert clean["status"] == "answer" and clean["config"] == "b0" and clean["provider_requests"] is None
    assert [e["name"] for e in clean["trace"]] == ["inspect_dataset", "inspect_interval", "predict_properties", "finish"]
    no_unit = run_fixed_pipeline(tiny_root, "Predict porosity for well 3 between 10600 and 10619.5",
                                 run_name="b0-nounit")
    assert no_unit["status"] == "answer" and no_unit["trace"][1]["arguments"]["unit"] == "ft"
    faulty = run_fixed_pipeline(tiny_root, QUERY, run_name="b0-fault", fault="corrupt_values")
    assert faulty["status"] == "answer" and faulty["oracle"]["final_artifacts_valid"] is False
    vague = run_fixed_pipeline(tiny_root, "Predict porosity for my best well", run_name="b0-vague")
    assert vague["status"] == "abstain"
    assert replay_trace(tiny_root, tiny_root / "logs/runs/b0-clean/result.json")["all_match"]


class RoleProvider:
    """Test double for the B2 roles: a fixed plan, then a scripted sequence of review decisions."""
    model = "scripted-unit-test"

    def __init__(self, plan: dict, reviews: list[str]):
        self.plan, self.reviews, self.request_count = plan, list(reviews), 0

    def generate(self, system, contents, declarations):
        self.request_count += 1
        name = declarations[0]["name"]
        args = self.plan if name == "submit_plan" else {"decision": self.reviews.pop(0), "reason": "Reviewed"}
        return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)


PLAN = {"decision": "execute", "reason": "Predict", "interval": INTERVAL,
        "steps": ["inspect_dataset", "inspect_interval", "predict_properties", "verify_predictions"]}


def test_b2_runs_planner_executor_and_reviewer(tiny_root):
    result = run_logacf_style(tiny_root, QUERY, RoleProvider(PLAN, ["approve"]), run_name="b2-ok")
    roles = [e.get("role") or e["name"] for e in result["trace"]]
    assert roles == ["planner", "inspect_dataset", "inspect_interval", "predict_properties",
                     "verify_predictions", "reviewer", "finish"]
    assert result["status"] == "answer" and result["provider_requests"] == 2
    assert replay_trace(tiny_root, tiny_root / "logs/runs/b2-ok/result.json")["all_match"]


def test_b2_reviewer_redo_can_repair_but_unnoticed_faults_pass(tiny_root):
    repaired = run_logacf_style(tiny_root, QUERY, RoleProvider(PLAN, ["redo", "approve"]), run_name="b2-redo",
                                fault="drop_rows")
    assert repaired["status"] == "answer" and repaired["oracle"]["final_artifacts_valid"] is True
    missed = run_logacf_style(tiny_root, QUERY, RoleProvider(PLAN, ["approve"]), run_name="b2-missed",
                              fault="corrupt_values")
    assert missed["status"] == "answer" and missed["oracle"]["final_artifacts_valid"] is False


def test_b2_planner_can_decline_without_tools(tiny_root):
    plan = {"decision": "clarify", "steps": [], "reason": "Which unit?"}
    result = run_logacf_style(tiny_root, "Predict porosity for well 3 between 10600 and 10619.5",
                              RoleProvider(plan, []), run_name="b2-clarify")
    assert result["status"] == "clarify" and result["tool_calls"] == 1
