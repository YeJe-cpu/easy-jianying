"""Plan (JSON, seconds) -> Draft.

A plan is what an agent writes. It is deliberately forgiving: clips without
`start` follow the previous clip on the same track, clips without `duration`
run to the end of their source, and resources are referred to by the names
shown in JianYing's UI (转场「叠化」, 蒙版「圆形」, 动画「渐显」...).
"""

from __future__ import annotations

import json
from pathlib import Path

from .catalog import Catalog
from .draft import Draft, Track
from .media import probe
from .runtime import Runtime
from .util import JyrError, us

CANVAS_PRESETS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080),
                  "4:3": (1440, 1080), "3:4": (1080, 1440), "2.35:1": (1920, 817)}
MASK_SHAPES = {"circle": "圆形", "rectangle": "矩形", "line": "线性", "mirror": "镜面", "heart": "爱心", "star": "星形"}
ALIGN = {"left": 0, "center": 1, "right": 2}


class PlanError(JyrError):
    pass


def load(path: str | Path) -> dict:
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except json.JSONDecodeError as e:
        raise PlanError(f"plan is not valid JSON: {e}") from None


def _canvas(plan: dict) -> tuple[int, int, float]:
    c = plan.get("canvas", "16:9")
    if isinstance(c, str):
        if c not in CANVAS_PRESETS:
            raise PlanError(f"canvas preset {c!r} unknown; use {list(CANVAS_PRESETS)} or {{width,height,fps}}")
        w, h = CANVAS_PRESETS[c]
        return w, h, float(plan.get("fps", 30))
    return int(c.get("width", 1920)), int(c.get("height", 1080)), float(c.get("fps", plan.get("fps", 30)))


class Compiler:
    def __init__(self, rt: Runtime, catalog: Catalog | None = None):
        self.rt = rt
        self._catalog = catalog
        self.warnings: list[str] = []

    @property
    def catalog(self) -> Catalog:
        if self._catalog is None:
            self._catalog = Catalog()
        return self._catalog

    def compile(self, plan: dict) -> Draft:
        if not isinstance(plan.get("tracks"), list) or not plan["tracks"]:
            raise PlanError("plan needs a non-empty `tracks` list")
        w, h, fps = _canvas(plan)
        d = Draft(plan.get("name") or "jyr draft", w, h, fps,
                  timeline_version=self.rt.timeline_version or "189.0.0", app_version=self.rt.version)
        first_video = True
        for ti, tp in enumerate(plan["tracks"]):
            kind = tp.get("type")
            where = f"tracks[{ti}]"
            if kind not in ("video", "audio", "text", "effect", "filter", "sticker", "subtitle"):
                raise PlanError(f"{where}: type must be video/audio/text/subtitle/effect/filter/sticker")
            track = d.add_track("text" if kind == "subtitle" else kind, name=tp.get("name", ""),
                                flag=1 if kind == "subtitle" else 0)
            cursor = 0
            clips = tp.get("clips", [])
            if not clips:
                raise PlanError(f"{where}: no clips")
            segs = []
            for ci, cp in enumerate(clips):
                w2 = f"{where}.clips[{ci}]"
                try:
                    seg, end = self._clip(d, track, kind, cp, cursor)
                except JyrError as e:
                    raise PlanError(f"{w2}: {e}") from None
                segs.append((seg, cp, w2))
                cursor = end
            if kind == "video":
                self._check_main(track, first_video, tp, where)
                first_video = False
                self._transitions(d, segs)
        return d

    # --------------------------------------------------------------
    def _clip(self, d: Draft, track: Track, kind: str, cp: dict, cursor: int):
        start = us(cp["start"]) if "start" in cp else cursor
        if kind in ("video", "audio"):
            src = cp.get("src")
            if not src:
                raise JyrError("missing `src` (absolute path)")
            info = probe(src)
            speed = float(cp.get("speed", 1.0))
            src_in = us(cp.get("in", 0))
            if "duration" in cp:
                dur = us(cp["duration"])
            elif "out" in cp:
                dur = int(round((us(cp["out"]) - src_in) / speed))
            elif info.kind == "photo":
                dur = us(3)
            else:
                dur = int((info.duration_us - src_in) / speed)
            seg = d.add_media(track, src, start, dur, source_start=src_in, speed=speed,
                              volume=float(cp.get("volume", 1.0)), transform=cp.get("transform"),
                              reverse=bool(cp.get("reverse")))
            if cp.get("beats"):
                d.add_beats(seg, [us(b) for b in cp["beats"]])
            fade = cp.get("fade") or {}
            d.add_fade(seg, us(fade.get("in", 0)), us(fade.get("out", 0)))
            if kind == "video":
                if cp.get("mask"):
                    self._mask(d, seg, cp["mask"])
                for name in cp.get("effects", []) or []:
                    d.add_effect_on(seg, self.catalog.find("effect", name))
                self._anims(d, seg, cp.get("anim"), "video")
            self._keyframes(d, seg, cp.get("keyframes"))
            return seg, start + dur
        if kind in ("text", "subtitle"):
            dur = us(cp.get("duration", 2))
            st = cp.get("style", {})
            font_path = font_id = font_title = ""
            if st.get("font"):
                f = st["font"]
                if Path(f).is_absolute():
                    if not Path(f).exists():
                        raise JyrError(f"font file not found: {f}")
                    font_path = f
                else:
                    e = self.catalog.find("font", f)
                    font_path, font_id, font_title = e["path"], e.get("resource_id", ""), e["name"]
            stroke = st.get("stroke") or {}
            seg = d.add_text(track, str(cp.get("text", "")), start, dur, size=float(st.get("size", 8)),
                             color=st.get("color", "#FFFFFF"), font_path=font_path, font_id=font_id,
                             font_title=font_title, stroke_color=stroke.get("color"),
                             stroke_width=float(stroke.get("width", 0.08)), bold=bool(st.get("bold")),
                             italic=bool(st.get("italic")), align=ALIGN.get(st.get("align", "center"), 1),
                             background=st.get("background"), line_spacing=float(st.get("line_spacing", 0.02)),
                             letter_spacing=float(st.get("letter_spacing", 0)),
                             transform=cp.get("transform") or ({"y": -0.75} if kind == "subtitle" else None),
                             subtitle=kind == "subtitle", words=cp.get("words"))
            self._anims(d, seg, cp.get("anim"), "text")
            self._keyframes(d, seg, cp.get("keyframes"))
            return seg, start + dur
        dur = us(cp.get("duration", 3))
        if kind in ("effect", "filter"):
            seg = d.add_track_effect(track, self.catalog.find(kind, cp.get("name", "")), start, dur)
        else:
            seg = d.add_sticker(track, self.catalog.find("sticker", cp.get("name", "")), start, dur,
                                transform=cp.get("transform"))
            self._anims(d, seg, cp.get("anim"), "text")
            self._keyframes(d, seg, cp.get("keyframes"))
        return seg, start + dur

    def _mask(self, d: Draft, seg: dict, m: dict) -> None:
        shape = m.get("shape", "circle")
        name = MASK_SHAPES.get(shape, shape)
        pool = [e for e in self.catalog.list("mask") if e.get("available") and (e.get("shape") == shape or e["name"] == name)]
        res = pool[0] if pool else self.catalog.find("mask", name)
        d.add_mask(seg, res, width=m.get("width", 0.5), height=m.get("height", 0.5), x=m.get("x", 0.0),
                   y=m.get("y", 0.0), feather=m.get("feather", 0.0), rotation=m.get("rotation", 0.0),
                   invert=bool(m.get("invert")), round_corner=m.get("round_corner", 0.0))

    def _anims(self, d: Draft, seg: dict, anim: dict | None, target: str) -> None:
        for slot, spec in (anim or {}).items():
            if slot not in ("in", "out", "loop"):
                raise JyrError(f"anim slot {slot!r}: use in / out / loop")
            spec = {"name": spec} if isinstance(spec, str) else spec
            res = self.catalog.find("animation", spec["name"], slot=slot, target=target)
            d.add_animation(seg, res, slot, us(spec["duration"]) if "duration" in spec else None)

    def _keyframes(self, d: Draft, seg: dict, kf: dict | None) -> None:
        for prop, pts in (kf or {}).items():
            d.add_keyframes(seg, prop, [(us(t), float(v)) for t, v in pts])

    def _check_main(self, track: Track, is_main: bool, tp: dict, where: str) -> None:
        if not is_main or tp.get("allow_gaps"):
            return
        t = 0
        for s in track.segments:
            st = s["target_timerange"].get("start", 0)
            if abs(st - t) > 1000:
                self.warnings.append(f"{where}: main track has a gap/overlap at {t / 1e6:.3f}s; "
                                     "JianYing's magnetic main track may close it. Set allow_gaps to silence.")
                return
            t = st + s["target_timerange"]["duration"]

    def _transitions(self, d: Draft, segs: list) -> None:
        for i, (seg, cp, w) in enumerate(segs):
            tr = cp.get("transition")
            if not tr:
                continue
            tr = {"name": tr} if isinstance(tr, str) else tr
            if i == len(segs) - 1:
                raise PlanError(f"{w}: a transition goes between two clips; the last clip cannot have one")
            nxt = segs[i + 1][0]
            end = seg["target_timerange"].get("start", 0) + seg["target_timerange"]["duration"]
            if abs(nxt["target_timerange"].get("start", 0) - end) > 1000:
                raise PlanError(f"{w}: transition needs the next clip to start right where this one ends")
            res = self.catalog.find("transition", tr.get("name", "叠化"))
            dur = us(tr["duration"]) if "duration" in tr else (res.get("default_duration_us") or 500000)
            limit = min(seg["target_timerange"]["duration"], nxt["target_timerange"]["duration"]) // 2
            if dur > limit:
                raise PlanError(f"{w}: transition {dur / 1e6:.2f}s is longer than half the shorter clip")
            d.add_transition(seg, res, dur)
