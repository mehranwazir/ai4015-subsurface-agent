"""Gemini REST native function calling; credentials never enter trace payloads."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .common import load_env


class ProviderError(RuntimeError):
    pass


@dataclass
class ProviderReply:
    content: dict
    usage: dict
    model_version: str


class GeminiProvider:
    """Decoding settings are explicit and recorded with every run.

    `min_interval` paces requests (seconds between request starts) and `rate_limit_waits` allows that many
    one-minute waits on HTTP 429 before giving up; both default to the Phase 1 behaviour (no pacing, one quick
    retry) and are raised by the experiment runner for free-tier quotas.
    """

    def __init__(self, root: Path, model: str | None = None, *, temperature: float = 1.0, seed: int | None = None,
                 min_interval: float = 0.0, rate_limit_waits: int = 0, rate_limit_wait_seconds: float = 60.0,
                 env_file: Path | None = None):
        load_env(root, env_file)
        # Which credentials file served a run is recorded (never the key itself).
        self.credentials = Path(env_file).name if env_file else ".env"
        self.key = os.getenv("GEMINI_API_KEY", "")
        if not self.key:
            raise ProviderError("Set GEMINI_API_KEY in environment or ignored .env")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        if not self.model.replace("-", "").replace(".", "").isalnum():
            raise ProviderError("Invalid model identifier")
        self.temperature, self.seed = temperature, seed
        self.min_interval, self.rate_limit_waits = min_interval, rate_limit_waits
        self.rate_limit_wait_seconds = rate_limit_wait_seconds
        self.request_count, self.rate_limit_events, self._last_request = 0, 0, 0.0
        # Seconds spent waiting for pacing or rate limits; excluded from a run's active latency.
        self.throttle_seconds = 0.0

    @property
    def generation_settings(self) -> dict:
        return {"temperature": self.temperature, "seed": self.seed, "max_output_tokens": 1024,
                "function_calling_mode": "ANY", "credentials_file": self.credentials}

    def _pace(self) -> None:
        wait = self._last_request + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
            self.throttle_seconds += wait
        self._last_request = time.monotonic()

    def generate(self, system: str, contents: list[dict], declarations: list[dict]) -> ProviderReply:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        generation = {"maxOutputTokens": 1024, "temperature": self.temperature}
        if self.seed is not None:
            generation["seed"] = self.seed
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "tools": [{"functionDeclarations": declarations}],
                "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
                "generationConfig": generation}
        quick_retry, waits = True, self.rate_limit_waits
        while True:
            self._pace()
            self.request_count += 1
            try:
                response = requests.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=(15, 75))
            except requests.RequestException as exc:
                raise ProviderError(f"Gemini connection failed ({type(exc).__name__}); no response saved") from None
            if response.status_code == 429 and waits > 0:
                waits -= 1
                self.rate_limit_events += 1
                time.sleep(self.rate_limit_wait_seconds)
                self.throttle_seconds += self.rate_limit_wait_seconds
                continue
            if response.status_code in {429, 500, 502, 503} and quick_retry:
                quick_retry = False
                time.sleep(2)
                continue
            if response.status_code != 200:
                # Do not log the request, headers, key, or arbitrary provider body.
                try:
                    status = response.json().get("error", {}).get("status", "UNKNOWN")
                except ValueError:
                    status = "NON_JSON_ERROR"
                raise ProviderError(f"Gemini HTTP {response.status_code}: {status}")
            try:
                data = response.json()
                content = data["candidates"][0]["content"]
            except (ValueError, KeyError, IndexError):
                raise ProviderError("Gemini returned no usable candidate") from None
            return ProviderReply(content, data.get("usageMetadata", {}), data.get("modelVersion", self.model))
