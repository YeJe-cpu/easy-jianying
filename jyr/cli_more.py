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


def _build(plan: dict, out: str | None, publish: bool, name: str | None = None) -> dict:
    """Shared tail of the recipe commands: save plan, optionally build and publish."""
    from . import home, plan as planmod, writer
    res = {}
    if out:
        rt = runtime.detect()
        runtime.require_known(rt)
        comp = planmod.Compiler(rt)
        d = comp.compile(plan)
        folder = Path(out).expanduser().resolve()
        writer.write(rt, d, folder, overwrite=True)
        res["built"] = str(folder)
        res["warnings"] = comp.warnings
        if publish:
            res["published"] = home.publish(rt, folder, name or d.name)
    return res


def _words(a) -> dict:
    from . import asr
    return asr.load_words(a.words) if a.words else asr.transcribe(a.media, model=a.model)


def cmd_transcribe(a) -> int:
    from . import asr
    d = _words(a)
    sents = asr.sentences(d["words"])
    out = {"source": d["source"], "engine": d["engine"], "words": d["words"],
           "sentences": [{k: s[k] for k in ("id", "start", "end", "text")} for s in sents]}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    for s in sents:
        print(f"[{s['id']:>3}] {s['start']:7.2f}-{s['end']:7.2f}  {s['text']}")
    print(f"-> {a.out}")
    return 0


def cmd_subtitles(a) -> int:
    from .recipes.subtitles import cues_from_words, subtitle_track
    from .srt import to_srt
    d = _words(a)
    cues = cues_from_words(d["words"], max_chars=a.max_chars)
    res = {"cues": len(cues)}
    if a.srt:
        Path(a.srt).write_text(to_srt([(int(c["start"] * 1e6), int(c["end"] * 1e6), c["text"]) for c in cues]), "utf-8")
        res["srt"] = a.srt
    if a.into:
        rt = runtime.detect()
        tmp = Path(a.srt or (Path(a.media).with_suffix(".jyr.srt")))
        if not a.srt:
            tmp.write_text(to_srt([(int(c["start"] * 1e6), int(c["end"] * 1e6), c["text"]) for c in cues]), "utf-8")
        s = Session(rt, reader.resolve(rt, a.into))
        s.add_subtitles(str(tmp))
        res["published"] = s.publish(a.name or f"{a.into}-字幕")
    elif a.out:
        from .media import probe
        m = probe(a.media)
        track = {"type": "video" if m.kind == "video" else "audio", "clips": [{"src": a.media}]}
        plan = {"name": a.name or Path(a.media).stem + "-字幕",
                "canvas": {"width": m.width or 1920, "height": m.height or 1080},
                "tracks": [track, subtitle_track(cues)]}
        Path(a.out).with_suffix(".plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
        res.update(_build(plan, a.out, a.publish, a.name))
    _print(res)
    return 0


def cmd_roughcut(a) -> int:
    from .recipes import roughcut
    d = _words(a)
    an = roughcut.analyze(d["words"], pause=a.pause)
    if a.edits:
        an = roughcut.apply_edits(an, json.loads(Path(a.edits).read_text("utf-8")))
    plan, rep = roughcut.build_plan(a.media, an, name=a.name or Path(a.media).stem + "-粗剪",
                                    subtitles=not a.no_subtitles)
    Path(a.plan).write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
    review = {"sentences": an["sentences"], "drops": [{k: x[k] for k in ("sentence", "word", "text", "reason")}
                                                       for x in an["drops"]]}
    Path(a.plan).with_suffix(".review.json").write_text(json.dumps(review, ensure_ascii=False, indent=1), "utf-8")
    rep["plan"] = a.plan
    rep["review"] = str(Path(a.plan).with_suffix(".review.json"))
    rep.update(_build(plan, a.out, a.publish, a.name))
    _print(rep)
    return 0


def cmd_beats(a) -> int:
    from .recipes import beats
    if not a.clips:
        r = beats.detect(a.music)
        _print({"bpm": r["bpm"], "count": len(r["beats"]), "beats": r["beats"]})
        return 0
    clips = []
    for c in a.clips:
        p = Path(c).expanduser()
        clips += sorted(str(x.resolve()) for x in p.iterdir() if x.suffix.lower() in
                        {".mp4", ".mov", ".m4v", ".png", ".jpg", ".jpeg"}) if p.is_dir() else [str(p.resolve())]
    plan, rep = beats.beat_plan(str(Path(a.music).resolve()), clips, every=a.every, max_len=a.max_len,
                                canvas=a.canvas, name=a.name or "卡点")
    Path(a.plan).write_text(json.dumps(plan, ensure_ascii=False, indent=1), "utf-8")
    rep["plan"] = a.plan
    rep.update(_build(plan, a.out, a.publish, a.name))
    _print(rep)
    return 0


def cmd_batch(a) -> int:
    from .recipes import batch
    from . import plan as planmod
    tpl = planmod.load(a.template)
    plans = batch.expand(tpl, batch.load_rows(a.rows))
    out_dir = Path(a.out_dir).expanduser().resolve()
    results = []
    for i, p in enumerate(plans, 1):
        r = _build(p, str(out_dir / f"{i:03d}"), a.publish, p["name"])
        results.append({"name": p["name"], **{k: v for k, v in r.items() if k != "warnings"}})
    _print({"drafts": len(results), "results": results})
    return 0


def cmd_fonts(a) -> int:
    from .catalog import Catalog
    from .recipes.fonts import STYLE_HINTS, candidates
    cat = Catalog(rt=runtime.detect())
    for role in ([a.role] if a.role else list(STYLE_HINTS)):
        names = [f"{e['name']}({e['category']})" for e in candidates(cat, role)[: a.limit]]
        print(f"{role:<12} " + "  ".join(names))
    return 0


def cmd_export(a) -> int:
    from .export import export
    results = [export(d, a.out, quit_after=(i == len(a.drafts) - 1)) for i, d in enumerate(a.drafts)]
    _print(results if len(results) > 1 else results[0])
    return 0


def cmd_trash(a) -> int:
    from . import home
    rt = runtime.detect()
    if a.restore:
        _print(home.restore(rt, Path(a.restore)))
        return 0
    _print(home.trash(rt, a.drafts))
    return 0


def register(sub) -> None:
    p = sub.add_parser("trash", help="take drafts off the home screen (moved to ~/.jyr/trash, restorable)")
    p.add_argument("drafts", nargs="*", help="draft folder names")
    p.add_argument("--restore", help="a ~/.jyr/trash/<time> folder to put back")
    p.set_defaults(fn=cmd_trash)

    p = sub.add_parser("export", help="render drafts to video with JianYing itself (drives its UI)")
    p.add_argument("drafts", nargs="+")
    p.add_argument("--out", help="file (.mp4/.mov) or folder; default: JianYing's export folder")
    p.set_defaults(fn=cmd_export)

    def media_args(p):
        p.add_argument("media", help="video or audio file (absolute path)")
        p.add_argument("--words", help="use words JSON from another ASR instead of local whisper")
        p.add_argument("--model", default="small", help="faster-whisper model: base/small/medium")

    p = sub.add_parser("transcribe", help="speech -> words + numbered sentences (local, no upload)")
    media_args(p)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_transcribe)

    p = sub.add_parser("subtitles", help="字幕贴语音: speech -> JianYing 识别字幕 / SRT")
    media_args(p)
    p.add_argument("--srt", help="also write an SRT file")
    p.add_argument("--out", help="build a new draft (video + subtitles) into this folder")
    p.add_argument("--into", help="add subtitles to a COPY of this existing draft instead")
    p.add_argument("--max-chars", type=int, default=16)
    p.add_argument("--publish", action="store_true")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_subtitles)

    p = sub.add_parser("roughcut", help="口播粗剪: cut fillers, stutters, retakes and dead air")
    media_args(p)
    p.add_argument("--plan", required=True, help="where to write the plan (+ .review.json)")
    p.add_argument("--edits", help="agent/human edits to the suggestions (drop_sentences, keep, drop_words)")
    p.add_argument("--pause", type=float, default=0.5, help="silences longer than this are cut (s)")
    p.add_argument("--no-subtitles", action="store_true")
    p.add_argument("--out", help="also build the draft here")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_roughcut)

    p = sub.add_parser("beats", help="卡点: detect beats, or cut clips on them")
    p.add_argument("music")
    p.add_argument("--clips", nargs="*", help="files or folders to cut on the beat (omit to just list beats)")
    p.add_argument("--every", type=int, default=1, help="cut every Nth beat")
    p.add_argument("--max-len", type=float, help="stop after this many seconds")
    p.add_argument("--canvas", default="9:16")
    p.add_argument("--plan", default="beats.plan.json")
    p.add_argument("--out")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--name")
    p.set_defaults(fn=cmd_beats)

    p = sub.add_parser("batch", help="批量: template plan x CSV/JSON rows -> many drafts")
    p.add_argument("template")
    p.add_argument("rows")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--publish", action="store_true")
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("fonts", help="字体自动调配: best local fonts per role, from your own habits")
    p.add_argument("role", nargs="?", help="title / subtitle / body / handwriting / cute")
    p.add_argument("--limit", type=int, default=6)
    p.set_defaults(fn=cmd_fonts)

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
