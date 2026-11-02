"""Draft files are plain JSON: jyr writes them as-is and reads only plain JSON.

JianYing and CapCut both open such drafts. After JianYing saves a draft it keeps
it in its own format, which jyr does not read; CapCut keeps plain JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from .runtime import Runtime
from .util import JyrError


def is_plain_json(data: bytes) -> bool:
    return data.lstrip()[:1] in (b"{", b"[")


def not_readable(rt: Runtime, path: Path) -> JyrError:
    if rt.is_capcut:
        return JyrError(f"{path} is not plain JSON — damaged, or not a CapCut draft file")
    return JyrError(f"{Path(path).parent.name}: JianYing has saved this draft in its own format, which jyr does "
                    "not read. jyr reads CapCut drafts and drafts it built itself.")


def read_json(rt: Runtime, path: Path) -> dict:
    raw = Path(path).read_bytes()
    if not is_plain_json(raw):
        raise not_readable(rt, path)
    return json.loads(raw)


def read_many(files: list[Path]) -> dict[Path, dict | None]:
    """Parse many draft files; None for ones that are not plain JSON."""
    out: dict[Path, dict | None] = {}
    for f in files:
        raw = Path(f).read_bytes()
        try:
            out[f] = json.loads(raw) if is_plain_json(raw) else None
        except (ValueError, UnicodeDecodeError):
            out[f] = None
    return out
