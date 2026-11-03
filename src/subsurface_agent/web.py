"""Local web interface: browse the saved final runs and start new runs from a browser.

Standard library only (http.server), so it adds no dependency. The page itself lives in `web/` at the
repository root. Saved runs are read from `logs/evidence/final` and need no API key. A live run calls the same
`run_system` the experiment runner uses, writes its evidence to `logs/runs/`, and needs GEMINI_API_KEY for every
system except B0. Nothing here changes how a run is executed or scored.
"""
from __future__ import annotations

import csv
import json
import mimetypes
import os
import re
import threading
import time
import uuid
import webbrowser
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pandas as pd

from .common import clean_json, read_json
from .experiments import SYSTEMS, run_system
from .providers import GeminiProvider, ProviderError

RUN_ID = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
MAX_QUERY = 400
MAX_POINTS = 400
LABELS = {"b0": "B0 fixed pipeline", "b2": "B2 LogACF-style", "full": "Proposed (full)",
          "no_g1": "Without G1", "no_g2": "Without G2", "no_g3": "Without G3"}


def _number(value: str):
    if value in ("", None):
        return None
    if value in ("True", "False"):
        return value == "True"
    try:
        return float(value) if any(c in value for c in ".eE") else int(value)
    except ValueError:
        return value


class Store:
    """Read-only access to the saved results, plus the live-run jobs started from the page."""

    def __init__(self, root: Path):
        self.root = root
        self.final_dir = root / "logs" / "evidence" / "final"
        self.live_dir = root / "logs" / "runs"
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.busy = threading.Lock()

    # ── saved runs ──────────────────────────────────────────────────────────
    @lru_cache(maxsize=1)
    def cases(self) -> dict:
        return {c["id"]: c for c in read_json(self.root / "experiments" / "benchmark" / "test.json")}

    @lru_cache(maxsize=1)
    def runs(self) -> list[dict]:
        cases = self.cases()
        rows = []
        with (self.root / "results" / "experiments" / "final" / "runs.csv").open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                item = {k: _number(v) for k, v in row.items()}
                item["query"] = cases.get(row["case_id"], {}).get("query", "")
                item["system_label"] = LABELS.get(row["system"], row["system"])
                rows.append(item)
        return rows

    def run_dir(self, run_id: str) -> Path | None:
        if not RUN_ID.match(run_id):
            return None
        for base in (self.final_dir, self.live_dir):
            path = base / run_id
            if (path / "result.json").is_file():
                return path
        return None

    @lru_cache(maxsize=1)
    def truth(self) -> pd.DataFrame | None:
        frames = []
        for split in ("train", "validation", "test"):
            path = self.root / "data" / "processed" / f"{split}.csv"
            if path.is_file():
                frames.append(pd.read_csv(path, usecols=["sample_id", "PHIF", "SW", "VSH"]))
        return pd.concat(frames).set_index("sample_id") if frames else None

    def series(self, run_dir: Path, result: dict) -> list[dict]:
        """Predicted logs of each verified (or else the last) prediction file, joined with reference labels."""
        files = [run_dir / f"{p}.csv" for p in result.get("verified_predictions") or []]
        if not any(f.is_file() for f in files):
            files = sorted(run_dir.glob("pred-*.csv"), key=lambda p: p.stat().st_mtime)[-1:]
        out = []
        truth = self.truth()
        for path in files:
            if not path.is_file():
                continue
            frame = pd.read_csv(path)
            if not {"DEPTH", "PHIF_pred", "SW_pred", "VSH_pred"} <= set(frame.columns):
                continue
            frame = frame.sort_values("DEPTH")
            step = max(1, len(frame) // MAX_POINTS)
            frame = frame.iloc[::step]
            item = {"artifact": path.stem, "well": int(frame["WELLNUM"].iloc[0]) if len(frame) else None,
                    "depth": frame["DEPTH"].round(2).tolist(),
                    "pred": {t: frame[f"{t}_pred"].round(4).tolist() for t in ("PHIF", "SW", "VSH")}}
            if truth is not None and "sample_id" in frame:
                joined = truth.reindex(frame["sample_id"])
                item["truth"] = {t: [None if pd.isna(v) else round(float(v), 4) for v in joined[t]]
                                 for t in ("PHIF", "SW", "VSH")}
            out.append(item)
        return out

    def detail(self, run_id: str) -> dict | None:
        run_dir = self.run_dir(run_id)
        if run_dir is None:
            return None
        result = read_json(run_dir / "result.json")
        score = next((r for r in self.runs() if r["run_id"] == run_id), None)
        plots = sorted(p.name for p in run_dir.glob("pred-*.png"))
        return clean_json({"result": result, "score": score, "series": self.series(run_dir, result),
                           "plots": plots, "source": "final" if run_dir.parent == self.final_dir else "live"})

    # ── results tables ──────────────────────────────────────────────────────
    @lru_cache(maxsize=1)
    def tables(self) -> dict:
        out = {}
        for path in sorted((self.root / "results" / "final" / "tables").glob("*.csv")):
            with path.open(encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            out[path.stem] = {"columns": rows[0], "rows": rows[1:]} if rows else {"columns": [], "rows": []}
        return out

    def figures(self) -> list[str]:
        return sorted(p.name for p in (self.root / "results" / "final" / "figures").glob("*.png"))

    def status(self) -> dict:
        from .common import load_env
        load_env(self.root, None)
        processed = self.root / "data" / "processed" / "features.csv"
        return {"api_key": bool(os.getenv("GEMINI_API_KEY")), "data_ready": processed.is_file(),
                "model": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                "saved_runs": len(self.runs()), "systems": [{"id": s, "label": LABELS[s]} for s in SYSTEMS],
                "busy": self.busy.locked()}

    # ── live runs ───────────────────────────────────────────────────────────
    def live_runs(self) -> list[dict]:
        out = []
        for path in sorted(self.live_dir.glob("web-*/result.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
            r = read_json(path)
            out.append({"run_id": r["run_id"], "query": r["query"], "config": r["config"], "status": r["status"],
                        "created_utc": r["created_utc"], "tool_calls": r["tool_calls"]})
        return out

    def start(self, query: str, system: str) -> dict:
        query = " ".join(str(query).split())
        if not query or len(query) > MAX_QUERY:
            raise ValueError(f"Write a request of 1 to {MAX_QUERY} characters")
        if system not in SYSTEMS:
            raise ValueError("Unknown system")
        if not (self.root / "data" / "processed" / "features.csv").is_file():
            raise ValueError("Data not prepared: run `subsurface download` and `subsurface prepare` first")
        if not self.busy.acquire(blocking=False):
            raise ValueError("A run is already in progress; wait for it to finish")
        job_id = uuid.uuid4().hex[:10]
        job = {"id": job_id, "query": query, "system": system, "state": "running", "steps": [],
               "started": time.time(), "run_id": f"web-{system}-{job_id}", "error": None}
        with self.lock:
            self.jobs[job_id] = job
        threading.Thread(target=self._work, args=(job,), daemon=True).start()
        return job

    def _work(self, job: dict) -> None:
        try:
            provider = None
            if job["system"] != "b0":
                provider = LiveProvider(self.root, job["steps"])
            result = run_system(self.root, job["system"], {"query": job["query"], "fault": None}, provider,
                                job["run_id"])
            job["state"] = "done"
            job["status"] = result["status"]
        except (ProviderError, ValueError, OSError) as exc:
            job["state"], job["error"] = "error", str(exc)
        except Exception as exc:  # keep the server alive; report the failure on the page
            job["state"], job["error"] = "error", f"{type(exc).__name__}: {exc}"
        finally:
            job["elapsed"] = time.time() - job["started"]
            self.busy.release()

    def job(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
        if job is None:
            return None
        out = {k: v for k, v in job.items()}
        out["steps"] = list(job["steps"])
        out["elapsed"] = job.get("elapsed", time.time() - job["started"])
        return out


class LiveProvider(GeminiProvider):
    """Gemini provider that also reports each model request and tool result to the page while a run is going.

    The run record names this class as the provider, so a run started from the page is never mistaken for one
    of the experiment runs.
    """

    def __init__(self, root: Path, steps: list):
        # Same pacing as the experiment runner, so a run from the page fits the free-tier per-minute quota. No long
        # waits on HTTP 429: on the page that is usually a used-up daily quota, so the run stops and says so.
        super().__init__(root, min_interval=4.5, rate_limit_waits=0)
        self.steps = steps

    def generate(self, system, contents, declarations):
        last = contents[-1] if contents else {}
        for part in last.get("parts", []):
            if "functionResponse" in part:
                response = part["functionResponse"]
                result = response.get("response", {})
                self.steps.append({"kind": "result", "name": response.get("name"), "ok": bool(result.get("ok")),
                                   "error": result.get("error"), "message": result.get("message"),
                                   "t": time.time()})
        self.steps.append({"kind": "thinking", "t": time.time()})
        reply = super().generate(system, contents, declarations)
        for part in reply.content.get("parts", []):
            if "functionCall" in part:
                call = part["functionCall"]
                self.steps.append({"kind": "call", "name": call.get("name"), "args": call.get("args", {}),
                                   "t": time.time()})
        return reply


class Handler(BaseHTTPRequestHandler):
    store: Store
    static: Path

    def log_message(self, fmt, *args):  # quiet console; errors are still returned to the page
        pass

    def _send(self, status: int, body: bytes, content_type: str, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(clean_json(data), allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _file(self, path: Path, base: Path, cache: bool = False) -> None:
        try:
            path = path.resolve()
            path.relative_to(base.resolve())
        except (OSError, ValueError):
            return self._json({"error": "not found"}, 404)
        if not path.is_file():
            return self._json({"error": "not found"}, 404)
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if kind.startswith("text/") or kind in ("application/javascript",):
            kind += "; charset=utf-8"
        self._send(200, path.read_bytes(), kind, cache)

    def do_GET(self):
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        store = self.store
        if not parts or parts == ["index.html"]:
            return self._file(self.static / "index.html", self.static)
        if parts[0] == "static":
            return self._file(self.static.joinpath(*parts[1:]), self.static)
        if parts[0] == "figures" and len(parts) == 2:
            base = store.root / "results" / "final" / "figures"
            return self._file(base / parts[1], base, cache=True)
        if parts[0] == "artifact" and len(parts) == 3:
            run_dir = store.run_dir(parts[1])
            if run_dir is None or not re.fullmatch(r"pred-[0-9a-f]{16}\.png", parts[2]):
                return self._json({"error": "not found"}, 404)
            return self._file(run_dir / parts[2], run_dir, cache=True)
        if parts[0] != "api":
            return self._json({"error": "not found"}, 404)
        route = parts[1:]
        if route == ["status"]:
            return self._json(store.status())
        if route == ["runs"]:
            return self._json(store.runs())
        if len(route) == 2 and route[0] == "runs":
            detail = store.detail(route[1])
            return self._json(detail) if detail else self._json({"error": "run not found"}, 404)
        if route == ["tables"]:
            return self._json({"tables": store.tables(), "figures": store.figures()})
        if route == ["live"]:
            return self._json(store.live_runs())
        if len(route) == 2 and route[0] == "jobs":
            job = store.job(route[1])
            return self._json(job) if job else self._json({"error": "job not found"}, 404)
        if route == ["cases"]:
            return self._json(list(store.cases().values()))
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path.rstrip("/") != "/api/jobs":
            return self._json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 4096:
            return self._json({"error": "bad request"}, 400)
        try:
            body = json.loads(self.rfile.read(length))
            job = self.store.start(body.get("query", ""), body.get("system", "full"))
        except (ValueError, json.JSONDecodeError, AttributeError) as exc:
            return self._json({"error": str(exc)}, 409 if "in progress" in str(exc) else 400)
        return self._json(self.store.job(job["id"]), 202)


def make_server(root: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"store": Store(root), "static": root / "web"})
    return ThreadingHTTPServer((host, port), handler)


def serve(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = make_server(root, host, port)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"Subsurface agent web interface on {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
