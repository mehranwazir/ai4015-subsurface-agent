"""Paths, finite JSON, checksums, and local configuration."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def project_root() -> Path:
    override = os.getenv("SUBSURFACE_ROOT")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean_json(v) for v in value]
    if hasattr(value, "item"):
        return clean_json(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean_json(value), indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_env(root: Path, env_file: Path | None = None) -> None:
    """Load only known settings, without logging or shell interpretation.

    The default `.env` never overrides variables already set; an explicitly chosen file does, so each
    experiment process can use its own credentials file.
    """
    allowed = {"GEMINI_API_KEY", "GEMINI_MODEL", "INPUT_USD_PER_MILLION", "OUTPUT_USD_PER_MILLION"}
    explicit = env_file is not None
    env_file = (root / env_file) if explicit and not Path(env_file).is_absolute() else (env_file or root / ".env")
    if not env_file.exists():
        if explicit:
            raise ValueError(f"Environment file {env_file.name} not found")
        return
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key in allowed:
            if explicit:
                os.environ[key] = value.strip().strip("\"'")
            else:
                os.environ.setdefault(key, value.strip().strip("\"'"))
