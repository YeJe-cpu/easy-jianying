"""SRT read/write."""

from __future__ import annotations

import re

from .util import JyrError

_TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def _us(ts: str) -> int:
    m = _TS.fullmatch(ts.strip())
    if not m:
        raise JyrError(f"bad SRT timestamp {ts!r}")
    h, mi, s, ms = m.groups()
    return ((int(h) * 60 + int(mi)) * 60 + int(s)) * 1_000_000 + int(ms.ljust(3, "0")) * 1000


def parse_srt(text: str) -> list[tuple[int, int, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        i = 1 if "-->" not in lines[0] else 0
        a, b = lines[i].split("-->")
        body = " ".join(lines[i + 1 :]).strip()
        if body:
            cues.append((_us(a), _us(b.split()[0]), body))
    if not cues:
        raise JyrError("no cues found in SRT")
    return cues


def _ts(us_: int) -> str:
    ms = int(round(us_ / 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[tuple[int, int, str]]) -> str:
    return "\n".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))
