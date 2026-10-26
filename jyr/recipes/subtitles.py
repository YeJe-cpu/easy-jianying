"""Words with timestamps -> subtitle cues that look like JianYing's own 识别字幕."""

from __future__ import annotations

import re

from ..asr import CLAUSE_END, SENT_END, strip_punct

BREAK = SENT_END + CLAUSE_END


def cues_from_words(words: list[dict], max_chars: int = 16, max_dur: float = 4.0, gap: float = 0.6) -> list[dict]:
    """Greedy grouping: break on punctuation, long gaps, length and duration limits."""
    cues, cur = [], []

    def flush():
        if not cur:
            return
        text = strip_punct("".join(w["text"] for w in cur))
        text = re.sub(rf"[{re.escape(BREAK)}]", " ", text).strip()
        if text:
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": re.sub(r"\s+", " ", text),
                         "words": [dict(w) for w in cur]})
        cur.clear()

    for w in words:
        if cur:
            length = len("".join(x["text"] for x in cur) + w["text"])
            if w["start"] - cur[-1]["end"] > gap or length > max_chars or w["end"] - cur[0]["start"] > max_dur:
                flush()
        cur.append(w)
        if w["text"][-1:] in BREAK:
            flush()
    flush()
    # Close tiny holes so subtitles don't flicker between cues.
    for a, b in zip(cues, cues[1:]):
        if 0 < b["start"] - a["end"] < 0.3:
            a["end"] = b["start"]
    return cues


def jianying_words(cue: dict) -> dict:
    """The per-word timing JianYing stores on 识别字幕 (ms, relative to the cue)."""
    s = cue["start"]
    ws = [w for w in cue["words"] if strip_punct(w["text"])]
    return {"start_time": [int(round((w["start"] - s) * 1000)) for w in ws],
            "end_time": [int(round((w["end"] - s) * 1000)) for w in ws],
            "text": [strip_punct(w["text"]) for w in ws]}


def subtitle_track(cues: list[dict], style: dict | None = None, y: float | None = None) -> dict:
    clips = []
    for c in cues:
        clip = {"text": c["text"], "start": round(c["start"], 3), "duration": round(max(c["end"] - c["start"], 0.3), 3),
                "words": jianying_words(c)}
        if style:
            clip["style"] = style
        if y is not None:
            clip["transform"] = {"y": y}
        clips.append(clip)
    return {"type": "subtitle", "name": "字幕", "clips": clips}
