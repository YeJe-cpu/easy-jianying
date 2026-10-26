"""导出成片: let JianYing itself render a draft, driven through its own UI.

open draft -> 导出 -> 确认 -> wait for the finished panel -> close -> move the
file where asked. Uses whatever export settings JianYing last used
(resolution / format); `.mp4` output is a lossless remux when needed.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from . import reader, runtime, ui
from .util import JyrError

DONE_MARKS = ("automationcloseBtn", "publish_pc_btn")


def _dialog_path() -> str:
    raw = ui.osa(f'tell application "System Events" to tell process "{ui.PROC}" to get name of every static text of every window')
    for item in raw.split(","):
        item = item.strip()
        if item.startswith("/"):
            return item
    return ""


def _stable(p: Path, secs: float = 3) -> bool:
    if not p.exists():
        return False
    a = p.stat().st_size
    time.sleep(secs)
    return p.exists() and p.stat().st_size == a and a > 0


def export(draft: str, out: str | None = None, quit_after: bool = True, timeout: float | None = None) -> dict:
    rt = runtime.detect()
    folder = reader.resolve(rt, draft)
    info = reader.inspect(rt, folder)
    if runtime.jianying_running():
        ui.quit_app()
    ui.launch(rt)
    if not ui.open_draft(rt, folder.name):
        raise JyrError("could not open the draft in JianYing")
    time.sleep(3)
    x, y, w, h = ui.locate(rt, "MainWindowTitleBarExportBtn")
    ui.click(x + w / 2, y + h / 2)
    if not ui.wait(lambda: "ExportOkBtn" in ui.ax_names(), 30):
        raise JyrError("export dialog did not open")
    shown = Path(_dialog_path())  # with or without extension, depending on its length
    if not shown.name:
        raise JyrError("could not read the export path from the dialog")
    stem = shown.stem if shown.suffix.lower() in (".mp4", ".mov") else shown.name
    x, y, w, h = ui.locate(rt, "ExportOkBtn")
    t0 = time.time()
    ui.click(x + w / 2, y + h / 2)
    limit = timeout or 120 + 4 * info["duration_s"]

    def produced():
        # Plain file next to the shown path, or — when JianYing also exports subtitles —
        # a folder of that name holding the video and a .txt/.srt.
        cands = list(shown.parent.glob(stem + ".*")) + list((shown.parent / stem).glob(stem + ".*"))
        files = [p for p in cands if p.is_file() and p.suffix.lower() in (".mp4", ".mov")
                 and p.stat().st_mtime >= t0 - 1]
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

    done = ui.wait(lambda: any(m in ui.ax_names() for m in DONE_MARKS) and produced(), limit, step=3)
    target = produced() if done else None
    if not target or not _stable(target):
        raise JyrError(f"export did not finish within {int(limit)}s (JianYing may be waiting on a prompt, "
                       "e.g. VIP materials or missing media)")
    secs = round(time.time() - t0, 1)
    try:
        x, y, w, h = ui.locate(rt, "automationcloseBtn")
        ui.click(x + w / 2, y + h / 2)
    except RuntimeError:
        pass
    result = target
    if out:
        dst = Path(out).expanduser().resolve()
        if dst.is_dir():
            dst = dst / target.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.suffix.lower() == ".mp4" and target.suffix.lower() == ".mov":
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(target), "-c", "copy",
                                "-movflags", "+faststart", str(dst)], capture_output=True)
            if r.returncode != 0:
                raise JyrError(f"remux to mp4 failed: {r.stderr.decode()[-300:]}")
            target.unlink()
        else:
            shutil.move(str(target), dst)
        for side in target.parent.glob(target.stem + ".*"):  # subtitle sidecars
            if side.suffix.lower() in (".txt", ".srt"):
                shutil.move(str(side), dst.with_suffix(side.suffix))
        if target.parent.name == stem and not any(target.parent.iterdir()):
            target.parent.rmdir()
        result = dst
    if quit_after:
        ui.quit_app()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(result)], capture_output=True, text=True).stdout.strip()
    return {"draft": folder.name, "file": str(result), "seconds_to_render": secs,
            "draft_duration_s": info["duration_s"], "file_duration_s": float(probe or 0)}
