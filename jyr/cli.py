"""Command line: `python3 -m jyr <command>` (or `jyr` once installed)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, catalog, files, home, plan as planmod, runtime, writer
from .util import JyrError


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_doctor(a) -> int:
    rt = runtime.detect()
    rep = {"target": rt.app.key, "app": str(rt.app_path), "version": rt.version, "build": rt.build,
           "adapted": rt.known, "timeline_version": rt.timeline_version or None, "draft_root": str(rt.draft_root),
           "app_running": runtime.app_running(rt), "draft_files": "plain JSON"}
    if rt.is_capcut:
        sample = next(iter(sorted(rt.draft_root.glob("*/draft_info.json"), key=lambda p: -p.stat().st_mtime)), None)
        if sample:
            try:
                files.read_json(rt, sample)
                rep["read_check"] = f"ok ({sample.parent.name})"
            except (JyrError, ValueError) as e:
                rep["read_check"] = f"FAILED: {e}"
    else:
        rep["note"] = "jyr writes drafts for JianYing; drafts JianYing has saved are not read"
    path = catalog.catalog_path(rt)
    rep["catalog"] = str(path) if path.exists() else \
        f"built-in free resources only (`jyr{' --app capcut' if rt.is_capcut else ''} catalog scan` adds your own)"
    rep["status"] = "ok" if rt.known else "needs-attention"
    _print(rep)
    return 0 if rep["status"] == "ok" else 1


def cmd_catalog(a) -> int:
    rt = runtime.detect()
    if a.action == "scan":
        c = catalog.scan(rt)
        counts = {}
        for e in c["entries"]:
            if e.get("available"):
                counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        res = {"drafts_scanned": c["drafts_scanned"], "unreadable": c["drafts_unreadable"],
                "available": counts, "saved_to": str(catalog.catalog_path(rt))}
        res["paid"] = sum(1 for e in c["entries"] if e.get("vip") is True)
        res["no_free_record"] = sum(1 for e in c["entries"] if e.get("vip") is None)
        _print(res)
        return 0
    cat = catalog.Catalog(rt=rt)
    rows = [e for e in cat.list(a.kind) if e.get("available") and (not a.grep or a.grep in e["name"])
            and (not a.free or e.get("vip") is False)]
    for e in rows[: a.limit]:
        extra = e.get("slot") or e.get("shape") or e.get("category") or ""
        vip = {True: "paid", False: "free"}.get(e.get("vip"), "")
        print(f"{e['kind']:<12} {e['name']:<24} {extra:<10} {vip:<5} used×{e['seen']}")
    print(f"({len(rows)} shown of kind={a.kind or 'all'})", file=sys.stderr)
    return 0


def cmd_build(a) -> int:
    rt = runtime.detect()
    runtime.require_known(rt)
    p = planmod.load(a.plan)
    comp = planmod.Compiler(rt, base_dir=Path(a.plan).resolve().parent)
    d = comp.compile(p)
    out = Path(a.out).expanduser().resolve()
    writer.write(rt, d, out, pack=a.pack or bool(p.get("pack_media")), overwrite=a.force)
    tracks = [{"type": t.kind, "segments": len(t.segments)} for t in d.tracks]
    res = {"built": str(out), "name": d.name, "duration_s": round(d.duration / 1e6, 3), "tracks": tracks,
           "warnings": comp.warnings}
    if a.publish:
        res["published"] = home.publish(rt, out, a.name or d.name)
    _print(res)
    return 0


def cmd_publish(a) -> int:
    rt = runtime.detect()
    runtime.require_known(rt)
    _print(home.publish(rt, Path(a.build).resolve(), a.name))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="jyr", description="Write JianYing (剪映) / CapCut drafts from code.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--app", choices=["auto", "jianying", "capcut"], default=None,
                    help="which editor to target (default: the one installed; JianYing if both)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check the JianYing / CapCut install").set_defaults(fn=cmd_doctor)

    c = sub.add_parser("catalog", help="scan / list transitions, masks, effects, fonts... this machine has")
    c.add_argument("action", choices=["scan", "list"])
    c.add_argument("kind", nargs="?", help="transition|mask|effect|filter|animation|font|sticker|audio_effect|text_effect")
    c.add_argument("--grep", default="")
    c.add_argument("--limit", type=int, default=200)
    c.add_argument("--free", action="store_true", help="only resources known to be free")
    c.set_defaults(fn=cmd_catalog)

    b = sub.add_parser("build", help="plan.json -> draft folder (does not touch the app)")
    b.add_argument("plan")
    b.add_argument("--out", required=True)
    b.add_argument("--pack", action="store_true", help="copy media into the draft folder")
    b.add_argument("--force", action="store_true", help="replace --out if it exists")
    b.add_argument("--publish", action="store_true", help="also put it on the app's home screen")
    b.add_argument("--name")
    b.set_defaults(fn=cmd_build)

    p = sub.add_parser("publish", help="put a built draft on the app's home screen")
    p.add_argument("build")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_publish)

    from . import cli_more
    cli_more.register(sub)

    a = ap.parse_args(argv)
    if a.app:
        os.environ["JYR_TARGET"] = a.app
    try:
        return a.fn(a)
    except JyrError as e:
        print(f"jyr: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
