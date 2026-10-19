"""Load and validate step-by-step pooja scripts that follow a YouTube video."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

POOJA_DIR = Path(__file__).with_name("poojas")
ACTIONS = {"listen", "do"}


class PoojaError(ValueError):
    """A pooja script is malformed."""


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    title_en: str
    say: str
    say_en: str
    segment: tuple[float, float] | None
    action: str
    check: str | None
    live_check: bool = False


@dataclass(frozen=True)
class Pooja:
    id: str
    title: str
    title_en: str
    status: str
    youtube_id: str
    duration: float
    notes_for_agent: tuple[str, ...]
    items: tuple[dict[str, str], ...]
    steps: tuple[Step, ...]
    raw: dict[str, Any]

    def step(self, step_id: str) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)


def parse_pooja(data: dict[str, Any]) -> Pooja:
    try:
        video = data["video"]
        duration = float(video["duration"])
        steps = []
        seen: set[str] = set()
        for raw in data["steps"]:
            step_id = raw["id"]
            if step_id in seen:
                raise PoojaError(f"Duplicate step id: {step_id}")
            seen.add(step_id)
            if raw["action"] not in ACTIONS:
                raise PoojaError(f"Step {step_id}: action must be one of {sorted(ACTIONS)}")
            segment = raw.get("segment")
            if segment is not None:
                start, end = float(segment[0]), float(segment[1])
                if not 0 <= start < end <= duration:
                    raise PoojaError(f"Step {step_id}: segment {segment} outside video 0-{duration}s")
                segment = (start, end)
            if raw["action"] == "do" and not raw.get("check"):
                raise PoojaError(f"Step {step_id}: 'do' steps need a visual check")
            steps.append(Step(
                id=step_id, title=raw["title"], title_en=raw["title_en"],
                say=raw["say"], say_en=raw["say_en"], segment=segment,
                action=raw["action"], check=raw.get("check"),
                live_check=bool(raw.get("live_check", False)),
            ))
        if not steps:
            raise PoojaError("A pooja needs at least one step")
        return Pooja(
            id=data["id"], title=data["title"], title_en=data["title_en"],
            status=data.get("status", "unreviewed_draft"),
            youtube_id=video["youtube_id"], duration=duration,
            notes_for_agent=tuple(data.get("notes_for_agent", [])),
            items=tuple(data.get("items", [])), steps=tuple(steps), raw=data,
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise PoojaError(f"Malformed pooja script: missing or invalid {exc}") from exc


def load_pooja_file(path: str | Path) -> Pooja:
    return parse_pooja(json.loads(Path(path).read_text(encoding="utf-8")))


@lru_cache(maxsize=None)
def bundled_poojas() -> dict[str, Pooja]:
    poojas = {}
    for path in sorted(POOJA_DIR.glob("*.json")):
        pooja = load_pooja_file(path)
        poojas[pooja.id] = pooja
    return poojas
