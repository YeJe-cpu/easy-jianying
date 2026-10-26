"""口播粗剪: drop fillers, stutters, false starts and dead air; keep the speaker's voice.

Two passes, so an agent can stay in the loop:
  analyze() -> numbered sentences + automatic suggestions (what would be cut and why)
  apply()   -> keep-ranges -> plan with the A-roll chopped on one track + re-timed subtitles
An agent (or a person) can edit the suggestions — e.g. drop a whole sentence
that repeats an earlier point — before apply().
"""

from __future__ import annotations

from ..asr import sentences, strip_punct
from ..media import probe
from .subtitles import cues_from_words, subtitle_track

FILLERS = {"嗯", "呃", "额", "啊", "哦", "唔", "嗯嗯", "呃呃", "啊啊", "emm", "um", "uh"}


def analyze(words: list[dict], pause: float = 0.5, fillers: set[str] | None = None) -> dict:
    fillers = FILLERS if fillers is None else fillers
    sents = sentences(words)
    drops = []  # {"sentence", "word", "reason"}
    for s in sents:
        ws = s["words"]
        for i, w in enumerate(ws):
            core = strip_punct(w["text"]).lower()
            if core in fillers:
                drops.append({"sentence": s["id"], "word": i, "text": w["text"], "reason": "filler"})
        # stutter: the same 1-4 chars said twice in a row ("我我", "就是就是")
        for i in range(len(ws) - 1):
            a, b = strip_punct(ws[i]["text"]), strip_punct(ws[i + 1]["text"])
            if a and a == b and len(a) <= 4:
                drops.append({"sentence": s["id"], "word": i, "text": ws[i]["text"], "reason": "repeat"})
    # false start: a short sentence that the next one restarts
    for a, b in zip(sents, sents[1:]):
        ta, tb = strip_punct(a["text"]), strip_punct(b["text"])
        if 2 <= len(ta) < len(tb) and tb.startswith(ta[: max(2, min(len(ta), 4))]) and len(ta) <= 0.6 * len(tb):
            drops.append({"sentence": a["id"], "word": None, "text": a["text"], "reason": "false-start"})
    return {"pause": pause, "sentences": [{k: s[k] for k in ("id", "start", "end", "text")} for s in sents],
            "drops": drops, "_words": [s["words"] for s in sents]}


def keep_ranges(analysis: dict, pad: float = 0.12, min_keep: float = 0.2) -> list[tuple[float, float, list]]:
    """-> [(src_start, src_end, words_in_range)] after applying drops and trimming pauses."""
    gone_sent = {d["sentence"] for d in analysis["drops"] if d["word"] is None}
    gone_word = {(d["sentence"], d["word"]) for d in analysis["drops"] if d["word"] is not None}
    kept = []
    for sid, ws in enumerate(analysis["_words"]):
        if sid in gone_sent:
            continue
        kept += [w for i, w in enumerate(ws) if (sid, i) not in gone_word]
    ranges = []
    for w in kept:
        if ranges and w["start"] - ranges[-1][2][-1]["end"] < analysis["pause"]:
            ranges[-1][1] = w["end"] + pad
            ranges[-1][2].append(w)
        else:
            ranges.append([max(0.0, w["start"] - pad), w["end"] + pad, [w]])
    # trim overlaps created by padding
    for x, y in zip(ranges, ranges[1:]):
        if x[1] > y[0]:
            mid = (x[2][-1]["end"] + y[2][0]["start"]) / 2
            x[1], y[0] = mid, mid
    return [(a, b, ws) for a, b, ws in ranges if b - a >= min_keep]


def build_plan(src: str, analysis: dict, name: str = "口播粗剪", subtitles: bool = True,
               canvas: str | dict | None = None, sub_style: dict | None = None) -> tuple[dict, dict]:
    info = probe(src)
    dur = info.duration_us / 1e6
    ranges = [(a, min(b, dur), ws) for a, b, ws in keep_ranges(analysis)]
    clips, new_words, t = [], [], 0.0
    for a, b, ws in ranges:
        clips.append({"src": src, "in": round(a, 3), "duration": round(b - a, 3)})
        for w in ws:
            new_words.append({"start": t + (w["start"] - a), "end": t + (w["end"] - a), "text": w["text"]})
        t += round(b - a, 3)
    if canvas is None:
        canvas = {"width": info.width or 1080, "height": info.height or 1920}
    plan = {"name": name, "canvas": canvas, "tracks": [{"type": "video", "name": "口播", "clips": clips}]}
    if subtitles:
        plan["tracks"].append(subtitle_track(cues_from_words(new_words), style=sub_style))
    report = {"source_s": round(dur, 2), "result_s": round(t, 2), "cut_s": round(dur - t, 2),
              "segments": len(clips), "drops": [{k: d[k] for k in ("sentence", "text", "reason")} for d in analysis["drops"]]}
    return plan, report


def apply_edits(analysis: dict, edits: dict) -> dict:
    """edits: {"drop_sentences":[ids], "keep":[{"sentence":id,"word":i|null}], "drop_words":[[sid,i],..]}"""
    drops = list(analysis["drops"])
    restore = {(k["sentence"], k.get("word")) for k in edits.get("keep", [])}
    drops = [d for d in drops if (d["sentence"], d["word"]) not in restore]
    for sid in edits.get("drop_sentences", []):
        drops.append({"sentence": sid, "word": None, "text": analysis["sentences"][sid]["text"], "reason": "agent"})
    for sid, wi in edits.get("drop_words", []):
        drops.append({"sentence": sid, "word": wi, "text": analysis["_words"][sid][wi]["text"], "reason": "agent"})
    return {**analysis, "drops": drops}
