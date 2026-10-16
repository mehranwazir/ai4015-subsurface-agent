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
    def __init__(self, root: Path, model: str | None = None):
        load_env(root)
        self.key = os.getenv("GEMINI_API_KEY", "")
        if not self.key:
            raise ProviderError("Set GEMINI_API_KEY in environment or ignored .env")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        if not self.model.replace("-", "").replace(".", "").isalnum():
            raise ProviderError("Invalid model identifier")
        self.request_count = 0

    def generate(self, system: str, contents: list[dict], declarations: list[dict]) -> ProviderReply:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                "tools": [{"functionDeclarations": declarations}],
                "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
                "generationConfig": {"maxOutputTokens": 1024}}
        for attempt in range(2):
            self.request_count += 1
            try:
                response = requests.post(url, json=body, headers={"x-goog-api-key": self.key}, timeout=(15, 75))
            except requests.RequestException as exc:
                raise ProviderError(f"Gemini connection failed ({type(exc).__name__}); no response saved") from None
            if response.status_code in {429, 500, 502, 503} and attempt == 0:
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
        raise ProviderError("Gemini retry budget exhausted")
