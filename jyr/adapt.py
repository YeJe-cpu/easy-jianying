"""Set up an app version that is not in jyr's version table yet.

The only version-specific thing jyr needs is the timeline schema
(draft_info.new_version) the app writes.

- JianYing: read its version from Info.plist; use the newest schema jyr knows.
  Open one built draft in JianYing to confirm it loads.
- CapCut: its drafts are plain JSON, so read the schema from drafts this exact
  CapCut version saved (create one blank project first if there is none).

The result is saved to ~/.jyr/profiles.json.
"""

from __future__ import annotations

import time

from . import runtime


def _newest(versions) -> str:
    return sorted(versions, key=lambda v: [int(p) for p in v.split(".")])[-1]


def adapt_capcut(rt: runtime.Runtime) -> dict:
    rep = {"target": "capcut", "version": rt.version, "already_known": rt.version in runtime.CAPCUT_VERSIONS}
    tv = runtime._version_from_drafts(rt.app, rt.version, rt.draft_root)
    if not tv:
        rep["result"] = (f"NEED ONE SAMPLE: open CapCut {rt.version}, create a blank project, wait a few seconds, "
                         "quit; then run `jyr --app capcut adapt` again.")
        return rep
    profile = {"timeline_version": tv, "adapted_at": time.strftime("%Y-%m-%d %H:%M")}
    rep["timeline_version"] = tv
    rep["profile_saved"] = str(runtime.save_user_profile(rt.version, profile, rt.app))
    rep["result"] = "OK — build a small plan, publish it, and open it in CapCut to be sure."
    return rep


def adapt() -> dict:
    rt = runtime.detect()
    if rt.is_capcut:
        return adapt_capcut(rt)
    rep = {"target": "jianying", "version": rt.version, "already_known": rt.version in runtime.KNOWN_VERSIONS}
    if rep["already_known"]:
        rep["timeline_version"] = rt.timeline_version
        rep["result"] = "OK — this JianYing version is in jyr's table; nothing to do."
        return rep
    tv = _newest(v["timeline_version"] for v in runtime.KNOWN_VERSIONS.values())
    profile = {"timeline_version": tv, "assumed": True, "adapted_at": time.strftime("%Y-%m-%d %H:%M")}
    rep["timeline_version"] = tv
    rep["profile_saved"] = str(runtime.save_user_profile(rt.version, profile))
    rep["result"] = (f"OK (assumed) — using timeline schema {tv}, the newest jyr knows. Build a small plan, "
                     "publish it and open it in JianYing once to confirm.")
    return rep
