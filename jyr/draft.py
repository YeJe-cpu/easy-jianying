"""Build the draft_info.json timeline.

`Draft` is a thin, explicit builder: every method appends exactly the
materials and segment fields that JianYing itself writes for that feature
(observed from drafts the app saved). Times are microseconds here; the plan
layer converts from seconds.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .media import MediaInfo, probe
from .runtime import DRAFT_FORMAT_VERSION
from .util import JyrError, hex_to_rgb, new_id

TRACK_TYPES = {"video", "audio", "text", "effect", "filter", "sticker"}
# Rough layering JianYing uses for render_index by track kind.
RENDER_BASE = {"video": 0, "sticker": 12000, "text": 14000, "effect": 11000, "filter": 11000, "audio": 0}

KEYFRAME_PROPS = {
    "x": "KFTypePositionX", "y": "KFTypePositionY", "scale": "KFTypeScaleX",
    "scale_x": "KFTypeScaleX", "scale_y": "KFTypeScaleY", "rotation": "KFTypeRotation",
    "opacity": "KFTypeAlpha", "volume": "KFTypeVolume",
}


@dataclass
class Track:
    kind: str
    id: str = field(default_factory=new_id)
    name: str = ""
    segments: list = field(default_factory=list)
    flag: int = 0

    def to_json(self) -> dict:
        d = {"id": self.id, "type": self.kind, "segments": self.segments}
        if self.name:
            d["name"] = self.name
        else:
            d["is_default_name"] = True
        if self.flag:
            d["flag"] = self.flag
        return d

    @property
    def end_us(self) -> int:
        return max((s["target_timerange"].get("start", 0) + s["target_timerange"]["duration"]
                    for s in self.segments), default=0)


class Draft:
    def __init__(self, name: str, width: int = 1920, height: int = 1080, fps: float = 30.0,
                 timeline_version: str = "189.0.0", app_version: str = "11.6.0"):
        if width <= 0 or height <= 0:
            raise JyrError("canvas width/height must be positive")
        self.name = name
        self.width, self.height, self.fps = int(width), int(height), float(fps)
        self.timeline_version = timeline_version
        self.app_version = app_version
        self.id = new_id()
        self.tracks: list[Track] = []
        self.materials: dict[str, list] = {}
        self.media: dict[str, dict] = {}  # path -> material (videos/audios reuse)
        self.local_media: list[dict] = []  # for draft_meta_info.draft_materials

    # ---------- bookkeeping ----------
    def _mat(self, kind: str, obj: dict) -> str:
        obj.setdefault("id", new_id())
        self.materials.setdefault(kind, []).append(obj)
        return obj["id"]

    def add_track(self, kind: str, name: str = "", **kw) -> Track:
        if kind not in TRACK_TYPES:
            raise JyrError(f"unknown track kind {kind!r}")
        t = Track(kind if kind != "filter" else "filter", name=name, **kw)
        self.tracks.append(t)
        return t

    def _track_index(self, track: Track) -> int:
        same = [t for t in self.tracks if t.kind == track.kind]
        return same.index(track)

    def _base_segment(self, track: Track, start: int, duration: int) -> dict:
        idx = self._track_index(track)
        seg = {
            "id": new_id(),
            "target_timerange": {"start": int(start), "duration": int(duration)},
            "render_timerange": {},
            "material_id": "",
            "extra_material_refs": [],
            "render_index": RENDER_BASE[track.kind] + idx,
            "track_render_index": self.tracks.index(track),
            "enable_lut": False, "enable_adjust": False, "enable_hsl": False,
            "responsive_layout": {}, "enable_adjust_mask": False,
            "source": "segmentsourcenormal",
        }
        if not start:
            seg["target_timerange"].pop("start")
        return seg

    @staticmethod
    def _clip(transform: dict | None) -> dict:
        t = transform or {}
        scale = t.get("scale", 1.0)
        clip = {
            "scale": {"x": float(t.get("scale_x", scale)), "y": float(t.get("scale_y", scale))},
            "transform": {"x": float(t.get("x", 0.0)), "y": float(t.get("y", 0.0))},
            "flip": {},
        }
        if t.get("rotation"):
            clip["rotation"] = float(t["rotation"])
        if "opacity" in t and t["opacity"] != 1:
            clip["alpha"] = float(t["opacity"])
        if t.get("flip_h") or t.get("flip_v"):
            clip["flip"] = {"horizontal": bool(t.get("flip_h")), "vertical": bool(t.get("flip_v"))}
        return clip

    def _media_material(self, info: MediaInfo) -> dict:
        # JianYing keeps one material per segment, even for the same file.
        known = self.media.get(info.path)
        local_id = known["local_material_id"] if known else new_id().lower()
        uid = hashlib.md5(info.path.encode()).hexdigest()
        name = Path(info.path).name
        if info.kind == "audio":
            mat = {"type": "extract_music", "name": name, "duration": info.duration_us, "path": info.path,
                   "category_name": "local", "music_id": local_id, "local_material_id": local_id,
                   "unique_id": uid, "similiar_music_info": {}, "tts_benefit_info": {"benefit_type": "none"}}
            self._mat("audios", mat)
        else:
            mat = {"unique_id": uid, "type": info.kind, "duration": info.duration_us, "path": info.path,
                   "width": info.width, "height": info.height, "category_name": "local",
                   "material_id": "", "material_name": name, "crop": {}, "stable": {"time_range": {}},
                   "matting": {"path": ""}, "check_flag": 62978047, "local_material_id": local_id,
                   "video_algorithm": {"path": "", "story_video_modify_video_config": {}},
                   "beauty_face_auto_preset": {},
                   "video_mask_stroke": {"resource_id": "", "path": "", "type": ""},
                   "video_mask_shadow": {"resource_id": "", "path": ""}}
            if info.kind == "photo" or not info.has_audio:
                mat["has_audio"] = False
            self._mat("videos", mat)
        if not known:
            self.media[info.path] = mat
            self.local_media.append({"id": local_id, "info": info})
        return mat

    # ---------- media segments ----------
    def add_media(self, track: Track, path: str, start: int, duration: int, source_start: int = 0,
                  speed: float = 1.0, volume: float = 1.0, transform: dict | None = None,
                  reverse: bool = False) -> dict:
        info = probe(path)
        if track.kind == "video" and info.kind == "audio":
            raise JyrError(f"{path} has no picture; put it on an audio track")
        if track.kind == "audio" and info.kind == "photo":
            raise JyrError(f"{path} is an image; put it on a video track")
        if not 0.1 <= speed <= 100:
            raise JyrError(f"speed {speed} out of range 0.1–100")
        if duration <= 0:
            raise JyrError(f"{Path(path).name}: duration must be > 0")
        src_dur = int(round(duration * speed))
        if info.kind != "photo" and source_start + src_dur > info.duration_us + 1000:
            raise JyrError(f"{Path(path).name}: needs {(source_start + src_dur) / 1e6:.3f}s of source but "
                           f"the file is {info.duration_us / 1e6:.3f}s")
        src_dur = min(src_dur, info.duration_us - source_start) if info.kind != "photo" else src_dur
        mat = self._media_material(info)
        seg = self._base_segment(track, start, duration)
        seg["material_id"] = mat["id"]
        seg["source_timerange"] = {"start": int(source_start), "duration": int(src_dur)}
        if not source_start:
            seg["source_timerange"].pop("start")
        if speed != 1:
            seg["speed"] = float(speed)
        if volume != 1:
            seg["volume"] = float(volume)
            seg["last_nonzero_volume"] = float(volume) if volume else 1.0
        if reverse:
            seg["reverse"] = True
        refs = []
        speed_mat = {"type": "speed"}
        if speed != 1:
            speed_mat.update({"speed": float(speed), "mode": 0, "curve_speed": None})
        refs.append(self._mat("speeds", speed_mat))
        refs.append(self._mat("placeholder_infos", {"type": "placeholder_info", "meta_type": "none"}))
        if track.kind == "video":
            refs.append(self._mat("canvases", {"type": "canvas_color"}))
        refs.append(self._mat("sound_channel_mappings", {"type": "none"}))
        if track.kind == "video":
            refs.append(self._mat("material_colors", {}))
        refs.append(self._mat("vocal_separations", {"type": "vocal_separation"}))
        seg["extra_material_refs"] = refs
        if track.kind == "video":
            seg["clip"] = self._clip(transform)
            seg["uniform_scale"] = {}
            seg["hdr_settings"] = {"mode": 1}
            for k in ("enable_lut", "enable_adjust"):
                seg.pop(k)
        track.segments.append(seg)
        return seg

    # ---------- decorations on media segments ----------
    def add_fade(self, seg: dict, fade_in: int = 0, fade_out: int = 0) -> None:
        if not (fade_in or fade_out):
            return
        m = {"type": "audio_fade"}
        if fade_in:
            m["fade_in_duration"] = int(fade_in)
        if fade_out:
            m["fade_out_duration"] = int(fade_out)
        fid = self._mat("audio_fades", m)
        refs = seg["extra_material_refs"]
        kinds = {x["id"]: k for k, v in self.materials.items() for x in v}
        pos = next((i + 1 for i, r in enumerate(refs) if kinds.get(r) == "placeholder_infos"), len(refs))
        refs.insert(pos, fid)
        # For video clips JianYing also keeps a copy on the (per-segment) material.
        mat = next((v for v in self.materials.get("videos", []) if v["id"] == seg["material_id"]), None)
        if mat is not None:
            mat["audio_fade"] = dict(m)

    def frames_us(self, n: int) -> int:
        return int(n * 1_000_000 / self.fps)

    def snap_even_frames(self, duration: int) -> int:
        n = int(duration * self.fps / 1_000_000 + 1e-6)
        n -= n % 2
        return self.frames_us(max(n, 2))

    def add_transition(self, seg: dict, res: dict, duration: int) -> None:
        duration = self.snap_even_frames(duration)
        m = copy.deepcopy(res["template"])
        m.update({"type": "transition", "duration": int(duration)})
        m.setdefault("is_overlap", True)
        seg["extra_material_refs"].append(self._mat("transitions", m))

    def add_mask(self, seg: dict, res: dict, width: float = 0.5, height: float = 0.5, x: float = 0.0,
                 y: float = 0.0, feather: float = 0.0, rotation: float = 0.0, invert: bool = False,
                 round_corner: float = 0.0) -> None:
        m = copy.deepcopy(res["template"])
        m.update({"type": "mask", "category": "video", "constant_material_id": new_id(),
                  "config": {"width": float(width), "height": float(height), "centerX": float(x),
                             "centerY": float(y), "feather": float(feather), "rotation": float(rotation),
                             "invert": bool(invert), "roundCorner": float(round_corner),
                             "expansion": 0.0, "aspectRatio": 1.0}})
        seg["extra_material_refs"].append(self._mat("common_mask", m))
        seg["enable_video_mask"] = True

    def add_animation(self, seg: dict, res: dict, slot: str, duration: int | None = None) -> None:
        """In / out / loop animation on a text or video segment."""
        anim = copy.deepcopy(res["template"])
        anim.update({"type": slot, "duration": int(duration or res.get("default_duration_us") or 500000)})
        anim["id"] = res["resource_id"]
        group = None
        for ref in seg["extra_material_refs"]:
            for m in self.materials.get("material_animations", []):
                if m["id"] == ref:
                    group = m
        if group is None:
            group = {"type": "sticker_animation", "animations": []}
            seg["extra_material_refs"].insert(0, self._mat("material_animations", group))
        group["animations"] = [a for a in group["animations"] if a.get("type") != slot] + [anim]

    def add_keyframes(self, seg: dict, prop: str, points: list[tuple[int, float]]) -> None:
        if prop not in KEYFRAME_PROPS:
            raise JyrError(f"keyframe property {prop!r} not supported; use one of {sorted(KEYFRAME_PROPS)}")
        dur = seg["target_timerange"]["duration"]
        last = -1
        for t, _ in points:
            if t <= last or t < 0 or t > dur:
                raise JyrError(f"keyframes for {prop} must be increasing and within the clip (0–{dur / 1e6:.3f}s)")
            last = t
        kfs = seg.setdefault("common_keyframes", [])
        kfs.append({"id": new_id(), "material_id": "", "property_type": KEYFRAME_PROPS[prop],
                    "keyframe_list": [{"id": new_id(), "time_offset": int(t),
                                       "left_control": {"x": 0.0, "y": 0.0}, "right_control": {"x": 0.0, "y": 0.0},
                                       "values": [float(v)], "curveType": "Line", "graphID": ""}
                                      for t, v in points]})
        if prop == "scale":
            kfs.append({**copy.deepcopy(kfs[-1]), "id": new_id(), "property_type": "KFTypeScaleY"})
            for k in kfs[-1]["keyframe_list"]:
                k["id"] = new_id()

    def add_effect_on(self, seg: dict, res: dict) -> None:
        """Attach a video effect to a single clip (instead of an effect track)."""
        m = copy.deepcopy(res["template"])
        m.update({"type": "video_effect", "value": 1.0, "apply_target_type": 0})
        seg["extra_material_refs"].append(self._mat("video_effects", m))

    # ---------- text ----------
    def add_text(self, track: Track, text: str, start: int, duration: int, size: float = 8.0,
                 color: str = "#FFFFFF", font_path: str = "", font_id: str = "", font_title: str = "",
                 stroke_color: str | None = None, stroke_width: float = 0.08, bold: bool = False,
                 italic: bool = False, align: int = 1, background: str | None = None,
                 line_spacing: float = 0.02, letter_spacing: float = 0.0, transform: dict | None = None,
                 subtitle: bool = False, words: dict | None = None) -> dict:
        if not text:
            raise JyrError("text clip needs non-empty text")
        style = {"fill": {"alpha": 1.0, "content": {"render_type": "solid",
                                                   "solid": {"alpha": 1.0, "color": hex_to_rgb(color)}}},
                 "range": [0, len(text)], "size": float(size)}
        if font_path:
            style["font"] = {"id": font_id, "path": font_path}
        if bold:
            style["bold"] = True
        if italic:
            style["italic"] = True
        if stroke_color:
            style["strokes"] = [{"alpha": 1.0, "content": {"render_type": "solid",
                                                         "solid": {"alpha": 1.0, "color": hex_to_rgb(stroke_color)}},
                                 "width": float(stroke_width)}]
        content = json.dumps({"styles": [style], "text": text}, ensure_ascii=False)
        mat = {"type": "subtitle" if subtitle else "text", "content": content,
               "words": words or {}, "current_words": {}, "combo_info": {},
               "caption_template_info": {"resource_id": "", "path": ""},
               "layer_weight": 1, "line_spacing": float(line_spacing), "letter_spacing": float(letter_spacing),
               "text_color": color.upper(), "font_size": float(size), "alignment": int(align),
               "initial_scale": 1.0, "check_flag": 7 | (8 if stroke_color else 0) | (16 if background else 0),
               "lyrics_template": {"resource_id": "", "path": ""}, "force_apply_line_max_width": True}
        if subtitle:
            mat["base_content"] = content
            mat["recognize_text"] = text
            mat["add_type"] = 1
        if font_path:
            mat["font_path"] = font_path
            if font_id:
                mat["font_resource_id"] = font_id
                mat["font_source_platform"] = 1
                mat["fonts"] = [{"id": new_id(), "resource_id": font_id, "source_platform": 1, "path": font_path,
                                 "effect_id": font_id, "title": font_title or Path(font_path).stem}]
        if stroke_color:
            mat["border_color"] = stroke_color.upper()
            mat["border_width"] = float(stroke_width)
        if background:
            mat["background_color"] = background.upper()
            mat["background_alpha"] = 1.0
            mat["background_style"] = 1
        mid = self._mat("texts", mat)
        seg = self._base_segment(track, start, duration)
        seg["material_id"] = mid
        seg["clip"] = self._clip(transform)
        seg["uniform_scale"] = {}
        track.segments.append(seg)
        return seg

    # ---------- effect / filter tracks ----------
    def add_track_effect(self, track: Track, res: dict, start: int, duration: int) -> dict:
        m = copy.deepcopy(res["template"])
        if track.kind == "filter":
            m.update({"type": "filter", "value": 1.0})
            mid = self._mat("effects", m)
        else:
            m.update({"type": "video_effect", "value": 1.0, "apply_target_type": 2})
            mid = self._mat("video_effects", m)
        seg = self._base_segment(track, start, duration)
        seg["material_id"] = mid
        track.segments.append(seg)
        return seg

    def add_sticker(self, track: Track, res: dict, start: int, duration: int, transform: dict | None = None) -> dict:
        m = copy.deepcopy(res["template"])
        m["type"] = "sticker"
        mid = self._mat("stickers", m)
        seg = self._base_segment(track, start, duration)
        seg["material_id"] = mid
        seg["clip"] = self._clip(transform)
        seg["uniform_scale"] = {}
        track.segments.append(seg)
        return seg

    # ---------- output ----------
    @property
    def duration(self) -> int:
        return max((t.end_us for t in self.tracks), default=0)

    def to_json(self, platform: dict | None = None) -> dict:
        plat = platform or {"os": "mac", "app_id": 3704, "app_version": self.app_version, "app_source": "lv"}
        return {
            "id": self.id,
            "version": DRAFT_FORMAT_VERSION,
            "new_version": self.timeline_version,
            "name": "",
            "duration": self.duration,
            "fps": self.fps,
            "color_space": 0,
            "config": {},
            "canvas_config": {"width": self.width, "height": self.height, "ratio": "original"},
            "tracks": [t.to_json() for t in self.tracks],
            "materials": self.materials,
            "keyframes": {},
            "platform": plat,
            "last_modified_platform": plat,
            "render_index_track_mode_on": True,
            "path": "",
            "uneven_animation_template_info": {},
            "smart_ads_info": {},
            "function_assistant_info": {"fps": {}},
        }
