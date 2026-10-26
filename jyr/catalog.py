"""A catalog of JianYing resources this machine already has.

Transitions, masks, effects, filters, text/video animations, stickers and
fonts are native resources: a draft only points at them by id and by a path
in JianYing's cache. Instead of shipping a fixed list, we scan the user's own
drafts and remember how JianYing itself recorded each resource. Anything the
user has applied once in the app (and is still cached) becomes usable here.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import crypto
from .runtime import CONFIG_DIR, Runtime
from .util import JyrError

CATALOG_PATH = CONFIG_DIR / "catalog.json"
FONT_EXT = {".ttf", ".otf", ".ttc"}
SYSTEM_FONT_DIRS = [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]

# material list in draft_info -> catalog kind
MATERIAL_KINDS = {
    "transitions": "transition",
    "common_mask": "mask",
    "video_effects": "effect",
    "audio_effects": "audio_effect",
    "stickers": "sticker",
}
# fields that belong to one use of a resource, not to the resource
VOLATILE = {"id", "request_id", "constant_material_id", "config", "duration", "value", "time_range"}


def _entry(kind: str, mat: dict, extra: dict | None = None) -> dict | None:
    rid = str(mat.get("resource_id") or mat.get("effect_id") or mat.get("sticker_id") or "")
    name = mat.get("name") or ""
    if not rid or not name:
        return None
    template = {k: v for k, v in mat.items() if k not in VOLATILE}
    e = {"kind": kind, "name": name, "resource_id": rid, "path": mat.get("path", ""),
         "category": mat.get("category_name", ""), "template": template, "seen": 1}
    if extra:
        e.update(extra)
    return e


def _harvest(draft: dict, out: dict[tuple, dict]) -> None:
    mats = draft.get("materials", {})

    def add(e):
        if not e:
            return
        key = (e["kind"], e["resource_id"], e.get("slot", ""))
        if key in out:
            out[key]["seen"] += 1
        else:
            out[key] = e

    for list_name, kind in MATERIAL_KINDS.items():
        for m in mats.get(list_name, []) or []:
            extra = {}
            if kind == "mask":
                extra["shape"] = m.get("resource_type", "")
            if kind == "transition":
                extra["default_duration_us"] = m.get("duration", 0)
            add(_entry(kind, m, extra))
    for m in mats.get("effects", []) or []:
        t = m.get("type", "")
        if t == "filter":
            add(_entry("filter", m))
        elif t in ("text_effect", "text_shape"):
            add(_entry("text_effect" if t == "text_effect" else "text_bubble", m))
    for m in mats.get("material_animations", []) or []:
        for a in m.get("animations", []) or []:
            slot = a.get("type", "")  # in / out / loop / caption
            target = "text" if a.get("material_type") == "sticker" else a.get("material_type", "")
            if slot not in ("in", "out", "loop") or not a.get("name"):
                continue
            add(_entry("animation", a, {"slot": slot, "target": target,
                                        "default_duration_us": a.get("duration", 0)}))
    for m in mats.get("texts", []) or []:
        try:
            content = json.loads(m.get("content") or "{}")
        except json.JSONDecodeError:
            continue
        for st in content.get("styles", []):
            f = st.get("font") or {}
            p = f.get("path", "")
            if not p:
                continue
            title = next((x.get("title") for x in m.get("fonts", []) if x.get("path") == p and x.get("title")), "")
            role = "subtitle" if m.get("type") == "subtitle" or m.get("recognize_text") else "title"
            e = {"kind": "font", "name": title or Path(p).stem, "resource_id": str(f.get("id") or ""),
                 "path": p, "category": "剪映字体" if f.get("id") else "内置字体", "template": {}, "seen": 1,
                 "slot": p, "roles": {role: 1}}
            key = ("font", e["resource_id"], p)
            if key in out:
                out[key]["roles"][role] = out[key]["roles"].get(role, 0) + 1
            add(e)


def _local_fonts(rt: Runtime) -> list[dict]:
    fonts = []
    builtin = rt.app_path / "Contents/Resources/Font"
    for base, cat in [(builtin, "内置字体")] + [(d, "系统字体") for d in SYSTEM_FONT_DIRS]:
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.suffix.lower() in FONT_EXT:
                fonts.append({"kind": "font", "name": p.stem, "resource_id": "", "path": str(p),
                              "category": cat, "template": {}, "seen": 0, "slot": str(p)})
    return fonts


def scan(rt: Runtime, draft_root: Path | None = None) -> dict:
    root = Path(draft_root or rt.draft_root)
    files = sorted(root.glob("*/draft_info.json"))
    found: dict[tuple, dict] = {}
    with tempfile.TemporaryDirectory(prefix="jyr-scan-") as tmp:
        decoded = crypto.decrypt_many(rt, files, Path(tmp))
        bad = 0
        for src, dst in decoded.items():
            if dst is None:
                bad += 1
                continue
            try:
                _harvest(json.loads(dst.read_text("utf-8")), found)
            except (json.JSONDecodeError, UnicodeDecodeError):
                bad += 1
    entries = list(found.values())
    seen_paths = {e["path"] for e in entries if e["kind"] == "font"}
    entries += [f for f in _local_fonts(rt) if f["path"] not in seen_paths]
    for e in entries:
        e["available"] = bool(e["path"]) and Path(e["path"]).exists()
        e.pop("slot", None) if e["kind"] == "font" else None
    entries.sort(key=lambda e: (e["kind"], -e["seen"], e["name"]))
    cat = {"app_version": rt.version, "drafts_scanned": len(files), "drafts_unreadable": bad, "entries": entries}
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(cat, ensure_ascii=False, indent=1))
    return cat


def load() -> dict:
    if not CATALOG_PATH.is_file():
        raise JyrError("no resource catalog yet; run `jyr catalog scan` once")
    return json.loads(CATALOG_PATH.read_text())


class Catalog:
    def __init__(self, data: dict | None = None):
        self.data = data if data is not None else load()
        self.entries = self.data["entries"]

    def find(self, kind: str, name: str, slot: str | None = None, target: str | None = None) -> dict:
        pool = [e for e in self.entries if e["kind"] == kind
                and (slot is None or e.get("slot") == slot)
                and (target is None or e.get("target") in (target, None))]
        if str(name).startswith("auto"):
            return self.auto(kind, str(name), pool)
        if not pool:
            raise JyrError(f"no {kind} resources in the catalog; apply one once in JianYing, then `jyr catalog scan`")
        key = str(name).strip()
        for test in (lambda e: e["resource_id"] == key, lambda e: e["name"] == key,
                     lambda e: e["name"].lower() == key.lower(), lambda e: key.lower() in e["name"].lower()):
            hits = [e for e in pool if test(e)]
            if hits:
                usable = [e for e in hits if e.get("available")]
                if not usable:
                    raise JyrError(f"{kind} {name!r} is known but not in JianYing's cache any more; "
                                   "use it once in the app to download it, then `jyr catalog scan`")
                return usable[0]
        near = ", ".join(e["name"] for e in pool if e.get("available"))[:400]
        raise JyrError(f"{kind} {name!r} not found. Available: {near}")

    def auto(self, kind: str, spec: str, pool: list[dict]) -> dict:
        """'auto' = the user's most-used available one; 'auto:<role>' for fonts."""
        if kind == "font":
            from .recipes.fonts import pick
            return pick(self, spec.split(":", 1)[1] if ":" in spec else "title")
        usable = sorted((e for e in pool if e.get("available")), key=lambda e: -e.get("seen", 0))
        if not usable:
            raise JyrError(f"no available {kind} for 'auto'")
        return usable[0]

    def list(self, kind: str | None = None) -> list[dict]:
        return [e for e in self.entries if kind is None or e["kind"] == kind]
