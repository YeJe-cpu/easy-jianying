"""Post real mouse clicks (CoreGraphics) — for driving JianYing in acceptance tests.

usage: python3 tools/mouse.py click X Y [--double]
"""
import ctypes
import ctypes.util
import sys
import time

cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
cg.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
cg.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
cg.CFRelease = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation")).CFRelease
cg.CFRelease.argtypes = [ctypes.c_void_p]

MOVED, DOWN, UP = 5, 1, 2
CLICK_STATE = 1


def post(kind, x, y, count=1):
    ev = cg.CGEventCreateMouseEvent(None, kind, CGPoint(x, y), 0)
    cg.CGEventSetIntegerValueField(ev, CLICK_STATE, count)
    cg.CGEventPost(0, ev)
    cg.CFRelease(ev)


def click(x, y, double=False):
    post(MOVED, x, y)
    time.sleep(0.15)
    for n in (1, 2) if double else (1,):
        post(DOWN, x, y, n)
        time.sleep(0.05)
        post(UP, x, y, n)
        time.sleep(0.08)


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "click":
        click(float(sys.argv[2]), float(sys.argv[3]), "--double" in sys.argv)
