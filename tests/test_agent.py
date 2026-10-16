from subsurface_agent.agent import replay_trace, run_agent
from subsurface_agent.evaluation import score_case
from subsurface_agent.providers import ProviderError, ProviderReply


class ScriptedProvider:
    """A software test double, never a claimed real LLM experiment."""
    model = "scripted-unit-test"
    request_count = 0

    def generate(self, system, contents, declarations):
        step = self.request_count
        self.request_count += 1
        successful = [part["functionResponse"]["response"] for message in contents for part in message["parts"]
                      if "functionResponse" in part and part["functionResponse"]["response"].get("ok")]
        if step == 0:
            name, args = "inspect_dataset", {}
        elif step == 1:
            name, args = "inspect_interval", {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
        elif step == 2:
            name, args = "predict_properties", {"slice_id": successful[-1]["slice_id"]}
        elif step == 3:
            name, args = "verify_predictions", {"prediction_id": successful[-1]["prediction_id"]}
        else:
            name, args = "finish", {"status": "answer", "reason": "Verified tool result"}
        return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)


def test_full_tool_loop_and_replay(tiny_root):
    result = run_agent(tiny_root, "unit test", ScriptedProvider(), run_name="software-test")
    assert result["status"] == "answer"
    assert result["provider"] == "ScriptedProvider"
    replay = replay_trace(tiny_root, tiny_root / "results/runs/software-test/result.json", replay_name="software-replay")
    assert replay["all_match"]
    assert replay["llm_called"] is False


def test_provider_failure_preserves_honest_failed_run(tiny_root):
    class FailingProvider:
        def generate(self, *args):
            raise ProviderError("Gemini HTTP 429: RESOURCE_EXHAUSTED")
    result = run_agent(tiny_root, "test", FailingProvider(), run_name="failed-test")
    assert result["status"] == "failed"
    assert result["tool_calls"] == 0
    assert result["trace"][0]["event"] == "provider_error"


def test_budget_stops_run_and_preserves_trace(tiny_root):
    result = run_agent(tiny_root, "test", ScriptedProvider(), run_name="budget-test", max_calls=2)
    assert result["status"] == "failed"
    assert result["tool_calls"] == 2


def test_evaluation_does_not_trust_answer_status_alone():
    case = {"id": "x", "expected": {"statuses": ["answer"], "well": 3, "tools": ["predict_properties"]}}
    result = {"status": "answer", "run_id": "x", "latency_seconds": 0, "usage": {}, "tool_calls": 0,
              "reason": "claimed success", "trace": []}
    assert not score_case(case, result)["passed"]


def test_reusing_provider_counts_requests_per_run(tiny_root):
    class ReusableProvider:
        model = "scripted-unit-test"
        request_count = 0

        def generate(self, system, contents, declarations):
            self.request_count += 1
            name = "inspect_dataset" if len(contents) == 1 else "finish"
            args = {} if name == "inspect_dataset" else {"status": "answer", "reason": "Listed schema"}
            return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)

    provider = ReusableProvider()
    first = run_agent(tiny_root, "List schema", provider, run_name="count-first")
    second = run_agent(tiny_root, "List schema", provider, run_name="count-second")
    assert first["status"] == second["status"] == "answer"
    assert first["provider_requests"] == second["provider_requests"] == 2
    assert provider.request_count == 4
