"""Score a rough-cut plan against a human cut's SRT (text-level).

recall    = share of the human-kept text that our cut also keeps
ceiling   = the same share for the *uncut* transcript (ASR mismatch bound)
usage: python3 tools/score_roughcut.py PLAN HUMAN.srt RAW_MEDIA
"""
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jyr import asr  # noqa: E402
from jyr.srt import parse_srt  # noqa: E402


def norm(t):
    return re.sub(r"[^\w一-鿿]", "", t).lower()


def matched(a, b):
    s = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(x.size for x in s.get_matching_blocks())


plan = json.load(open(sys.argv[1]))
human = norm("".join(c[2] for c in parse_srt(Path(sys.argv[2]).read_text("utf-8-sig"))))
ours = norm("".join(c["text"] for t in plan["tracks"] if t["type"] == "subtitle" for c in t["clips"]))
raw = norm("".join(w["text"] for w in asr.transcribe(sys.argv[3])["words"]))
dur = sum(c["duration"] for c in plan["tracks"][0]["clips"])
hm = matched(human, raw)
print(json.dumps({
    "chars": {"raw": len(raw), "human": len(human), "ours": len(ours)},
    "our_duration_s": round(dur, 1),
    "recall_pct": round(100 * matched(human, ours) / len(human), 1),
    "ceiling_pct": round(100 * hm / len(human), 1),
    "raw_chars_human_dropped": len(raw) - hm,
    "raw_chars_we_dropped": len(raw) - len(ours),
}, ensure_ascii=False, indent=1))
