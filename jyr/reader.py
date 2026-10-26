"""Read existing drafts: find them, summarise them, export subtitles."""

from __future__ import annotations

import json
from pathlib import Path

from .runtime import Runtime
from .srt import to_srt
from .util import JyrError
from .writer import read_info, read_meta


def resolve(rt: Runtime, ref: str) -> Path:
    """A draft by folder path, folder name, or home-screen name."""
    p = Path(ref).expanduser()
    if p.is_dir() and (p / "draft_info.json").exists():
        return p.resolve()
    cand = rt.draft_root / ref
    if (cand / "draft_info.json").exists():
        return cand
    hits = [d for d in rt.draft_root.iterdir() if d.is_dir() and ref in d.name and (d / "draft_info.json").exists()]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise JyrError(f"{ref!r} matches several drafts: {[h.name for h in hits][:8]}")
    raise JyrError(f"no draft named {ref!r} in {rt.draft_root}")


def list_drafts(rt: Runtime) -> list[dict]:
    index = json.loads((rt.draft_root / "root_meta_info.json").read_text("utf-8"))
    out = []
    for e in index.get("all_draft_store", []):
        out.append({"name": e.get("draft_name"), "duration_s": round(e.get("tm_duration", 0) / 1e6, 2),
                    "modified_us": e.get("tm_draft_modified", 0), "folder": e.get("draft_fold_path")})
    return sorted(out, key=lambda x: -x["modified_us"])


def text_of(mat: dict) -> str:
    try:
        return json.loads(mat.get("content") or "{}").get("text", "")
    except json.JSONDecodeError:
        return mat.get("content", "")


def materials_by_id(info: dict) -> dict:
    return {m["id"]: (k, m) for k, v in info.get("materials", {}).items() if isinstance(v, list)
            for m in v if isinstance(m, dict) and "id" in m}


def inspect(rt: Runtime, folder: Path) -> dict:
    info = read_info(rt, folder)
    meta = read_meta(rt, folder)
    mats = materials_by_id(info)
    tracks, missing, used = [], set(), {}
    for t in info.get("tracks", []):
        segs = []
        for s in t.get("segments", []):
            kind, m = mats.get(s.get("material_id"), ("?", {}))
            tr = s.get("target_timerange", {})
            row = {"start": round(tr.get("start", 0) / 1e6, 3), "duration": round(tr.get("duration", 0) / 1e6, 3)}
            if kind in ("videos", "audios"):
                row["src"] = m.get("path", "")
                if row["src"] and not row["src"].startswith("##_") and not Path(row["src"]).exists():
                    missing.add(row["src"])
                if s.get("speed", 1) != 1:
                    row["speed"] = s["speed"]
            elif kind == "texts":
                row["text"] = text_of(m)
            elif m.get("name"):
                row["name"] = m["name"]
            for ref in s.get("extra_material_refs", []):
                rk, rm = mats.get(ref, ("?", {}))
                if rm.get("name"):
                    used.setdefault(rk, set()).add(rm["name"])
                for a in rm.get("animations", []) or []:
                    if a.get("name"):
                        used.setdefault("animations", set()).add(a["name"])
            segs.append(row)
        tracks.append({"type": t.get("type"), "name": t.get("name", ""), "subtitle": t.get("flag") == 1,
                       "segments": segs})
    return {"name": folder.name, "folder": str(folder), "draft_id": meta.get("draft_id"),
            "timeline_version": info.get("new_version"),
            "app": (info.get("last_modified_platform") or {}).get("app_version"),
            "canvas": info.get("canvas_config"), "fps": info.get("fps"),
            "duration_s": round(info.get("duration", 0) / 1e6, 3), "tracks": tracks,
            "missing_media": sorted(missing), "resources_used": {k: sorted(v) for k, v in used.items()}}


def export_srt(rt: Runtime, folder: Path, which: str = "auto") -> str:
    """which: auto (subtitle tracks if any, else all text), subtitle, all"""
    info = read_info(rt, folder)
    mats = materials_by_id(info)
    text_tracks = [t for t in info.get("tracks", []) if t.get("type") == "text"]
    subs = [t for t in text_tracks if t.get("flag") == 1]
    if which == "subtitle" or (which == "auto" and subs):
        text_tracks = subs
    cues = []
    for t in text_tracks:
        for s in t.get("segments", []):
            k, m = mats.get(s.get("material_id"), ("?", {}))
            if k != "texts":
                continue
            tr = s["target_timerange"]
            cues.append((tr.get("start", 0), tr.get("start", 0) + tr["duration"], text_of(m)))
    cues.sort()
    return to_srt(cues)
