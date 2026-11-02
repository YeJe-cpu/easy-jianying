"""Build jyr/data/resources.json — the built-in resource cards — from a scanned catalog.

A card is what JianYing itself writes about a transition / mask / effect /
animation / sticker / font: its name, resource id and the fields of its
material. Not the effect files: JianYing downloads those by id when a draft
needs them (tested 2026-10-30 on 11.7). Machine-specific bits are removed:
absolute paths become paths relative to JianYing's "User Data" or app bundle,
signed preview URLs and per-use ids are dropped, usage counts become ranks.

CapCut (`--app capcut`) gets its own pack, jyr/data/resources.capcut.json, from
`jyr --app capcut catalog scan`. It holds only resources CapCut itself marked
free (is_vip "0" in a draft's key_value.json) plus fonts bundled in CapCut.app;
anything Pro or without a record is left out.

usage: python3 tools/build_resource_pack.py [--app jianying|capcut] [--out FILE] [catalog.json]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--app", choices=["jianying", "capcut"], default="jianying")
ap.add_argument("catalog", nargs="?")
ap.add_argument("--out", help="write here instead of jyr/data/")
args = ap.parse_args()
APP = args.app
DEFAULT_SRC = {"jianying": "~/.jyr/catalog.json", "capcut": "~/.jyr/catalog-capcut.json"}[APP]
SRC = Path(args.catalog or DEFAULT_SRC).expanduser()
OUT = Path(__file__).resolve().parents[1] / ("jyr/data/resources.json" if APP == "jianying"
                                              else f"jyr/data/resources.{APP}.json")
if args.out:
    OUT = Path(args.out)
DROP = {"icon_url", "preview_cover_url", "request_id", "local_material_id", "constant_material_id"}


def rel(path: str) -> str:
    if "/User Data/" in path:
        return "@userdata/" + path.split("/User Data/", 1)[1]
    m = re.search(r"\.app/(Contents/.*)$", path)
    if m:
        return "@app/" + m.group(1)
    return ""  # placeholders and anything else: JianYing resolves by id


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if k not in DROP}
    if isinstance(v, list):
        return [clean(x) for x in v]
    if isinstance(v, str) and ("/Users/" in v or v.startswith("##_draftpath")):
        return rel(v)
    return v


cat = json.loads(SRC.read_text())
if cat.get("app", "jianying") != APP:
    raise SystemExit(f"{SRC} is a {cat.get('app', 'jianying')} catalog, not {APP}")
cards, by_kind, left_out = [], defaultdict(list), defaultdict(int)
for e in cat["entries"]:
    if APP == "capcut" and e.get("vip") is not False:
        left_out["pro" if e.get("vip") else "no free record"] += 1
        continue  # the CapCut pack is free resources only
    if e["kind"] == "font" and e.get("category") == "系统字体":
        continue  # machine-specific; found on each machine at scan time
    if e["kind"] == "font" and not (e.get("resource_id") or "/Contents/Resources/Font/" in e["path"]):
        continue
    by_kind[e["kind"]].append(e)
for kind, items in by_kind.items():
    items.sort(key=lambda e: -e.get("seen", 0))
    seen_keys = set()
    for rank, e in enumerate(items, 1):
        key = (e["name"], e.get("slot", ""), e.get("resource_id", ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        card = {k: e[k] for k in ("kind", "name", "resource_id", "category") if k in e}
        for k in ("slot", "target", "shape", "default_duration_us", "vip"):
            if k in e:
                card[k] = e[k]
        card["path"] = rel(e["path"])
        card["template"] = clean(e.get("template", {}))
        card["rank"] = rank
        cards.append(card)
note = {"jianying": "names and ids of JianYing resources; files are downloaded by JianYing",
        "capcut": "names and ids of free CapCut resources (is_vip 0 in CapCut's own drafts); files are downloaded by CapCut"}[APP]
blob = json.dumps({"schema": "jyr-resources/1", "app": APP, "note": note, "cards": cards}, ensure_ascii=False, indent=0)
if APP == "jianying":  # keep the JianYing pack byte-identical to before
    blob = json.dumps({"schema": "jyr-resources/1", "note": note, "cards": cards}, ensure_ascii=False, indent=0)
assert "/Users/" not in blob and "x-signature" not in blob, "private data left in the pack"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(blob)
counts = defaultdict(int)
for c in cards:
    counts[c["kind"]] += 1
print(dict(counts), OUT, f"{OUT.stat().st_size // 1024} KB", {"left_out": dict(left_out)} if left_out else "")
