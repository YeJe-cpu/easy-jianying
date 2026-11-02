"""Build the built-in resource cards — free resources only — for JianYing or CapCut.

A card is what the app itself writes about a transition / mask / effect /
animation / sticker / font: its name, resource id and the fields of its
material. Not the effect files: the app downloads those by id when a draft
needs them (tested 2026-10-30 on JianYing 11.7). Machine-specific bits are
removed: absolute paths become paths relative to the app's "User Data" or app
bundle, signed preview URLs and per-use ids are dropped, usage counts become ranks.

Only free resources go in. "Free" means the app itself recorded is_vip "0" for
that resource id in a draft's plain key_value.json, or a font bundled inside
the app (@app/...). Paid resources and resources with no record are left out.

Input is a catalog (`jyr [--app capcut] catalog scan`) or an existing pack
(cards); free/paid flags come from the entries themselves or from the
key_value.json files under --key-values (default: the app's project folder).

  jyr/data/resources.json         JianYing
  jyr/data/resources.capcut.json  CapCut

usage: python3 tools/build_resource_pack.py [--app jianying|capcut] [--key-values DIR] [--out FILE] [source.json]
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--app", choices=["jianying", "capcut"], default="jianying")
ap.add_argument("source", nargs="?", help="catalog or pack JSON")
ap.add_argument("--key-values", help="folder of draft folders whose key_value.json give free/paid flags")
ap.add_argument("--out", help="write here instead of jyr/data/")
args = ap.parse_args()
APP = args.app
ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / ("jyr/data/resources.json" if APP == "jianying" else f"jyr/data/resources.{APP}.json")
DEFAULT_SRC = {"jianying": "~/.jyr/catalog.json", "capcut": "~/.jyr/catalog-capcut.json"}[APP]
USER_DATA = {"jianying": "~/Movies/JianyingPro/User Data", "capcut": "~/Movies/CapCut/User Data"}[APP]
SRC = Path(args.source or DEFAULT_SRC).expanduser()
KV_ROOT = Path(args.key_values or f"{USER_DATA}/Projects/com.lveditor.draft").expanduser()
OUT = Path(args.out) if args.out else PACK
DROP = {"icon_url", "preview_cover_url", "request_id", "local_material_id", "constant_material_id"}


def rel(path: str) -> str:
    if path.startswith("@"):
        return path
    if "/User Data/" in path:
        return "@userdata/" + path.split("/User Data/", 1)[1]
    m = re.search(r"\.app/(Contents/.*)$", path)
    if m:
        return "@app/" + m.group(1)
    return ""  # placeholders and anything else: the app resolves by id


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items() if k not in DROP}
    if isinstance(v, list):
        return [clean(x) for x in v]
    if isinstance(v, str) and ("/Users/" in v or v.startswith("##_draftpath")):
        return rel(v)
    return v


def key_value_flags(root: Path) -> dict:
    flags = {}
    for kv in root.glob("*/key_value.json"):
        try:
            data = json.loads(kv.read_text("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        for v in data.values():
            if not isinstance(v, dict) or v.get("materialSubcategory") == "local":
                continue
            rid, flag = str(v.get("materialId") or ""), v.get("is_vip")
            if rid and flag is not None:
                flags[rid] = flags.get(rid, False) or str(flag) not in ("0", "", "false", "False")
    return flags


src = json.loads(SRC.read_text())
if src.get("app", "jianying") != APP:
    raise SystemExit(f"{SRC} is for {src.get('app', 'jianying')}, not {APP}")
entries = src.get("entries") or src.get("cards") or []
flags = key_value_flags(KV_ROOT)


def paid(e):
    """True paid, False free, None unknown."""
    if e["kind"] == "font" and rel(e.get("path", "")).startswith("@app/"):
        return False  # bundled with the app
    if e.get("vip") is not None:
        return bool(e["vip"])
    return flags.get(str(e.get("resource_id") or ""))


cards, by_kind, left_out = [], defaultdict(list), defaultdict(int)
for e in entries:
    if e["kind"] == "font" and e.get("category") == "系统字体":
        continue  # machine-specific; found on each machine at scan time
    if e["kind"] == "font" and not (e.get("resource_id") or "/Contents/Resources/Font/" in rel(e.get("path", ""))):
        continue
    p = paid(e)
    if p is not False:
        left_out["paid" if p else "no free record"] += 1
        continue
    by_kind[e["kind"]].append(e)
for kind, items in by_kind.items():
    items.sort(key=lambda e: (e.get("rank", 0), -e.get("seen", 0)))
    seen_keys = set()
    for e in items:
        key = (e["name"], e.get("slot", ""), e.get("resource_id", ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        card = {k: e[k] for k in ("kind", "name", "resource_id", "category") if k in e}
        for k in ("slot", "target", "shape", "default_duration_us"):
            if k in e:
                card[k] = e[k]
        card["vip"] = False
        card["path"] = rel(e.get("path", ""))
        card["template"] = clean(e.get("template", {}))
        card["rank"] = len(seen_keys)
        cards.append(card)
label = {"jianying": "JianYing", "capcut": "CapCut"}[APP]
note = (f"names and ids of free {label} resources (is_vip 0 in {label}'s own key_value.json, or fonts bundled "
        f"with {label}); files are downloaded by {label}")
blob = json.dumps({"schema": "jyr-resources/2", "app": APP, "note": note, "cards": cards}, ensure_ascii=False, indent=0)
assert "/Users/" not in blob and "x-signature" not in blob, "private data left in the pack"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(blob)
counts = defaultdict(int)
for c in cards:
    counts[c["kind"]] += 1
print(json.dumps({"cards": len(cards), "by_kind": counts, "left_out": left_out, "out": str(OUT)}, ensure_ascii=False))
