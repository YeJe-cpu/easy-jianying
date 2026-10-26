"""字体自动调配: pick fonts from what this machine has, guided by the user's own habits.

Roles: title (标题), subtitle (字幕), body (正文), handwriting (手写), cute (可爱).
Score = how often the user used the font for that role in past drafts, plus a
name-based style match; only fonts present on disk are considered.
"""

from __future__ import annotations

from ..catalog import Catalog

STYLE_HINTS = {
    "title": ["黑", "粗", "综艺", "标题", "新青年", "庞门", "优设", "站酷", "锐", "Bold", "Heavy", "Black"],
    "subtitle": ["黑", "圆", "苹方", "思源", "本黑", "PingFang", "Sans", "Hei", "system", "zh-hans"],
    "body": ["宋", "明", "书", "思源", "Song", "Serif"],
    "handwriting": ["手写", "手书", "行书", "楷", "毛笔", "草书", "书法", "Kaiti", "Xingkai"],
    "cute": ["圆", "可爱", "萌", "童", "卡通", "Yuanti", "Round"],
}


def candidates(cat: Catalog, role: str) -> list[dict]:
    hints = STYLE_HINTS.get(role)
    if hints is None:
        raise ValueError(f"unknown font role {role!r}; use {list(STYLE_HINTS)}")
    scored = []
    for e in cat.list("font"):
        if not e.get("available"):
            continue
        name = e["name"] + " " + e["path"].rsplit("/", 1)[-1]
        style = sum(1 for h in hints if h.lower() in name.lower())
        habit = e.get("roles", {}).get(role, 0)
        score = habit * 10 + style * 5 + min(e.get("seen", 0), 50) / 10
        if style or habit:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, e in scored:
        if e["name"] not in seen:  # same font cached twice: keep the better-scored copy
            seen.add(e["name"])
            out.append(e)
    return out


def pick(cat: Catalog, role: str) -> dict:
    c = candidates(cat, role)
    if not c:
        return cat.find("font", "zh-hans")  # JianYing's built-in system font
    return c[0]
