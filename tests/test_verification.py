import pytest

from subsurface_agent.agent import run_agent
from subsurface_agent.config import get_config
from subsurface_agent.faults import BENIGN, FAULTS
from subsurface_agent.gaps.verification import REPAIR_LIMIT
from subsurface_agent.providers import ProviderReply
from subsurface_agent.tools import ToolRuntime

QUERY = "Predict PHIF, SW and VSH for well 3 from 10600 to 10619.5 ft and verify the result."
INTERVAL = {"well": 3, "start": 10600, "end": 10619.5, "unit": "ft"}
EXPECTED = {"missing_file": "MISSING_ARTIFACT", "corrupt_values": "RECOMPUTE_MISMATCH",
            "drop_rows": "ARTIFACT_IDENTITY", "duplicate_rows": "ARTIFACT_IDENTITY",
            "wrong_well": "ARTIFACT_IDENTITY", "nan_values": "NONFINITE_RESULT",
            "stale_artifact": "ARTIFACT_IDENTITY"}


def predicted(tiny_root, config, fault):
    runtime = ToolRuntime(tiny_root, tiny_root / f"run-{config}-{fault}", query=QUERY,
                          config=get_config(config), fault=fault)
    runtime.dispatch("inspect_dataset", {})
    interval = runtime.dispatch("inspect_interval", INTERVAL)
    prediction = runtime.dispatch("predict_properties", {"slice_id": interval["slice_id"]})
    return runtime, interval["slice_id"], prediction


@pytest.mark.parametrize("fault", FAULTS)
def test_every_fault_is_detected_and_repaired_or_correctly_accepted(tiny_root, fault):
    runtime, slice_id, prediction = predicted(tiny_root, "full", fault)
    assert "fault" not in str(prediction) and "simulation" not in str(prediction)
    first = runtime.dispatch("verify_predictions", {"prediction_id": prediction["prediction_id"]})
    if fault in BENIGN:
        assert first["ok"]
        return
    assert (first["error"], first["recoverable"]) == (EXPECTED[fault], True)
    assert runtime.dispatch("finish", {"status": "answer", "reason": "Done"})["error"] == "UNVERIFIED_RESULT"
    runtime.dispatch("predict_properties", {"slice_id": slice_id})
    assert runtime.dispatch("verify_predictions", {"prediction_id": prediction["prediction_id"]})["ok"]
    assert runtime.audit()["final_artifacts_valid"] is True


@pytest.mark.parametrize("fault", sorted(set(FAULTS) - BENIGN))
def test_without_g2_faulty_artifacts_are_accepted_and_the_oracle_records_it(tiny_root, fault):
    runtime, _, prediction = predicted(tiny_root, "no_g2", fault)
    assert runtime.dispatch("verify_predictions", {"prediction_id": prediction["prediction_id"]})["ok"]
    assert runtime.dispatch("finish", {"status": "answer", "reason": "Done"})["ok"]
    audit = runtime.audit()
    assert audit["fault_applied"] and audit["final_artifacts_valid"] is False


def test_repair_is_bounded(tiny_root):
    runtime, slice_id, _ = predicted(tiny_root, "full", None)
    for _ in range(REPAIR_LIMIT):
        assert runtime.dispatch("predict_properties", {"slice_id": slice_id})["ok"]
    blocked = runtime.dispatch("predict_properties", {"slice_id": slice_id})
    assert (blocked["error"], blocked["recoverable"]) == ("REPAIR_LIMIT", False)


class AcceptingProvider:
    """Test double that runs the normal sequence and answers whatever the verify step says."""
    model = "scripted-unit-test"
    request_count = 0

    def generate(self, system, contents, declarations):
        self.request_count += 1
        if len(contents) == 1:
            name, args = "inspect_dataset", {}
        else:
            last = contents[-1]["parts"][-1]["functionResponse"]
            tool, response = last["name"], last["response"]
            if tool == "inspect_dataset":
                name, args = "inspect_interval", INTERVAL
            elif tool == "inspect_interval":
                self.slice_id = response["slice_id"]
                name, args = "predict_properties", {"slice_id": self.slice_id}
            elif tool == "predict_properties":
                name, args = "verify_predictions", {"prediction_id": response["prediction_id"]}
            elif not response["ok"]:
                name, args = "predict_properties", {"slice_id": self.slice_id}
            else:
                name, args = "finish", {"status": "answer", "reason": "Verified"}
        return ProviderReply({"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {}, self.model)


def test_run_records_oracle_for_silent_error_scoring(tiny_root):
    full = run_agent(tiny_root, QUERY, AcceptingProvider(), run_name="g2-full", fault="corrupt_values")
    ablated = run_agent(tiny_root, QUERY, AcceptingProvider(), run_name="g2-off", fault="corrupt_values",
                        config=get_config("no_g2"))
    assert full["status"] == "answer" and full["oracle"]["final_artifacts_valid"] is True
    assert ablated["status"] == "answer" and ablated["oracle"]["final_artifacts_valid"] is False
    assert full["fault_injection"] == ablated["fault_injection"] == "corrupt_values"
