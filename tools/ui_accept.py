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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jyr import crypto, home, runtime  # noqa: E402
from mouse import click  # noqa: E402

PROC = "VideoFusion-macOS"


def osa(script: str, timeout: float = 30) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        print("osascript:", out.stderr.strip()[:300], file=sys.stderr)
    return out.stdout.strip() if out.returncode == 0 else ""


def ax_names() -> list[str]:
    raw = osa(f'tell application "System Events" to tell process "{PROC}" to get name of every UI element of every window', 60)
    return [x.strip() for x in raw.split(",") if x.strip() and x.strip() != "missing value"]


def wait(pred, timeout: float, step: float = 2.0):
    end = time.time() + timeout
    while time.time() < end:
        r = pred()
        if r:
            return r
        time.sleep(step)
    return None


def locate(rt, title: str) -> tuple[float, float, float]:
    """Screen position of a home-screen draft title; retried while the UI settles."""
    script = f'''tell application "System Events" to tell process "{PROC}"
  repeat with w in windows
    try
      set t to (first static text of w whose name is "{title}")
      set p to position of t
      set s to size of t
      return {{item 1 of p, item 2 of p, item 1 of s}}
    end try
  end repeat
end tell'''
    for _ in range(15):
        subprocess.run(["open", "-a", str(rt.app_path)])
        time.sleep(1)
        pos = osa(script)
        if pos:
            return tuple(float(v) for v in pos.replace(" ", "").split(",")[:3])
        time.sleep(2)
    raise SystemExit("could not find the draft card on the home screen")


def dismiss_dialogs() -> None:
    """Close JianYing's modal prompts (e.g. 链接媒体 for missing files) with Esc."""
    for _ in range(3):
        names = osa(f'tell application "System Events" to tell process "{PROC}" to get name of every window')
        if "链接媒体" not in names:
            return
        osa(f'tell application "System Events" to tell process "{PROC}" to set frontmost to true')
        osa('tell application "System Events" to key code 53')
        time.sleep(1.5)


def quit_app() -> bool:
    dismiss_dialogs()
    # The menu click blocks while JianYing runs its exit flow, so fire and forget.
    subprocess.Popen(["osascript", "-e", f'tell application "System Events" to tell process "{PROC}" to '
                      'click menu item "退出" of menu 1 of menu bar item 2 of menu bar 1'])
    return bool(wait(lambda: not runtime.jianying_running(), 90))


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

    subprocess.run(["open", "-a", str(rt.app_path)])
    title = f"HomePageDraftTitle:{folder.name}"
    ok = wait(lambda: title in ax_names(), 120)
    report["steps"]["on_home_screen"] = bool(ok)
    if not ok:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1
    editor = None
    for _ in range(3):  # the home screen sometimes swallows the first click while it loads
        time.sleep(3)
        x, y, w = locate(rt, title)
        click(x + w / 2, y - 50)
        editor = wait(lambda: "MainWindowTitleBarExportBtn" in ax_names(), 40)
        if editor:
            break
    report["steps"]["opened_in_editor"] = bool(editor)
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
