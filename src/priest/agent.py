"""The priest agent: watches a camera frame, hears the user, and guides the current step."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .pooja import Pooja, Step

log = logging.getLogger(__name__)

Mode = Literal["check", "live", "ask"]
DEFAULT_MODEL = "claude-opus-5-5"

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean"},
        "say": {"type": "string"},
        "urgent": {"type": "boolean"},
    },
    "required": ["done", "say", "urgent"],
    "additionalProperties": False,
}

PERSONA = """You are "Ayyagaru" (అయ్యగారు), a warm, patient elderly Telugu priest on a live video call. \
You sit with a family and guide them through one pooja that follows a recorded YouTube video. \
The video's priest chants every mantra; you never chant, invent, transliterate or correct mantras, \
svara or sankalpa wording yourself. Your role is procedural: watch the camera, listen, and tell the \
user what to do with their hands and items, gently and briefly.

How you speak:
- Your words are read aloud by text-to-speech. Write 1-2 short spoken sentences (under 30 words), \
no lists, no emoji, no markdown, no stage directions.
- Reply in {language}. Address the user respectfully (in Telugu use మీరు / అండి).
- Encourage; never scold. Families vary in custom; accept reasonable variations and substitutes \
(akshata or a flower can replace a missing item).
- If the image is dark, blurry or the setup is out of view, ask them to adjust the phone.
- Safety overrides everything: flame near cloth, curtains, paper, hair or a child is urgent.
- Do not claim the pooja guarantees health, wealth or other outcomes.
- You are an AI guide, not an initiated priest; if asked about eligibility, muhurta, or family \
customs, suggest asking their family priest or elders.

Reply with JSON only: {{"done": bool, "say": string, "urgent": bool}}.
"""

MODE_INSTRUCTIONS = {
    "check": "The video segment for this step just finished. Look at the camera frame. Set done=true if "
             "the step's expectation is reasonably met (be lenient: they may already have finished the "
             "action), and say a very short affirmation. Otherwise done=false and say the one most useful "
             "correction. urgent=true only for a safety problem.",
    "live": "The video is still playing this step and the user is following along. Only speak if a "
            "correction is clearly needed or there is a safety issue; otherwise return say=\"\" and "
            "done=false. Keep any correction to one short sentence. urgent=true only for safety.",
    "ask": "The user just spoke to you (see 'User said'). Answer them helpfully for this moment of the "
           "pooja, using the frame if relevant. If what they said means the step is finished (e.g. "
           "'అయిపోయింది', 'done'), set done=true. urgent=true only for safety.",
}


@dataclass
class Reply:
    done: bool | None
    say: str
    urgent: bool = False
    available: bool = True

    def as_payload(self) -> dict[str, Any]:
        return {"done": self.done, "say": self.say, "urgent": self.urgent, "available": self.available}


def _pooja_context(pooja: Pooja) -> str:
    outline = "\n".join(
        f"{index + 1}. [{step.id}] {step.title_en} ({step.action})"
        for index, step in enumerate(pooja.steps)
    )
    items = ", ".join(item["en"] for item in pooja.items)
    notes = "\n".join(f"- {note}" for note in pooja.notes_for_agent)
    return (
        f"Pooja: {pooja.title_en} / {pooja.title}\n"
        f"Items the family was asked to keep ready: {items}\n"
        f"Guidance for you:\n{notes}\n"
        f"Full step outline:\n{outline}"
    )


def _step_context(pooja: Pooja, step: Step) -> str:
    index = pooja.steps.index(step)
    following = pooja.steps[index + 1].title_en if index + 1 < len(pooja.steps) else "(end of pooja)"
    return (
        f"Current step {index + 1}/{len(pooja.steps)}: [{step.id}] {step.title_en} / {step.title}\n"
        f"What you told the user to do: {step.say_en}\n"
        f"What you expect to see: {step.check or 'nothing specific; they are listening'}\n"
        f"Next step: {following}"
    )


def _has_credentials() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return bool(os.environ.get("ANTHROPIC_PROFILE")) or (config_home / "anthropic").is_dir()


class PriestAgent:
    """Wraps the Claude API. Without credentials it reports itself unavailable so the call
    still works hands-free with voice/tap confirmation instead of vision."""

    def __init__(self, model: str | None = None, client: Any | None = None):
        self.model = model or os.environ.get("PRIEST_MODEL", DEFAULT_MODEL)
        self._client = client
        if self._client is None and _has_credentials():
            try:
                import anthropic
                # User-level keys (not scoped to a workspace) must name the workspace per request.
                workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
                self._client = anthropic.Anthropic(
                    default_headers={"anthropic-workspace-id": workspace} if workspace else None)
            except ImportError as exc:
                log.warning("Priest agent vision disabled: %s", exc)
        if self._client is None:
            log.warning("Priest agent vision disabled: no Anthropic credentials. "
                        "Set ANTHROPIC_API_KEY to let Ayyagaru see the camera.")

    @property
    def available(self) -> bool:
        return self._client is not None

    def respond(self, pooja: Pooja, step: Step, mode: Mode, *, frame_jpeg_b64: str | None = None,
                heard: str = "", history: list[dict[str, str]] | None = None,
                language: str = "te") -> Reply:
        if not self.available:
            return Reply(done=None, say="", available=False)
        if mode == "live" and not frame_jpeg_b64:
            return Reply(done=False, say="")

        content: list[dict[str, Any]] = []
        if frame_jpeg_b64:
            content.append({"type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": frame_jpeg_b64}})
        recent = "\n".join(f"{turn.get('who', '?')}: {turn.get('text', '')}" for turn in (history or [])[-6:])
        content.append({"type": "text", "text": (
            f"{_step_context(pooja, step)}\n\n"
            f"Recent conversation:\n{recent or '(none)'}\n\n"
            f"User said: {heard or '(nothing)'}\n\n"
            f"Task: {MODE_INSTRUCTIONS[mode]}"
            + ("" if frame_jpeg_b64 else "\n(No camera frame is available right now.)")
        )})

        language_name = "Telugu (తెలుగు script)" if language == "te" else "simple English"
        import anthropic
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=2048,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
                system=[
                    {"type": "text", "text": PERSONA.format(language=language_name)},
                    {"type": "text", "text": _pooja_context(pooja), "cache_control": {"type": "ephemeral"}},
                ],
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AuthenticationError as exc:
            log.error("Claude API rejected the credentials; disabling vision: %s", exc.message)
            self._client = None
            return Reply(done=None, say="", available=False)
        except anthropic.APIStatusError as exc:
            log.error("Claude API error %s: %s", exc.status_code, exc.message)
            return Reply(done=None, say="", available=False)
        except anthropic.APIConnectionError as exc:
            log.error("Claude API connection error: %s", exc)
            return Reply(done=None, say="", available=False)

        if response.stop_reason == "refusal":
            return Reply(done=None, say="")
        text = next((block.text for block in response.content if block.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.error("Unparseable agent reply: %r", text[:200])
            return Reply(done=None, say="")
        return Reply(done=bool(data["done"]), say=str(data["say"]).strip(), urgent=bool(data["urgent"]))
