"""剪映升级自适配: learn a JianYing version we have not seen.

1. the codec symbols are still exported            (otherwise: stop, nothing to do safely)
2. our bridge compiles and links against this build
3. a draft *saved by this version* decrypts, and re-encrypts byte-identically
4. read which timeline schema (new_version) this version writes
-> saved to ~/.jyr/profiles.json; build/publish/edit then work as before.

With auto=True and no sample draft yet, JianYing is driven to create one
(开始创作 -> quit), so the whole thing runs unattended.
"""

from __future__ import annotations

import json
import platform
import subprocess
import tempfile
import time
from pathlib import Path

from . import crypto, runtime

NEEDED = ["lvve::EncryptUtils::enable(bool)", "lvve::EncryptUtils::encrypt(", "lvve::EncryptUtils::decrypt("]


def _symbols(rt: runtime.Runtime) -> dict:
    nm = subprocess.run(["nm", "-gU", "-arch", platform.machine(), str(rt.dylib)], capture_output=True, text=True)
    dem = subprocess.run(["c++filt"], input=nm.stdout, capture_output=True, text=True).stdout
    return {s: s in dem for s in NEEDED}


def _samples(rt: runtime.Runtime, limit: int = 40) -> list[dict]:
    """Newest drafts whose last save came from this exact app version."""
    files = sorted(rt.draft_root.glob("*/draft_info.json"), key=lambda p: -p.stat().st_mtime)[:limit]
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        dec = crypto.decrypt_many(rt, files, Path(tmp))
        for src, dst in dec.items():
            if not dst:
                continue
            try:
                info = json.loads(dst.read_text("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if (info.get("last_modified_platform") or {}).get("app_version") == rt.version:
                out.append({"folder": src.parent.name, "new_version": info.get("new_version"),
                            "raw": src.read_bytes(), "plain": dst.read_bytes()})
    return out


def adapt_capcut(rt: runtime.Runtime) -> dict:
    """CapCut: no codec, so adapting is only reading the timeline schema its own drafts use."""
    rep = {"target": "capcut", "version": rt.version, "already_known": rt.version in runtime.CAPCUT_VERSIONS}
    tv = runtime._version_from_drafts(rt.app, rt.version, rt.draft_root)
    if not tv:
        rep["result"] = (f"NEED ONE SAMPLE: open CapCut {rt.version}, create a blank project, wait a few seconds, "
                         "quit; then run `jyr --app capcut adapt` again.")
        return rep
    profile = {"timeline_version": tv, "cipher": "plain", "adapted_at": time.strftime("%Y-%m-%d %H:%M")}
    rep["timeline_version"] = tv
    rep["profile_saved"] = str(runtime.save_user_profile(rt.version, profile, rt.app))
    rep["result"] = "OK — build a small plan, publish it, and open it in CapCut to be sure."
    return rep


def adapt(auto: bool = False) -> dict:
    rt = runtime.detect()
    if rt.is_capcut:
        return adapt_capcut(rt)
    rep = {"version": rt.version, "dylib_sha256": rt.dylib_sha256, "already_known": rt.known, "steps": {}}
    syms = _symbols(rt)
    rep["steps"]["codec_symbols"] = syms
    if not all(syms.values()):
        rep["result"] = ("STOP: this JianYing no longer exports the draft codec. Do not publish drafts; "
                         "stay on (or reinstall) the last adapted version.")
        return rep
    bridge = crypto.bridge_path(rt)
    if bridge.exists():
        bridge.unlink()
    crypto.ensure_bridge(rt)
    rep["steps"]["bridge_built"] = str(bridge)

    # 11.7+: the codec answers "ok" with nothing unless the app itself supplied the key.
    probe = json.dumps({"jyr": "probe"}).encode()
    try:
        crypto.encrypt_bytes(rt, probe)
        codec_usable = True
    except Exception:
        codec_usable = False
    rep["steps"]["codec_usable_from_outside"] = codec_usable
    if not codec_usable:
        known = [v.get("timeline_version") for v in runtime.KNOWN_VERSIONS.values() if v.get("timeline_version")]
        tv = sorted(known, key=lambda v: [int(p) for p in v.split(".")])[-1]
        profile = {"timeline_version": tv, "cipher": "plain", "dylib_sha256": rt.dylib_sha256,
                   "adapted_at": time.strftime("%Y-%m-%d %H:%M")}
        rep["profile_saved"] = str(runtime.save_user_profile(rt.version, profile))
        rep["result"] = ("OK (write-only) — this JianYing keeps the draft key inside the app (11.7+). "
                         "jyr writes plaintext drafts that JianYing encrypts itself on first save; reading drafts "
                         "JianYing saved (inspect/edit/srt) is not possible. Open one built draft to confirm.")
        return rep

    samples = _samples(rt)
    if not samples and auto:
        from . import ui
        if runtime.jianying_running():
            ui.quit_app()
        ui.launch(rt)
        made = ui.start_new_project(rt)
        time.sleep(6)
        ui.quit_app()
        rep["steps"]["created_sample_in_app"] = made
        samples = _samples(rt, limit=5)
    if not samples:
        rep["result"] = ("NEED ONE SAMPLE: open JianYing, click 开始创作, wait a few seconds, quit; "
                         "then run `jyr adapt` again (or run `jyr adapt --auto`).")
        return rep
    s = samples[0]
    enc = crypto.encrypt_bytes(rt, s["plain"])  # raises if dec(enc(x)) != x
    rep["steps"]["roundtrip"] = f"ok on {s['folder']} ({len(s['raw'])} bytes)"
    versions = sorted({x["new_version"] for x in samples if x["new_version"]},
                      key=lambda v: [int(p) for p in v.split(".")])
    profile = {"timeline_version": versions[-1], "dylib_sha256": rt.dylib_sha256,
               "adapted_at": time.strftime("%Y-%m-%d %H:%M"), "sample": s["folder"]}
    path = runtime.save_user_profile(rt.version, profile)
    rep["steps"]["timeline_version"] = versions[-1]
    rep["profile_saved"] = str(path)
    rep["result"] = ("OK — build a tiny plan and publish it once, then open it in JianYing to be sure "
                     "(tools/ui_accept.py does this unattended).")
    del enc
    return rep
