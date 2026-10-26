"""Probe local media with ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .util import JyrError

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".heic"}
# JianYing gives still images a 3-hour material duration.
STILL_DURATION_US = 10_800_000_000


@dataclass(frozen=True)
class MediaInfo:
    path: str
    kind: str  # "video" | "photo" | "audio"
    duration_us: int
    width: int
    height: int
    has_audio: bool


@lru_cache(maxsize=512)
def probe(path: str) -> MediaInfo:
    p = Path(path)
    if not p.is_absolute():
        raise JyrError(f"media path must be absolute: {path}")
    if not p.is_file():
        raise JyrError(f"media not found: {path}")
    if not shutil.which("ffprobe"):
        raise JyrError("ffprobe not found; install ffmpeg (brew install ffmpeg)")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise JyrError(f"ffprobe cannot read {path}: {out.stderr.strip()[:200]}")
    info = json.loads(out.stdout)
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    ext = p.suffix.lower()
    if video is not None and (ext in IMAGE_EXT and ext != ".gif" or video.get("disposition", {}).get("attached_pic")):
        if audio is None or ext in IMAGE_EXT:
            return MediaInfo(str(p), "photo", STILL_DURATION_US, int(video.get("width", 0)), int(video.get("height", 0)), False)
    dur = float(info.get("format", {}).get("duration") or 0)
    if video is not None:
        w, h = int(video.get("width", 0)), int(video.get("height", 0))
        rot = _rotation(video)
        if rot in (90, 270):
            w, h = h, w
        return MediaInfo(str(p), "video", int(dur * 1_000_000), w, h, audio is not None)
    if audio is not None:
        return MediaInfo(str(p), "audio", int(dur * 1_000_000), 0, 0, True)
    raise JyrError(f"no audio or video stream in {path}")


def _rotation(stream: dict) -> int:
    rot = stream.get("tags", {}).get("rotate")
    if rot is None:
        for side in stream.get("side_data_list", []) or []:
            if "rotation" in side:
                rot = side["rotation"]
    try:
        return abs(int(float(rot))) % 360
    except (TypeError, ValueError):
        return 0
