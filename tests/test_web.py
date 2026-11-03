"""The web interface reads saved evidence only and rejects bad input; no network or API key needed."""
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from subsurface_agent.web import Store, make_server

ROOT = Path(__file__).resolve().parents[1]


def test_store_lists_every_final_run_with_its_request():
    runs = Store(ROOT).runs()
    assert len(runs) == 566
    first = runs[0]
    assert first["query"] and first["system_label"] and isinstance(first["task_correct"], bool)


def test_detail_returns_trace_score_and_prediction_series():
    detail = Store(ROOT).detail("final-full-test-fault-droprows-1-r1")
    assert detail["result"]["status"] == "answer"
    assert detail["score"]["repaired"] is True
    assert [e["name"] for e in detail["result"]["trace"]].count("verify_predictions") == 2
    series = detail["series"][0]
    assert len(series["depth"]) == len(series["pred"]["PHIF"]) > 0
    assert series["depth"] == sorted(series["depth"])


@pytest.mark.parametrize("run_id", ["../secrets", "final-full-test-predict-01-r1/../../x", "", "nope"])
def test_detail_refuses_unknown_or_unsafe_ids(run_id):
    assert Store(ROOT).detail(run_id) is None


def test_start_rejects_bad_requests_before_running_anything():
    store = Store(ROOT)
    with pytest.raises(ValueError):
        store.start("", "full")
    with pytest.raises(ValueError):
        store.start("Predict PHIF for well 3 from 10900 to 11000 ft.", "gpt")
    with pytest.raises(ValueError):
        store.start("x" * 401, "full")
    assert not store.jobs


@pytest.fixture()
def server():
    srv = make_server(ROOT, port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as res:
        return res.status, res.headers.get("Content-Type"), res.read()


def test_http_serves_page_api_and_figures(server):
    status, kind, body = _get(server + "/")
    assert status == 200 and kind.startswith("text/html") and b"Subsurface Agent" in body
    status, _, body = _get(server + "/api/tables")
    tables = json.loads(body)
    assert "gap_resolution" in tables["tables"] and "fig_gapwise.png" in tables["figures"]
    status, kind, _ = _get(server + "/figures/fig_gapwise.png")
    assert status == 200 and kind == "image/png"


@pytest.mark.parametrize("path", ["/static/../../.env", "/figures/..%2F..%2F.env", "/api/runs/..%2Fx", "/api/nothing"])
def test_http_does_not_serve_outside_its_folders(server, path):
    with pytest.raises(urllib.error.HTTPError) as err:
        _get(server + path)
    assert err.value.code == 404


def test_http_rejects_an_empty_run_request(server):
    req = urllib.request.Request(server + "/api/jobs", data=json.dumps({"query": "", "system": "full"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(req, timeout=10)
    assert err.value.code == 400
