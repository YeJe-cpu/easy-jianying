"""Build jyr/data/resources.json — the built-in resource cards — from a scanned catalog.

A card is what JianYing itself writes about a transition / mask / effect /
animation / sticker / font: its name, resource id and the fields of its
material. Not the effect files: JianYing downloads those by id when a draft
needs them (tested 2026-10-30 on 11.7). Machine-specific bits are removed:
absolute paths become paths relative to JianYing's "User Data" or app bundle,
signed preview URLs and per-use ids are dropped, usage counts become ranks.

usage: python3 tools/build_resource_pack.py [~/.jyr/catalog.json]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(sys.argv[1] if len(sys.argv) > 1 else Path.home() / ".jyr/catalog.json").expanduser()
OUT = Path(__file__).resolve().parents[1] / "jyr/data/resources.json"
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
cards, by_kind = [], defaultdict(list)
for e in cat["entries"]:
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
        for k in ("slot", "target", "shape", "default_duration_us"):
            if k in e:
                card[k] = e[k]
        card["path"] = rel(e["path"])
        card["template"] = clean(e.get("template", {}))
        card["rank"] = rank
        cards.append(card)
blob = json.dumps({"schema": "jyr-resources/1", "note": "names and ids of JianYing resources; files are downloaded by JianYing",
                   "cards": cards}, ensure_ascii=False, indent=0)
assert "/Users/" not in blob and "x-signature" not in blob, "private data left in the pack"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(blob)
counts = defaultdict(int)
for c in cards:
    counts[c["kind"]] += 1
print(dict(counts), OUT, f"{OUT.stat().st_size // 1024} KB")
