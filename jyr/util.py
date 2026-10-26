"""Small helpers shared by every module."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path


class JyrError(Exception):
    """A user-facing error: the message says what to fix."""


def new_id() -> str:
    """JianYing ids are upper-case UUID4 strings."""
    return str(uuid.uuid4()).upper()


def us(seconds: float | int) -> int:
    """Seconds (plan unit) -> microseconds (draft unit)."""
    return int(round(float(seconds) * 1_000_000))


def now_us() -> int:
    return int(time.time() * 1_000_000)


def hex_to_rgb(color: str) -> list[float]:
    c = color.lstrip("#")
    if len(c) != 6:
        raise JyrError(f"color must be #RRGGBB, got {color!r}")
    return [round(int(c[i : i + 2], 16) / 255, 6) for i in (0, 2, 4)]


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def atomic_write(path: Path, data: bytes | str) -> None:
    """Write via a temp file in the same folder, then rename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".jyr-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
