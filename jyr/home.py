"""Put a built draft on JianYing's home screen (项目首页).

This is the only step that touches JianYing's own files. It refuses to run
while JianYing is open, backs up the index first, and only ever appends.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .runtime import CONFIG_DIR, Runtime, jianying_running
from .util import JyrError, atomic_write, dump, new_id, now_us
from .writer import read_meta

INDEX = "root_meta_info.json"


def backup_index(rt: Runtime) -> Path:
    src = rt.draft_root / INDEX
    dst_dir = CONFIG_DIR / "backups"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{INDEX}.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(src, dst)
    return dst


def unique_folder(rt: Runtime, name: str) -> Path:
    safe = name.replace("/", "-").strip() or "jyr-draft"
    cand = rt.draft_root / safe
    n = 2
    while cand.exists():
        cand = rt.draft_root / f"{safe}({n})"
        n += 1
    return cand


def publish(rt: Runtime, built: Path, name: str | None = None) -> dict:
    """Copy a built draft folder into JianYing's project root and register it."""
    built = Path(built)
    if not (built / "draft_info.json").is_file():
        raise JyrError(f"{built} is not a built draft folder")
    if jianying_running():
        raise JyrError("JianYing is running. Quit it completely (⌘Q) first — it rewrites the index on exit.")
    index_path = rt.draft_root / INDEX
    if not index_path.is_file():
        raise JyrError(f"{index_path} not found; open JianYing once so it creates its project folder")
    meta_jyr = json.loads((built / ".jyr.json").read_text()) if (built / ".jyr.json").exists() else {}
    target = unique_folder(rt, name or meta_jyr.get("name") or built.name)
    backup = backup_index(rt)
    shutil.copytree(built, target)
    try:
        _fix_paths(rt, target)
        meta = read_meta(rt, target)
        index = json.loads(index_path.read_text("utf-8"))
        entry = {
            "cloud_draft_cover": False, "cloud_draft_sync": False, "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "", "draft_cloud_template_id": "", "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "", "draft_cover": str(target / "draft_cover.jpg"),
            "draft_fold_path": str(target), "draft_id": meta["draft_id"], "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False, "draft_is_infinite_canvas_draft": False,
            "draft_is_invisible": False, "draft_is_pippit_draft": False, "draft_is_web_article_video": False,
            "draft_json_file": str(target / "draft_info.json"), "draft_name": target.name,
            "draft_new_version": "", "draft_root_path": str(rt.draft_root),
            "draft_timeline_materials_size": meta.get("draft_timeline_materials_size_", 0),
            "draft_type": "", "draft_web_article_video_enter_from": "", "pippit_avatar_url": "",
            "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
            "streaming_edit_draft_ready": True, "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0, "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1, "tm_draft_cloud_user_id": -1,
            "tm_draft_create": meta["tm_draft_create"], "tm_draft_modified": now_us(),
            "tm_draft_removed": 0, "tm_duration": meta["tm_duration"],
        }
        if any(e.get("draft_id") == entry["draft_id"] for e in index.get("all_draft_store", [])):
            raise JyrError("this draft id is already on the home screen")
        before = len(index.get("all_draft_store", []))
        index.setdefault("all_draft_store", []).insert(0, entry)
        if isinstance(index.get("draft_ids"), int):
            index["draft_ids"] += 1
        atomic_write(index_path, dump(index))
        after = json.loads(index_path.read_text("utf-8"))
        if len(after["all_draft_store"]) != before + 1:
            raise JyrError("index check failed after write")
    except BaseException:
        shutil.copy2(backup, index_path)
        shutil.rmtree(target, ignore_errors=True)
        raise
    return {"folder": str(target), "draft_id": meta["draft_id"], "index_backup": str(backup)}


def _fix_paths(rt: Runtime, folder: Path) -> None:
    """The meta file records its own folder; rewrite it for the final location."""
    from . import crypto
    meta = read_meta(rt, folder)
    meta["draft_id"] = new_id()  # each published copy is its own draft
    old = meta.get("draft_fold_path", "")
    meta["draft_fold_path"] = str(folder)
    meta["draft_root_path"] = str(folder.parent)
    meta["draft_name"] = folder.name
    raw = dump(meta)
    if old and old != str(folder):
        raw = raw.replace(json.dumps(old, ensure_ascii=False)[1:-1], json.dumps(str(folder), ensure_ascii=False)[1:-1])
    atomic_write(folder / "draft_meta_info.json", crypto.encrypt_bytes(rt, raw.encode()))
    # Packed media lives inside the draft; point materials at the new place.
    if old and old != str(folder):
        info_raw = crypto.decrypt_bytes(rt, (folder / "draft_info.json").read_bytes()).decode()
        o = json.dumps(old, ensure_ascii=False)[1:-1]
        if o in info_raw:
            enc = crypto.encrypt_bytes(rt, info_raw.replace(o, json.dumps(str(folder), ensure_ascii=False)[1:-1]).encode())
            tl = json.loads(info_raw)["id"]
            for p in (folder / "draft_info.json", folder / "draft_info.json.bak",
                      folder / "Timelines" / tl / "draft_info.json", folder / "Timelines" / tl / "draft_info.json.bak"):
                atomic_write(p, enc)
