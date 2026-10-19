"""Ayyagaru's own chant recordings: one MP3 per pooja step, plus voice samples for cloning.

Recordings are personal (a family member's voice), so they live outside the repository:
$AYYAGARU_RECORDINGS, default ~/.ayyagaru/recordings.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

SAFE_ID = re.compile(r"^[a-z0-9_]{1,80}$")
MAX_UPLOAD_BYTES = 30_000_000


class RecordingError(ValueError):
    """The upload is not usable audio."""


def default_root() -> Path:
    return Path(os.environ.get("AYYAGARU_RECORDINGS", Path.home() / ".ayyagaru" / "recordings"))


def to_mp3(audio: bytes) -> bytes:
    """Convert a browser recording (WebM/Opus, MP4/AAC, WAV...) to level-matched mono MP3."""
    import imageio_ffmpeg

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "upload"
        source.write_bytes(audio)
        result = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", str(source),
             "-vn", "-ac", "1", "-ar", "44100", "-af", "loudnorm=I=-18:TP=-2:LRA=11",
             "-codec:a", "libmp3lame", "-b:a", "96k", "-f", "mp3", "pipe:1"],
            capture_output=True, timeout=120, check=False,
        )
    if result.returncode != 0 or not result.stdout:
        raise RecordingError(f"could not read the recording: {result.stderr.decode(errors='replace')[:200]}")
    return result.stdout


class ChantStore:
    def __init__(self, root: str | Path | None = None, transcode: Callable[[bytes], bytes] = to_mp3):
        self.root = Path(root) if root is not None else default_root()
        self.transcode = transcode

    def _path(self, pooja_id: str, step_id: str) -> Path:
        if not (SAFE_ID.match(pooja_id) and SAFE_ID.match(step_id)):
            raise KeyError(f"{pooja_id}/{step_id}")
        return self.root / pooja_id / f"{step_id}.mp3"

    def chant_path(self, pooja_id: str, step_id: str) -> Path | None:
        path = self._path(pooja_id, step_id)
        return path if path.is_file() else None

    def available(self, pooja_id: str) -> dict[str, int]:
        """step_id -> version (modification time), for cache-busting on re-record."""
        folder = self.root / pooja_id
        if not SAFE_ID.match(pooja_id) or not folder.is_dir():
            return {}
        return {p.stem: int(p.stat().st_mtime) for p in sorted(folder.glob("*.mp3"))}

    def save_chant(self, pooja_id: str, step_id: str, audio: bytes) -> int:
        path = self._path(pooja_id, step_id)
        mp3 = self._convert(audio)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(mp3)
        tmp.replace(path)
        return int(path.stat().st_mtime)

    def delete_chant(self, pooja_id: str, step_id: str) -> bool:
        path = self._path(pooja_id, step_id)
        if path.is_file():
            path.unlink()
            return True
        return False

    def save_voice_sample(self, audio: bytes) -> str:
        folder = self.root / "_voice_samples"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"sample_{time.strftime('%Y%m%d_%H%M%S')}.mp3"
        (folder / name).write_bytes(self._convert(audio))
        return name

    def voice_samples(self) -> list[str]:
        folder = self.root / "_voice_samples"
        return sorted(p.name for p in folder.glob("*.mp3")) if folder.is_dir() else []

    def _convert(self, audio: bytes) -> bytes:
        if not audio:
            raise RecordingError("empty recording")
        if len(audio) > MAX_UPLOAD_BYTES:
            raise RecordingError("recording too large")
        return self.transcode(audio)
