"""Change an existing draft — always on a copy, never the original.

clone(src) copies the draft out to a work folder, ops change it there, and
home.publish() puts the result on the home screen as a new draft.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import tempfile
from pathlib import Path

from . import crypto, home
from .draft import Draft
from .reader import materials_by_id, text_of
from .runtime import Runtime, jianying_running
from .srt import parse_srt
from .util import JyrError, atomic_write, dump

SKIP = {".locked", ".backup", "template.tmp", "template-2.tmp", ".jyr.json"}


def _info_files(folder: Path, timeline_id: str) -> list[Path]:
    files = [folder / "draft_info.json", folder / "draft_info.json.bak",
             folder / "Timelines" / timeline_id / "draft_info.json",
             folder / "Timelines" / timeline_id / "draft_info.json.bak"]
    return [f for f in files if f.exists() or f.name == "draft_info.json"]


class Session:
    """An editable copy of a draft."""

    def __init__(self, rt: Runtime, src: Path, work: Path | None = None):
        if jianying_running():
            raise JyrError("quit JianYing first — it holds open drafts and rewrites them on exit")
        self.rt = rt
        self.src = Path(src)
        self.work = Path(work or tempfile.mkdtemp(prefix="jyr-edit-")) / self.src.name
        shutil.copytree(self.src, self.work, ignore=lambda d, names: [n for n in names if n in SKIP])
        for tmp in self.work.rglob("template*.tmp"):
            tmp.unlink()  # crash-recovery copies; they would shadow our edit
        self.info = json.loads(crypto.decrypt_bytes(rt, (self.work / "draft_info.json").read_bytes()))
        self.meta = json.loads(crypto.decrypt_bytes(rt, (self.work / "draft_meta_info.json").read_bytes()))
        self.log: list[str] = []

    # ---------------- ops ----------------
    def replace_text(self, find: str, replace: str, regex: bool = False) -> int:
        n = 0
        for m in self.info["materials"].get("texts", []):
            try:
                content = json.loads(m.get("content") or "{}")
            except json.JSONDecodeError:
                continue
            old = content.get("text", "")
            new = re.sub(find, replace, old) if regex else old.replace(find, replace)
            if new == old:
                continue
            content["text"] = new
            styles = content.get("styles") or []
            if styles:
                # Per-character styling can't survive a length change; keep the first style for all.
                first = styles[0] if len(new) != len(old) else None
                if first is not None:
                    first["range"] = [0, len(new)]
                    content["styles"] = [first]
            m["content"] = json.dumps(content, ensure_ascii=False)
            for k in ("base_content",):
                if k in m:
                    m[k] = m["content"]
            if "recognize_text" in m:
                m["recognize_text"] = new
            m["words"] = {}
            n += 1
        self.log.append(f"replace_text {find!r}->{replace!r}: {n} texts")
        return n

    def relink(self, mapping: dict[str, str] | None = None, search_dirs: list[str] | None = None) -> int:
        """Point missing media at new files: explicit old->new, or find by file name in search_dirs."""
        mapping = dict(mapping or {})
        pool = {}
        for d in search_dirs or []:
            for p in Path(d).expanduser().rglob("*"):
                if p.is_file():
                    pool.setdefault(p.name, str(p))
        n = 0
        for kind in ("videos", "audios"):
            for m in self.info["materials"].get(kind, []):
                old = m.get("path", "")
                if not old or old.startswith("##_"):
                    continue
                new = mapping.get(old)
                if new is None and not Path(old).exists():
                    new = pool.get(Path(old).name)
                if new and new != old:
                    if not Path(new).exists():
                        raise JyrError(f"relink target missing: {new}")
                    m["path"] = new
                    mapping[old] = new
                    n += 1
        for group in self.meta.get("draft_materials", []):
            for v in group.get("value", []):
                if v.get("file_Path") in mapping:
                    v["file_Path"] = mapping[v["file_Path"]]
        self.log.append(f"relink: {n} materials")
        return n

    def track_volume(self, index: int, volume: float) -> None:
        t = self._track(index)
        for s in t["segments"]:
            s["volume"] = float(volume)
            if volume:
                s["last_nonzero_volume"] = float(volume)
        self.log.append(f"track {index} volume={volume}")

    def remove_tracks(self, kind: str | None = None, subtitle: bool | None = None, index: int | None = None) -> int:
        keep, n = [], 0
        for i, t in enumerate(self.info["tracks"]):
            hit = (index is not None and i == index) or (index is None and (kind is None or t["type"] == kind)
                                                       and (subtitle is None or (t.get("flag") == 1) == subtitle))
            if hit:
                n += 1
            else:
                keep.append(t)
        self.info["tracks"] = keep
        self.log.append(f"remove_tracks: {n}")
        return n

    def add_subtitles(self, srt: str, style: dict | None = None, y: float = -0.75) -> int:
        cues = parse_srt(Path(srt).read_text("utf-8-sig"))
        frag = Draft("frag", **self._canvas())
        track = frag.add_track("text", flag=1)
        st = style or {}
        stroke = st.get("stroke") or {"color": "#000000", "width": 0.08}
        for start, end, text in cues:
            frag.add_text(track, text, start, end - start, size=float(st.get("size", 6)),
                          color=st.get("color", "#FFFFFF"), font_path=st.get("font_path", ""),
                          stroke_color=stroke.get("color"), stroke_width=float(stroke.get("width", 0.08)),
                          transform={"y": y}, subtitle=True)
        self._merge(frag)
        self.log.append(f"add_subtitles: {len(cues)} cues")
        return len(cues)

    def shift(self, seconds: float, kinds: tuple[str, ...] = ("text",)) -> None:
        d = int(round(seconds * 1e6))
        for t in self.info["tracks"]:
            if t["type"] in kinds:
                for s in t["segments"]:
                    tr = s["target_timerange"]
                    tr["start"] = max(0, tr.get("start", 0) + d)
        self.log.append(f"shift {kinds} by {seconds}s")

    # ---------------- helpers ----------------
    def _canvas(self) -> dict:
        c = self.info.get("canvas_config", {})
        return {"width": c.get("width", 1920), "height": c.get("height", 1080), "fps": self.info.get("fps") or 30.0}

    def _track(self, index: int) -> dict:
        try:
            return self.info["tracks"][index]
        except IndexError:
            raise JyrError(f"no track #{index}; the draft has {len(self.info['tracks'])}") from None

    def _merge(self, frag: Draft) -> None:
        mats = self.info.setdefault("materials", {})
        for k, v in frag.materials.items():
            mats.setdefault(k, []).extend(copy.deepcopy(v))
        base = len(self.info["tracks"])
        for i, t in enumerate(frag.tracks):
            tj = t.to_json()
            for s in tj["segments"]:
                s["track_render_index"] = base + i
            self.info["tracks"].append(tj)
        self.info["duration"] = max(self.info.get("duration", 0), frag.duration)

    def ops(self, ops: list[dict]) -> None:
        for op in ops:
            kind = op.get("op")
            args = {k: v for k, v in op.items() if k != "op"}
            fn = {"replace_text": self.replace_text, "relink": self.relink, "track_volume": self.track_volume,
                  "remove_tracks": self.remove_tracks, "add_subtitles": self.add_subtitles,
                  "shift": self.shift}.get(kind)
            if fn is None:
                raise JyrError(f"unknown op {kind!r}")
            fn(**args)

    def save(self) -> Path:
        enc = crypto.encrypt_bytes(self.rt, dump(self.info).encode())
        for f in _info_files(self.work, self.info["id"]):
            atomic_write(f, enc)
        self.meta["tm_duration"] = self.info.get("duration", self.meta.get("tm_duration", 0))
        atomic_write(self.work / "draft_meta_info.json", crypto.encrypt_bytes(self.rt, dump(self.meta).encode()))
        (self.work / ".jyr.json").write_text(json.dumps({"name": self.work.name, "edited_from": str(self.src),
                                                         "ops": self.log}, ensure_ascii=False, indent=1))
        return self.work

    def publish(self, name: str) -> dict:
        self.save()
        return home.publish(self.rt, self.work, name)
