"""Speech to words with timestamps.

Default engine: faster-whisper running locally (no key, no upload). Any other
ASR works too: hand us its words as JSON (see `load_words`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .runtime import CONFIG_DIR
from .util import JyrError

CACHE = CONFIG_DIR / "asr-cache"
# Bias whisper towards simplified Chinese with punctuation.
ZH_PROMPT = "以下是普通话的句子，使用简体中文和标点。"
SENT_END = "。！？!?…"
CLAUSE_END = "，,、；;：:"


def _key(path: str, model: str, language: str) -> str:
    st = os.stat(path)
    return hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime_ns}|{model}|{language}".encode()).hexdigest()[:16]


def transcribe(path: str, model: str = "small", language: str = "zh", use_cache: bool = True) -> dict:
    """-> {"source", "words": [{"start","end","text"} in seconds], "engine"}"""
    path = str(Path(path).resolve())
    cache = CACHE / f"{_key(path, model, language)}.json"
    if use_cache and cache.exists():
        return json.loads(cache.read_text("utf-8"))
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise JyrError("local ASR needs faster-whisper: pip install faster-whisper "
                       "(or pass --words FILE from any other ASR)") from None
    wm = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _info = wm.transcribe(path, language=language, word_timestamps=True, vad_filter=False,
                                initial_prompt=ZH_PROMPT if language == "zh" else None,
                                condition_on_previous_text=False)
    words = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"start": round(w.start, 3), "end": round(w.end, 3), "text": t})
    data = {"source": path, "engine": f"faster-whisper/{model}", "words": _to_simplified(words)}
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, ensure_ascii=False))
    return data


def load_words(path: str) -> dict:
    """Bring-your-own ASR: {"words":[{"start":s,"end":s,"text":..}]} or a bare list."""
    raw = json.loads(Path(path).read_text("utf-8"))
    words = raw["words"] if isinstance(raw, dict) else raw
    for w in words:
        if not {"start", "end", "text"} <= set(w):
            raise JyrError("each word needs start, end (seconds) and text")
    return {"source": raw.get("source", "") if isinstance(raw, dict) else "", "engine": "external", "words": words}


_T2S = None


def _to_simplified(words: list[dict]) -> list[dict]:
    """Whisper sometimes answers in traditional characters; convert if OpenCC is around."""
    global _T2S
    try:
        if _T2S is None:
            from opencc import OpenCC
            _T2S = OpenCC("t2s")
        for w in words:
            w["text"] = _T2S.convert(w["text"])
    except ImportError:
        pass
    return words


def sentences(words: list[dict], max_chars: int = 40, max_gap: float = 0.8) -> list[dict]:
    """Group words into sentences on end punctuation or long silences."""
    out, cur = [], []

    def flush():
        if cur:
            out.append({"id": len(out), "start": cur[0]["start"], "end": cur[-1]["end"],
                        "text": "".join(w["text"] for w in cur), "words": list(cur)})
            cur.clear()

    for i, w in enumerate(words):
        if cur and (w["start"] - cur[-1]["end"] > max_gap):
            flush()
        cur.append(w)
        txt = "".join(x["text"] for x in cur)
        if w["text"][-1:] in SENT_END or len(txt) >= max_chars:
            flush()
    flush()
    return out


def strip_punct(text: str) -> str:
    return re.sub(rf"[{re.escape(SENT_END + CLAUSE_END)}。，\"“”]+$", "", re.sub(r"^[，,。]+", "", text)).strip()
