import base64
import copy
import json
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from priest.agent import PriestAgent, Reply
from priest.app import create_app
from priest.pooja import PoojaError, bundled_poojas, parse_pooja

POOJA_ID = "mahanavami_mahishasura_mardini"


def test_bundled_mahanavami_script_is_consistent():
    pooja = bundled_poojas()[POOJA_ID]
    assert pooja.youtube_id == "Iskh_EQqvwQ"
    segments = [step.segment for step in pooja.steps if step.segment]
    assert len(segments) >= 20
    for (start, end), (next_start, _) in zip(segments, segments[1:]):
        assert start < end <= next_start, "video segments must play forward without overlap"
    ids = [step.id for step in pooja.steps]
    assert ids[0] == "prep_items" and ids[-1] == "closing"
    assert "kumkuma_puja" in ids and "sankalpam" in ids
    for step in pooja.steps:
        assert step.say and step.say_en
        if step.action == "do":
            assert step.check


def test_parse_rejects_segment_outside_video():
    raw = copy.deepcopy(bundled_poojas()[POOJA_ID].raw)
    raw["steps"][2]["segment"] = [1500, 1600]
    with pytest.raises(PoojaError):
        parse_pooja(raw)


def test_parse_rejects_do_step_without_check():
    raw = copy.deepcopy(bundled_poojas()[POOJA_ID].raw)
    raw["steps"][0]["check"] = None
    with pytest.raises(PoojaError):
        parse_pooja(raw)


class FakeAgent:
    available = True

    def __init__(self):
        self.calls = []

    def respond(self, pooja, step, mode, **kwargs):
        self.calls.append((step.id, mode, kwargs))
        return Reply(done=True, say="బాగుంది")


def test_turn_endpoint_passes_frame_and_returns_reply():
    agent = FakeAgent()
    client = TestClient(create_app(agent=agent))
    frame = base64.b64encode(b"\xff\xd8fake-jpeg").decode()
    response = client.post("/api/turn", json={
        "pooja_id": POOJA_ID, "step_id": "prep_lamp", "mode": "check",
        "frame": "data:image/jpeg;base64," + frame, "heard": "అయిపోయింది", "lang": "te",
        "history": [{"who": "User", "text": "hi"}, "junk"],
    })
    assert response.status_code == 200
    assert response.json() == {"done": True, "say": "బాగుంది", "urgent": False, "available": True}
    step_id, mode, kwargs = agent.calls[0]
    assert (step_id, mode) == ("prep_lamp", "check")
    assert kwargs["frame_jpeg_b64"] == frame
    assert kwargs["history"] == [{"who": "User", "text": "hi"}]


@pytest.mark.parametrize("body, status", [
    ({"pooja_id": "nope", "step_id": "x", "mode": "check"}, 404),
    ({"pooja_id": POOJA_ID, "step_id": "nope", "mode": "check"}, 404),
    ({"pooja_id": POOJA_ID, "step_id": "prep_lamp", "mode": "sing"}, 400),
    ({"pooja_id": POOJA_ID, "step_id": "prep_lamp", "mode": "check", "frame": "not base64!"}, 400),
])
def test_turn_endpoint_rejects_bad_input(body, status):
    assert TestClient(create_app(agent=FakeAgent())).post("/api/turn", json=body).status_code == status


def test_pages_and_pooja_payload_served():
    client = TestClient(create_app(agent=FakeAgent()))
    assert "Ayyagaru" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/poojas").json()[0]["id"] == POOJA_ID
    payload = client.get(f"/api/poojas/{POOJA_ID}").json()
    assert payload["vision"] is True and payload["video"]["youtube_id"] == "Iskh_EQqvwQ"


def test_agent_without_credentials_is_unavailable(monkeypatch, tmp_path):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    agent = PriestAgent()
    pooja = bundled_poojas()[POOJA_ID]
    reply = agent.respond(pooja, pooja.steps[0], "check", frame_jpeg_b64="AAAA")
    assert not agent.available and reply.available is False and reply.done is None


def test_agent_builds_vision_request_and_parses_json():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text=json.dumps({"done": False, "say": "దీపం వెలిగించండి", "urgent": False})),
        ])

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    agent = PriestAgent(model="claude-opus-5-5", client=client)
    pooja = bundled_poojas()[POOJA_ID]
    reply = agent.respond(pooja, pooja.step("prep_lamp"), "check", frame_jpeg_b64="AAAA", language="te")
    assert reply == Reply(done=False, say="దీపం వెలిగించండి", urgent=False)
    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["data"] == "AAAA"
    assert "Light the lamp" in content[1]["text"]
    assert captured["output_config"]["format"]["type"] == "json_schema"
    assert "Telugu" in captured["system"][0]["text"]
    assert "Mahishasura Mardini" in captured["system"][1]["text"]


def test_split_for_tts_respects_limit_and_keeps_text():
    from priest.app import split_for_tts
    text = bundled_poojas()[POOJA_ID].step("achamanam").say
    chunks = split_for_tts(text, limit=60)
    assert all(len(chunk) <= 60 for chunk in chunks)
    assert " ".join(chunks).split() == text.split()


def test_tts_endpoint_returns_cached_telugu_audio(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    calls = []

    async def fake_synth(text, lang, voice):
        calls.append((text, lang, voice))
        return b"ID3fake-mp3"

    client = TestClient(create_app(agent=FakeAgent(), synthesize=fake_synth))
    for _ in range(2):
        response = client.get("/api/tts", params={"text": "నమస్కారం", "voice": "bogus"})
        assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
        assert response.content == b"ID3fake-mp3"
    assert calls == [("నమస్కారం", "te", "ayyagaru")]
    client.get("/api/tts", params={"text": "నమస్కారం", "voice": "female"})
    assert calls[-1] == ("నమస్కారం", "te", "female")
    voices = client.get("/api/voices").json()
    assert voices["default"] == "ayyagaru" and {v["id"] for v in voices["voices"]} == {"ayyagaru", "male", "female"}
    assert client.get("/api/tts").status_code == 400


def test_sarvam_preset_overrides(monkeypatch):
    from priest.app import available_voices, sarvam_settings
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert set(available_voices()) == {"ayyagaru", "male", "female"}
    monkeypatch.setenv("SARVAM_API_KEY", "test")
    assert "devotional" in available_voices()
    assert sarvam_settings("ayyagaru")["speaker"] == "tarun_te_narration"
    monkeypatch.setenv("SARVAM_AYYAGARU_SPEAKER", "girish_hi_devotional")
    monkeypatch.setenv("SARVAM_AYYAGARU_PACE", "0.85")
    settings = sarvam_settings("ayyagaru")
    assert settings["speaker"] == "girish_hi_devotional" and settings["pace"] == 0.85


def _wav(seconds=0.5, rate=16000):
    import io, math, struct, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate)))
                               for i in range(int(seconds * rate))))
    return buf.getvalue()


def test_studio_records_converts_and_serves_chants(monkeypatch, tmp_path):
    from priest.recordings import ChantStore
    monkeypatch.setenv("STUDIO_KEY", "s3cret")
    client = TestClient(create_app(agent=FakeAgent(), chants=ChantStore(tmp_path)))
    url = f"/api/studio/chant/{POOJA_ID}/prarthana"

    assert client.put(url, content=_wav()).status_code == 401
    assert client.put(url, content=_wav(), headers={"x-studio-key": "nope"}).status_code == 401
    assert client.get(f"/api/chant/{POOJA_ID}/prarthana").status_code == 404

    saved = client.put(url, content=_wav(), headers={"x-studio-key": "s3cret"})
    assert saved.status_code == 200 and saved.json()["ok"]
    audio = client.get(f"/api/chant/{POOJA_ID}/prarthana")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/mpeg" and len(audio.content) > 500
    assert "prarthana" in client.get(f"/api/poojas/{POOJA_ID}").json()["chants"]

    bad = client.put(url, content=b"not audio", headers={"x-studio-key": "s3cret"})
    assert bad.status_code == 400
    # steps without a chant segment, unknown steps and path tricks are refused
    for step in ("prep_items", "nope", "..%2F..%2Fetc"):
        assert client.put(f"/api/studio/chant/{POOJA_ID}/{step}", content=_wav(),
                          headers={"x-studio-key": "s3cret"}).status_code == 404

    assert client.delete(url, headers={"x-studio-key": "s3cret"}).json() == {"deleted": True}
    assert client.get(f"/api/chant/{POOJA_ID}/prarthana").status_code == 404


def test_studio_disabled_without_key_and_voice_samples(monkeypatch, tmp_path):
    from priest.recordings import ChantStore
    monkeypatch.delenv("STUDIO_KEY", raising=False)
    client = TestClient(create_app(agent=FakeAgent(), chants=ChantStore(tmp_path)))
    assert client.get("/api/studio/check").status_code == 403
    assert client.get("/studio").status_code == 200

    monkeypatch.setenv("STUDIO_KEY", "k")
    headers = {"x-studio-key": "k"}
    assert client.post("/api/studio/voice-samples", content=_wav(), headers=headers).json()["ok"]
    assert len(client.get("/api/studio/voice-samples", headers=headers).json()["samples"]) == 1
