"""Write a Draft to a folder laid out the way JianYing lays out its own."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import crypto
from .draft import Draft
from .runtime import Runtime
from .util import JyrError, atomic_write, dump, new_id, now_us

ENCRYPTED = ("draft_info.json", "draft_meta_info.json")


def _meta(draft: Draft, folder: Path, draft_id: str, created: int) -> dict:
    mats = []
    for m in draft.local_media:
        info = m["info"]
        kind = {"video": "video", "photo": "photo", "gif": "photo", "audio": "music"}[info.kind]
        mats.append({"ai_group_type": "", "create_time": created // 1_000_000, "duration": info.duration_us if kind != "photo" else 5_000_000,
                     "enter_from": 0, "extra_info": Path(info.path).name, "file_Path": info.path,
                     "height": info.height, "width": info.width, "id": m["id"],
                     "import_time": created // 1_000_000, "import_time_ms": created, "item_source": 1,
                     "material_color_tag": "", "md5": "", "metetype": kind,
                     "roughcut_time_range": {"duration": info.duration_us, "start": 0} if kind != "photo" else {"duration": -1, "start": -1},
                     "sub_time_range": {"duration": -1, "start": -1}, "type": 0})
    return {
        "cloud_draft_cover": False, "cloud_draft_sync": False, "cloud_package_completed_time": "",
        "draft_cloud_capcut_purchase_info": "", "draft_cloud_last_action_download": False,
        "draft_cloud_package_type": "", "draft_cloud_purchase_info": "", "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "", "draft_cloud_videocut_purchase_info": "",
        "draft_cover": "draft_cover.jpg", "draft_deeplink_url": "",
        "draft_enterprise_info": {"draft_enterprise_extra": "", "draft_enterprise_id": "",
                                  "draft_enterprise_name": "", "enterprise_material": []},
        "draft_fold_path": str(folder), "draft_id": draft_id,
        "draft_is_ae_produce": False, "draft_is_ai_packaging_used": False, "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False, "draft_is_article_video_draft": False, "draft_is_cloud_temp_draft": False,
        "draft_is_from_deeplink": "false", "draft_is_infinite_canvas_draft": False, "draft_is_invisible": False,
        "draft_is_pippit_draft": False, "draft_is_web_article_video": False,
        "draft_materials": [{"type": t, "value": mats if t == 0 else []} for t in (0, 1, 2, 3, 6, 7, 8)],
        "draft_materials_copied_info": [], "draft_name": folder.name, "draft_need_rename_folder": False,
        "draft_new_version": "", "draft_removable_storage_device": "", "draft_root_path": str(folder.parent),
        "draft_segment_extra_info": [], "draft_timeline_materials_size_": sum(
            Path(m["info"].path).stat().st_size for m in draft.local_media),
        "draft_type": "", "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "", "pippit_extra_info": "", "pippit_id": "", "pippit_user_name": "",
        "tm_draft_cloud_completed": "", "tm_draft_cloud_entry_id": -1, "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1, "tm_draft_cloud_space_id": -1, "tm_draft_cloud_user_id": -1,
        "tm_draft_create": created, "tm_draft_modified": created, "tm_draft_removed": 0,
        "tm_duration": draft.duration,
    }


def _cover(draft: Draft, dst: Path) -> None:
    """First frame of the first visual clip, small; JianYing redraws it on save."""
    for t in draft.tracks:
        if t.kind != "video":
            continue
        for seg in t.segments:
            mat = next((m for m in draft.materials.get("videos", []) if m["id"] == seg["material_id"]), None)
            if not mat:
                continue
            ss = seg.get("source_timerange", {}).get("start", 0) / 1e6
            args = ["ffmpeg", "-v", "error", "-y"] + (["-ss", f"{ss:.3f}"] if mat["type"] == "video" else []) + \
                   ["-i", mat["path"], "-frames:v", "1", "-vf", "scale=480:-2", str(dst)]
            if subprocess.run(args, capture_output=True).returncode == 0:
                return
    return


def pack_media(draft: Draft, folder: Path) -> None:
    """Copy every source file into <draft>/Resources/media so the draft can travel."""
    media_dir = folder / "Resources" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    mapping = {}
    for m in draft.local_media:
        src = Path(m["info"].path)
        dst = media_dir / f"{m['id'][:8]}-{src.name}"
        if not dst.exists():
            shutil.copy2(src, dst)
        mapping[str(src)] = str(dst)
    for kind in ("videos", "audios"):
        for mat in draft.materials.get(kind, []):
            if mat.get("path") in mapping:
                mat["path"] = mapping[mat["path"]]
    for m in draft.local_media:
        m["file_path_override"] = mapping[m["info"].path]


def write(rt: Runtime, draft: Draft, folder: Path, pack: bool = False, overwrite: bool = False) -> Path:
    folder = Path(folder)
    if folder.exists():
        if not overwrite:
            raise JyrError(f"{folder} already exists")
        if (folder / "draft_meta_info.json").exists() and folder.parent == rt.draft_root:
            raise JyrError("refusing to overwrite a draft inside JianYing's project folder")
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    if pack:
        pack_media(draft, folder)
    created = now_us()
    draft_id = new_id()
    info = draft.to_json(platform={"os": "mac", "app_id": 3704, "app_version": rt.version, "app_source": "lv"})
    info_bytes = dump(info).encode()
    enc_info = crypto.encrypt_bytes(rt, info_bytes)

    meta = _meta(draft, folder, draft_id, created)
    if pack:
        for v in meta["draft_materials"][0]["value"]:
            for m in draft.local_media:
                if m["id"] == v["id"] and m.get("file_path_override"):
                    v["file_Path"] = m["file_path_override"]
    enc_meta = crypto.encrypt_bytes(rt, dump(meta).encode())

    tl_dir = folder / "Timelines" / draft.id
    for base in (folder, tl_dir):
        atomic_write(base / "draft_info.json", enc_info)
        atomic_write(base / "draft_info.json.bak", enc_info)
    project = {"config": {"color_space": -1, "hdr_vivid": False, "mixed_track_mode_on": False,
                          "render_index_track_mode_on": False, "use_float_render": False},
               "create_time": created, "id": new_id(), "main_timeline_id": draft.id,
               "timelines": [{"id": draft.id, "name": "时间线01", "create_time": created,
                              "update_time": created, "is_marked_delete": False}],
               "update_time": created, "version": 0}
    atomic_write(folder / "Timelines/project.json", dump(project))
    atomic_write(folder / "Timelines/project.json.bak", dump(project))
    atomic_write(folder / "draft_meta_info.json", enc_meta)
    atomic_write(folder / "timeline_layout.json", dump(
        {"activeTimeline": draft.id, "dockItems": [{"dockIndex": 0, "ratio": 1, "timelineIds": [draft.id],
                                                    "timelineNames": ["时间线01"]}], "layoutOrientation": 1}))
    store = {"draft_materials": [], "draft_virtual_store": [
        {"type": 0, "value": [{"creation_time": 0, "display_name": "", "filter_type": 0, "id": "",
                               "import_time": 0, "import_time_us": 0, "material_color_tag": "",
                               "sort_sub_type": 0, "sort_type": 0, "subdraft_filter_type": 0}]},
        {"type": 1, "value": [{"child_id": m["id"], "parent_id": ""} for m in draft.local_media]},
        {"type": 2, "value": []}]}
    atomic_write(folder / "draft_virtual_store.json", dump(store))
    atomic_write(folder / "key_value.json", "{}")
    sec = created // 1_000_000
    atomic_write(folder / "draft_settings",
                 f"[General]\ncloud_last_modify_platform=mac\ndraft_create_time={sec}\ndraft_last_edit_time={sec}\n")
    (folder / "Resources").mkdir(exist_ok=True)
    _cover(draft, folder / "draft_cover.jpg")
    if (folder / "draft_cover.jpg").exists():
        shutil.copy2(folder / "draft_cover.jpg", tl_dir / "draft_cover.jpg")
    (folder / ".jyr.json").write_text(json.dumps(
        {"draft_id": draft_id, "timeline_id": draft.id, "name": draft.name, "created_us": created,
         "duration_us": draft.duration, "app_version": rt.version}, ensure_ascii=False, indent=1))
    return folder


def read_info(rt: Runtime, folder: Path) -> dict:
    return json.loads(crypto.decrypt_bytes(rt, (Path(folder) / "draft_info.json").read_bytes()))


def read_meta(rt: Runtime, folder: Path) -> dict:
    return json.loads(crypto.decrypt_bytes(rt, (Path(folder) / "draft_meta_info.json").read_bytes()))
