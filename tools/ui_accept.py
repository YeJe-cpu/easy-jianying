"""Acceptance test in the real JianYing app, with nobody at the keyboard.

publish a built draft -> launch JianYing -> open the draft from the home
screen -> let JianYing load and re-save it -> quit -> decrypt what JianYing
saved and diff it against what we wrote.

JianYing re-serialises a draft when it opens it, so "it saved back the same
tracks, timings and materials" is strong evidence it parsed everything.

Needs Accessibility permission for the app running this script.
usage: python3 tools/ui_accept.py BUILD_DIR [--name NAME] [--keep-open]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jyr import crypto, home, runtime  # noqa: E402
from jyr.ui import ax_names, launch, open_draft, quit_app  # noqa: E402


def summary(info: dict) -> dict:
    mats = {k: len(v) for k, v in info["materials"].items() if isinstance(v, list) and v}
    tracks = [[t["type"], [(s["target_timerange"].get("start", 0), s["target_timerange"]["duration"],
                            s.get("speed", 1.0)) for s in t["segments"]]] for t in info["tracks"]]
    kf = sum(len(s.get("common_keyframes", [])) for t in info["tracks"] for s in t["segments"])
    return {"version": info.get("new_version"), "duration": info.get("duration"), "materials": mats,
            "tracks": tracks, "keyframe_props": kf}


# Materials JianYing adds on its own when it opens a draft; not a loss.
APP_ADDS = {"loudnesses", "beats", "time_marks", "material_animations"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("build", nargs="?", help="built draft folder to publish and test")
    ap.add_argument("--name")
    ap.add_argument("--existing", help="test a draft already on the home screen (e.g. one made by `jyr edit`)")
    a = ap.parse_args()
    rt = runtime.detect()
    if runtime.jianying_running():
        print("quit JianYing first", file=sys.stderr)
        return 2
    if a.existing:
        from jyr import reader
        folder = reader.resolve(rt, a.existing)
    else:
        built = Path(a.build).resolve()
        name = a.name or f"jyr验收-{built.name}-{time.strftime('%H%M%S')}"
        folder = Path(home.publish(rt, built, name)["folder"])
    before = json.loads(crypto.decrypt_bytes(rt, (folder / "draft_info.json").read_bytes()))
    report = {"draft": folder.name, "steps": {}}

    launch(rt)
    report["steps"]["opened_in_editor"] = open_draft(rt, folder.name)
    report["steps"]["on_home_screen"] = True
    names = ax_names()
    report["editor_texts"] = [n.split(":", 1)[1] for n in names if n.startswith("MTLSText:")]
    report["editor_media"] = [n.split(".")[-2] + "." + n.split(".")[-1].replace("apply", "").rstrip(".")
                              for n in names if n.startswith("material.library.item.")]
    time.sleep(8)  # let autosave run
    report["steps"]["quit_cleanly"] = quit_app()

    ours = summary(before)
    saved_raw = json.loads(crypto.decrypt_bytes(rt, (folder / "draft_info.json").read_bytes()))
    saved = summary(saved_raw)
    diffs = []
    if ours["tracks"] != saved["tracks"]:
        diffs.append({"tracks": {"ours": ours["tracks"], "saved": saved["tracks"]}})
    for k in sorted(set(ours["materials"]) | set(saved["materials"])):
        o, s = ours["materials"].get(k, 0), saved["materials"].get(k, 0)
        if o != s and not (k in APP_ADDS and s > o):
            diffs.append({"material": k, "ours": o, "saved": s})
    if ours["keyframe_props"] != saved["keyframe_props"]:
        diffs.append({"keyframes": [ours["keyframe_props"], saved["keyframe_props"]]})
    index = json.loads((rt.draft_root / home.INDEX).read_text("utf-8"))
    report["steps"]["still_in_index"] = any(e.get("draft_fold_path") == str(folder) for e in index["all_draft_store"])
    report["saved_version"] = saved["version"]
    report["diffs"] = diffs
    report["pass"] = all(report["steps"].values()) and not diffs
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
