"""Commands for existing drafts and recipes; kept apart so cli.py stays readable."""

from __future__ import annotations

import json
from pathlib import Path

from . import reader, runtime
from .edit import Session


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_list(a) -> int:
    rt = runtime.detect()
    for d in reader.list_drafts(rt)[: a.limit]:
        print(f"{d['duration_s']:>8.1f}s  {d['name']}")
    return 0


def cmd_inspect(a) -> int:
    rt = runtime.detect()
    r = reader.inspect(rt, reader.resolve(rt, a.draft))
    if not a.full:
        for t in r["tracks"]:
            t["segments"] = t["segments"][:a.segments] + ([f"... {len(t['segments']) - a.segments} more"]
                                                          if len(t["segments"]) > a.segments else [])
    _print(r)
    return 0


def cmd_srt(a) -> int:
    rt = runtime.detect()
    text = reader.export_srt(rt, reader.resolve(rt, a.draft), a.which)
    if a.out:
        Path(a.out).write_text(text, "utf-8")
        print(a.out)
    else:
        print(text)
    return 0


def cmd_edit(a) -> int:
    rt = runtime.detect()
    runtime.require_known(rt)
    src = reader.resolve(rt, a.draft)
    ops = json.loads(Path(a.ops).read_text("utf-8")) if a.ops else []
    if a.replace:
        for pair in a.replace:
            find, _, rep = pair.partition("=>")
            ops.append({"op": "replace_text", "find": find, "replace": rep})
    if a.relink_dir:
        ops.append({"op": "relink", "search_dirs": a.relink_dir})
    if a.add_srt:
        ops.append({"op": "add_subtitles", "srt": a.add_srt})
    if not ops:
        raise SystemExit("nothing to do: give --ops FILE or --replace / --relink-dir / --add-srt")
    s = Session(rt, src)
    s.ops(ops)
    res = {"source": src.name, "ops": s.log}
    if a.dry_run:
        res["work_copy"] = str(s.save())
    else:
        res["published"] = s.publish(a.name or f"{src.name}-jyr改")
    _print(res)
    return 0


def cmd_adapt(a) -> int:
    from .adapt import adapt
    rep = adapt(auto=a.auto)
    _print(rep)
    return 0 if rep.get("result", "").startswith("OK") else 1


def register(sub) -> None:
    p = sub.add_parser("adapt", help="learn a new JianYing version after an update")
    p.add_argument("--auto", action="store_true", help="let jyr drive JianYing to make a sample draft if needed")
    p.set_defaults(fn=cmd_adapt)

    p = sub.add_parser("list", help="drafts on JianYing's home screen")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("inspect", help="tracks, texts, missing media and resources of a draft")
    p.add_argument("draft", help="home-screen name, folder name or folder path")
    p.add_argument("--full", action="store_true")
    p.add_argument("--segments", type=int, default=5)
    p.set_defaults(fn=cmd_inspect)

    p = sub.add_parser("srt", help="export a draft's subtitles / texts as SRT")
    p.add_argument("draft")
    p.add_argument("--which", choices=["auto", "subtitle", "all"], default="auto")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_srt)

    p = sub.add_parser("edit", help="edit a COPY of a draft and add it to the home screen")
    p.add_argument("draft")
    p.add_argument("--ops", help="JSON list of ops (replace_text, relink, track_volume, remove_tracks, add_subtitles, shift)")
    p.add_argument("--replace", action="append", help="'old=>new' text replacement (repeatable)")
    p.add_argument("--relink-dir", action="append", help="find missing media by file name under this folder")
    p.add_argument("--add-srt", help="add an SRT file as a subtitle track")
    p.add_argument("--name", help="name of the new draft (default: <name>-jyr改)")
    p.add_argument("--dry-run", action="store_true", help="only write the edited copy to a temp folder")
    p.set_defaults(fn=cmd_edit)
