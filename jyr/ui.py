"""Drive the JianYing app through macOS Accessibility (no screenshots needed).

Used by `jyr adapt --auto` and tools/ui_accept.py. Needs Accessibility
permission for the terminal / app running Python.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import subprocess
import sys
import time

from .runtime import Runtime, jianying_running

PROC = "VideoFusion-macOS"
MAIN = "剪映专业版"

_cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
_cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))


class _Pt(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


_cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
_cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, _Pt, ctypes.c_uint32]
_cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_cg.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
_cf.CFRelease.argtypes = [ctypes.c_void_p]


def _post(kind: int, x: float, y: float) -> None:
    ev = _cg.CGEventCreateMouseEvent(None, kind, _Pt(x, y), 0)
    _cg.CGEventSetIntegerValueField(ev, 1, 1)  # click state
    _cg.CGEventPost(0, ev)
    _cf.CFRelease(ev)


def click(x: float, y: float) -> None:
    """A real mouse click; JianYing ignores System Events' synthetic `click at`."""
    _post(5, x, y)
    time.sleep(0.15)
    _post(1, x, y)
    time.sleep(0.05)
    _post(2, x, y)


def osa(script: str, timeout: float = 60) -> str:
    out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        print("osascript:", out.stderr.strip()[:300], file=sys.stderr)
        return ""
    return out.stdout.strip()


def ax_names() -> list[str]:
    raw = osa(f'tell application "System Events" to tell process "{PROC}" to get name of every UI element of every window')
    return [x.strip() for x in raw.split(",") if x.strip() and x.strip() != "missing value"]


def wait(pred, timeout: float, step: float = 2.0):
    end = time.time() + timeout
    while time.time() < end:
        r = pred()
        if r:
            return r
        time.sleep(step)
    return None


def launch(rt: Runtime) -> None:
    subprocess.run(["open", "-a", str(rt.app_path)])


def locate(rt: Runtime, name: str) -> tuple[float, float, float, float]:
    """Screen rect (x, y, w, h) of a UI element by its accessibility name, in any window."""
    script = f'''tell application "System Events" to tell process "{PROC}"
  repeat with w in windows
    try
      set t to (first UI element of w whose name is "{name}")
      set p to position of t
      set s to size of t
      return {{item 1 of p, item 2 of p, item 1 of s, item 2 of s}}
    end try
  end repeat
end tell'''
    for _ in range(15):
        launch(rt)  # also brings it to the front
        time.sleep(1)
        pos = osa(script)
        if pos:
            x, y, w, h = (float(v) for v in pos.replace(" ", "").split(",")[:4])
            return x, y, w, h
        time.sleep(2)
    raise RuntimeError(f"JianYing UI element {name!r} not found")


def in_editor() -> bool:
    return "MainWindowTitleBarExportBtn" in ax_names()


def open_draft(rt: Runtime, folder_name: str) -> bool:
    """Click a draft card on the home screen and wait for the editor."""
    title = f"HomePageDraftTitle:{folder_name}"
    if not wait(lambda: title in ax_names(), 120):
        return False
    for _ in range(3):  # the home screen can swallow the first click while it loads
        time.sleep(3)
        x, y, w, _h = locate(rt, title)
        click(x + w / 2, y - 50)  # the thumbnail sits above the title
        if wait(in_editor, 40):
            return True
    return False


def start_new_project(rt: Runtime) -> bool:
    """Press 开始创作 so this JianYing version saves a fresh draft of its own."""
    if not wait(lambda: "HomePageStartProjectName" in ax_names(), 120):
        return False
    for _ in range(3):
        time.sleep(3)
        x, y, w, h = locate(rt, "HomePageStartProjectName")
        click(x + w / 2, y + h / 2)
        if wait(in_editor, 40):
            return True
    return False


def _press(rt_free_name: str) -> bool:
    """Click a named button wherever it is, if it is on screen."""
    script = f'''tell application "System Events" to tell process "{PROC}"
  repeat with w in windows
    try
      set t to (first UI element of w whose name is "{rt_free_name}")
      set p to position of t
      set s to size of t
      return {{(item 1 of p) + (item 1 of s) / 2, (item 2 of p) + (item 2 of s) / 2}}
    end try
  end repeat
end tell'''
    pos = osa(script)
    if not pos:
        return False
    x, y = (float(v) for v in pos.replace(" ", "").split(",")[:2])
    click(x, y)
    time.sleep(1.5)
    return True


def dismiss_dialogs() -> None:
    """Close modal prompts: 链接媒体 (missing files) with Esc, an open export dialog
    with 取消, the after-export share panel with 关闭."""
    for _ in range(3):
        names = osa(f'tell application "System Events" to tell process "{PROC}" to get name of every window')
        if "链接媒体" in names:
            osa(f'tell application "System Events" to tell process "{PROC}" to set frontmost to true')
            osa('tell application "System Events" to key code 53')
            time.sleep(1.5)
            continue
        if "导出-" in names:
            ax = ax_names()
            if "automationcloseBtn" in ax and _press("automationcloseBtn"):
                continue
            if "automationcancel" in ax and _press("automationcancel"):
                continue
        return


def quit_app() -> bool:
    if not jianying_running():
        return True
    dismiss_dialogs()
    # The menu click blocks while JianYing runs its exit flow, so fire and forget.
    subprocess.Popen(["osascript", "-e", f'tell application "System Events" to tell process "{PROC}" to '
                      'click menu item "退出" of menu 1 of menu bar item 2 of menu bar 1'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return bool(wait(lambda: not jianying_running(), 90))
