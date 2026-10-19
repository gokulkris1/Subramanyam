"""Web app for the live "call Ayyagaru" (అయ్యగారు) experience (phone browser: camera, mic, speaker)."""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import contextlib
import hmac
import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .agent import PriestAgent
from .pooja import Pooja, bundled_poojas
from .recordings import ChantStore, RecordingError

STATIC_DIR = Path(__file__).with_name("static")
MAX_FRAME_BYTES = 2_000_000
MODES = {"check", "live", "ask"}
MAX_TTS_CHARS = 600
TTS_CHUNK_CHARS = 180


def _pooja_payload(pooja: Pooja) -> dict[str, Any]:
    return pooja.raw | {"agent_notes_count": len(pooja.notes_for_agent)}


def split_for_tts(text: str, limit: int = TTS_CHUNK_CHARS) -> list[str]:
    """Split at sentence/clause boundaries into chunks the speech service accepts."""
    chunks: list[str] = []
    current = ""
    for piece in re.split(r"(?<=[.!?।,;])\s+", text):
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            chunks.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        if current and len(current) + 1 + len(piece) > limit:
            chunks.append(current)
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


async def google_tts(text: str, lang: str) -> bytes:
    """Telugu speech for devices without a Telugu voice (most iPhones, Macs).
    Uses Google Translate's public TTS endpoint: fine for a POC, swap for a
    licensed TTS API (Google Cloud / Azure te-IN voices) before launch."""
    audio = b""
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for chunk in split_for_tts(text):
            response = await client.get("https://translate.google.com/translate_tts", params={
                "ie": "UTF-8", "tl": lang, "client": "tw-ob", "q": chunk})
            response.raise_for_status()
            audio += response.content  # MP3 frames concatenate cleanly
    return audio


# Voice presets. Microsoft neural voices (via edge-tts) give a male Telugu voice; the
# Google voice is the fallback. Swap to a licensed Azure Speech key before launch.
VOICES: dict[str, dict[str, Any]] = {
    "ayyagaru": {"label_te": "అయ్యగారు – గంభీర పురుష స్వరం", "label_en": "Ayyagaru – deep male",
               "te": "te-IN-MohanNeural", "en": "en-IN-PrabhatNeural", "rate": "-10%", "pitch": "-8Hz"},
    "male": {"label_te": "పురుష స్వరం", "label_en": "Male",
             "te": "te-IN-MohanNeural", "en": "en-IN-PrabhatNeural", "rate": "+0%", "pitch": "+0Hz"},
    "female": {"label_te": "స్త్రీ స్వరం", "label_en": "Female",
               "te": "te-IN-ShrutiNeural", "en": "en-IN-NeerjaNeural", "rate": "-5%", "pitch": "+0Hz"},
}
DEFAULT_VOICE = "ayyagaru"


async def edge_voice_tts(text: str, lang: str, voice: str) -> bytes:
    import edge_tts

    preset = VOICES[voice]
    last_error: Exception | None = None
    for attempt in range(4):  # the free endpoint intermittently returns no audio
        try:
            audio = b""
            communicate = edge_tts.Communicate(text, preset[lang], rate=preset["rate"], pitch=preset["pitch"])
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
            if audio:
                return audio
            last_error = RuntimeError("edge-tts returned no audio")
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"edge-tts failed after retries: {last_error}")


# Paid, natural Indian voices (Sarvam AI "Bulbul"), offered when SARVAM_API_KEY is set.
# Any preset can be re-pointed without code: SARVAM_<ID>_SPEAKER / _MODEL / _PACE, e.g.
# SARVAM_AYYAGARU_SPEAKER=girish_hi_devotional.
SARVAM_VOICES: dict[str, dict[str, Any]] = {
    "ayyagaru": {"label_te": "అయ్యగారు – తరుణ్ (తెలుగు పురుష స్వరం)", "label_en": "Ayyagaru – Tarun (Telugu male)",
               "model": "bulbul:v4-flash", "speaker": "tarun_te_narration", "pace": 0.9},
    "devotional": {"label_te": "భక్తి స్వరం – శుభ్", "label_en": "Devotional – Shubh",
                   "model": "bulbul:v4-flash", "speaker": "shubh_hi_devotional", "pace": 0.9},
    "girish": {"label_te": "భక్తి స్వరం – గిరీష్", "label_en": "Devotional – Girish",
               "model": "bulbul:v4-flash", "speaker": "girish_hi_devotional", "pace": 0.9},
    "anand": {"label_te": "ఆనంద్", "label_en": "Anand", "model": "bulbul:v3", "speaker": "anand", "pace": 0.95},
    "vijay": {"label_te": "విజయ్", "label_en": "Vijay", "model": "bulbul:v3", "speaker": "vijay", "pace": 0.95},
    "female": {"label_te": "స్త్రీ స్వరం – కవిత", "label_en": "Female – Kavitha",
               "model": "bulbul:v4-flash", "speaker": "kavitha_te_narration", "pace": 0.95},
}


def sarvam_enabled() -> bool:
    return bool(os.environ.get("SARVAM_API_KEY"))


def available_voices() -> dict[str, dict[str, Any]]:
    return SARVAM_VOICES if sarvam_enabled() else VOICES


def sarvam_settings(voice: str) -> dict[str, Any]:
    settings = dict(SARVAM_VOICES[voice])
    for field in ("model", "speaker", "pace"):
        override = os.environ.get(f"SARVAM_{voice.upper()}_{field.upper()}")
        if override:
            settings[field] = float(override) if field == "pace" else override
    return settings


async def sarvam_tts(text: str, lang: str, voice: str) -> bytes:
    settings = sarvam_settings(voice)
    body = {
        "text": text, "language_code": "en-IN" if lang == "en" else "te-IN",
        "model": settings["model"], "speaker": settings["speaker"], "pace": settings["pace"],
        "output_audio_codec": "mp3", "speech_sample_rate": 24000,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.sarvam.ai/text-to-speech", json=body,
                                     headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]})
        if response.status_code >= 400:
            raise RuntimeError(f"Sarvam TTS {response.status_code}: {response.text[:200]}")
        return b"".join(base64.b64decode(audio) for audio in response.json()["audios"])


async def default_tts(text: str, lang: str, voice: str) -> bytes:
    if sarvam_enabled() and voice in SARVAM_VOICES:
        try:
            return await sarvam_tts(text, lang, voice)
        except Exception as exc:
            logging.getLogger(__name__).warning("Sarvam voice failed (%s); using free voice", exc)
    free_voice = voice if voice in VOICES else ("female" if voice == "female" else DEFAULT_VOICE)
    try:
        return await edge_voice_tts(text, lang, free_voice)
    except Exception as exc:  # network/service hiccup: keep Ayyagaru talking
        logging.getLogger(__name__).warning("Neural voice failed (%s); using Google voice", exc)
        return await google_tts(text, lang)


def create_app(agent: PriestAgent | None = None, poojas: dict[str, Pooja] | None = None,
               synthesize: Callable[[str, str, str], Awaitable[bytes]] = default_tts,
               warm_voices: bool = False, chants: ChantStore | None = None) -> Starlette:
    poojas = poojas if poojas is not None else bundled_poojas()
    state: dict[str, PriestAgent] = {}
    tts_cache: dict[tuple[str, str, str], bytes] = {}
    chants = chants if chants is not None else ChantStore()

    def get_agent() -> PriestAgent:
        if "agent" not in state:
            state["agent"] = agent if agent is not None else PriestAgent()
        return state["agent"]

    async def index(request: Request) -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    async def list_poojas(request: Request) -> JSONResponse:
        return JSONResponse([
            {"id": p.id, "title": p.title, "title_en": p.title_en, "steps": len(p.steps), "status": p.status}
            for p in poojas.values()
        ])

    async def get_pooja(request: Request) -> JSONResponse:
        pooja = poojas.get(request.path_params["pooja_id"])
        if pooja is None:
            return JSONResponse({"error": "unknown pooja"}, status_code=404)
        return JSONResponse(_pooja_payload(pooja) | {"vision": get_agent().available,
                                                     "chants": chants.available(pooja.id)})

    async def turn(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        pooja = poojas.get(body.get("pooja_id", ""))
        if pooja is None:
            return JSONResponse({"error": "unknown pooja"}, status_code=404)
        try:
            step = pooja.step(body.get("step_id", ""))
        except KeyError:
            return JSONResponse({"error": "unknown step"}, status_code=404)
        mode = body.get("mode")
        if mode not in MODES:
            return JSONResponse({"error": f"mode must be one of {sorted(MODES)}"}, status_code=400)

        frame = body.get("frame") or None
        if frame:
            if frame.startswith("data:"):
                frame = frame.split(",", 1)[-1]
            try:
                if len(base64.b64decode(frame, validate=True)) > MAX_FRAME_BYTES:
                    return JSONResponse({"error": "frame too large"}, status_code=413)
            except (binascii.Error, ValueError):
                return JSONResponse({"error": "frame must be base64 JPEG"}, status_code=400)

        history = body.get("history") or []
        if not isinstance(history, list):
            history = []
        reply = get_agent().respond(
            pooja, step, mode, frame_jpeg_b64=frame,
            heard=str(body.get("heard", ""))[:500],
            history=[turn for turn in history if isinstance(turn, dict)],
            language="en" if body.get("lang") == "en" else "te",
        )
        return JSONResponse(reply.as_payload())

    async def cached_speech(text: str, lang: str, voice: str) -> bytes:
        key = (lang, voice, text)
        if key not in tts_cache:
            audio = await synthesize(text, lang, voice)
            if len(tts_cache) > 2000:
                tts_cache.pop(next(iter(tts_cache)))
            tts_cache[key] = audio
        return tts_cache[key]

    async def warm_voice_cache() -> None:
        """Pre-render every scripted instruction in the default voice so the call never waits on TTS."""
        texts = {"నమస్కారం"} | {step.say for pooja in poojas.values() for step in pooja.steps}
        for text in texts:
            try:
                await cached_speech(text, "te", DEFAULT_VOICE)
            except Exception as exc:
                logging.getLogger(__name__).warning("Voice warm-up skipped a line: %s", exc)
        logging.getLogger(__name__).info("Voice cache warmed: %d lines", len(tts_cache))

    async def tts(request: Request) -> Response:
        text = request.query_params.get("text", "").strip()[:MAX_TTS_CHARS]
        lang = "en" if request.query_params.get("lang") == "en" else "te"
        voice = request.query_params.get("voice", DEFAULT_VOICE)
        if voice not in available_voices():
            voice = DEFAULT_VOICE
        if not text:
            return JSONResponse({"error": "text required"}, status_code=400)
        try:
            audio = await cached_speech(text, lang, voice)
        except httpx.HTTPError as exc:
            logging.getLogger(__name__).warning("TTS failed: %s", exc)
            return JSONResponse({"error": "tts unavailable"}, status_code=502)
        return Response(audio, media_type="audio/mpeg",
                        headers={"Cache-Control": "public, max-age=86400"})

    async def voices(request: Request) -> JSONResponse:
        return JSONResponse({"default": DEFAULT_VOICE, "voices": [
            {"id": key, "label_te": v["label_te"], "label_en": v["label_en"]} for key, v in available_voices().items()]})

    # ---- Ayyagaru's chant recordings (studio) ----
    def chant_step(request: Request) -> tuple[Pooja, str]:
        pooja = poojas.get(request.path_params["pooja_id"])
        if pooja is None:
            raise KeyError("pooja")
        step = pooja.step(request.path_params["step_id"])
        if step.segment is None:
            raise KeyError("step has no chant")
        return pooja, step.id

    def studio_denied(request: Request) -> JSONResponse | None:
        key = os.environ.get("STUDIO_KEY", "")
        if not key:
            return JSONResponse({"error": "studio disabled: set STUDIO_KEY on the server"}, status_code=403)
        if not hmac.compare_digest(request.headers.get("x-studio-key", ""), key):
            return JSONResponse({"error": "wrong studio key"}, status_code=401)
        return None

    async def studio_page(request: Request) -> FileResponse:
        return FileResponse(STATIC_DIR / "studio.html")

    async def studio_check(request: Request) -> JSONResponse:
        return studio_denied(request) or JSONResponse({"ok": True})

    async def chant_audio(request: Request) -> Response:
        try:
            pooja, step_id = chant_step(request)
        except KeyError:
            return JSONResponse({"error": "unknown chant"}, status_code=404)
        path = chants.chant_path(pooja.id, step_id)
        if path is None:
            return JSONResponse({"error": "not recorded yet"}, status_code=404)
        return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "no-cache"})

    async def chant_upload(request: Request) -> JSONResponse:
        if denied := studio_denied(request):
            return denied
        try:
            pooja, step_id = chant_step(request)
        except KeyError:
            return JSONResponse({"error": "unknown chant"}, status_code=404)
        if request.method == "DELETE":
            return JSONResponse({"deleted": chants.delete_chant(pooja.id, step_id)})
        try:
            version = await asyncio.to_thread(chants.save_chant, pooja.id, step_id, await request.body())
        except RecordingError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"ok": True, "version": version})

    async def voice_samples(request: Request) -> JSONResponse:
        if denied := studio_denied(request):
            return denied
        if request.method == "POST":
            try:
                name = await asyncio.to_thread(chants.save_voice_sample, await request.body())
            except RecordingError as exc:
                return JSONResponse({"error": str(exc)}, status_code=400)
            return JSONResponse({"ok": True, "name": name})
        return JSONResponse({"samples": chants.voice_samples()})

    warm_tasks: set[asyncio.Task] = set()

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        if warm_voices:
            task = asyncio.create_task(warm_voice_cache())
            warm_tasks.add(task)
            task.add_done_callback(warm_tasks.discard)
        yield
        for task in list(warm_tasks):
            task.cancel()

    return Starlette(lifespan=lifespan, routes=[
        Route("/", index),
        Route("/api/tts", tts),
        Route("/api/voices", voices),
        Route("/studio", studio_page),
        Route("/api/studio/check", studio_check),
        Route("/api/chant/{pooja_id}/{step_id}", chant_audio),
        Route("/api/studio/chant/{pooja_id}/{step_id}", chant_upload, methods=["PUT", "DELETE"]),
        Route("/api/studio/voice-samples", voice_samples, methods=["GET", "POST"]),
        Route("/api/poojas", list_poojas),
        Route("/api/poojas/{pooja_id}", get_pooja),
        Route("/api/turn", turn, methods=["POST"]),
        Mount("/static", StaticFiles(directory=STATIC_DIR), name="static"),
    ])


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Run the live Ayyagaru pooja call web app.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ssl-certfile", help="TLS certificate, needed for camera access from a phone on your LAN")
    parser.add_argument("--ssl-keyfile")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(warm_voices=True), host=args.host, port=args.port,
                ssl_certfile=args.ssl_certfile, ssl_keyfile=args.ssl_keyfile)


if __name__ == "__main__":
    main()
