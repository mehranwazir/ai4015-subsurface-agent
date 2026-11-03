"""Named system configurations; each research-gap component is an explicit switch for ablation."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SystemConfig:
    name: str
    # G1: registry context in the prompt plus a deterministic check that interval arguments
    # (well, depths, unit) are stated in the user's own request rather than assumed.
    grounding: bool = True

    def flags(self) -> dict:
        return asdict(self)


PRESETS = {
    "full": SystemConfig("full"),
    "no_g1": SystemConfig("no_g1", grounding=False),
    # Behaviour of the recorded Phase 1 runs; used to replay traces that predate configurations.
    "phase1": SystemConfig("phase1", grounding=False),
}


def get_config(name: str) -> SystemConfig:
    if name not in PRESETS:
        raise ValueError(f"Unknown configuration {name!r}; choose from {sorted(PRESETS)}")
    return PRESETS[name]
