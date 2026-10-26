"""批量: one template plan x many rows of data -> many drafts.

Template strings use {{field}}. A value that fills a whole string keeps its
type ("duration": "{{secs}}" with secs=3.5 becomes 3.5).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from ..util import JyrError

FIELD = re.compile(r"\{\{\s*([\w一-鿿]+)\s*\}\}")


def load_rows(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with open(p, newline="", encoding="utf-8-sig") as f:
            return [dict(r) for r in csv.DictReader(f)]
    data = json.loads(p.read_text("utf-8"))
    if isinstance(data, dict):
        data = data.get("rows", [])
    if not isinstance(data, list):
        raise JyrError("rows file must be CSV, a JSON list, or {\"rows\": [...]}")
    return data


def _coerce(v):
    if isinstance(v, str):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v
    return v


def fill(node, row: dict, where: str = ""):
    if isinstance(node, dict):
        return {k: fill(v, row, f"{where}.{k}") for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, row, f"{where}[{i}]") for i, v in enumerate(node)]
    if isinstance(node, str):
        whole = FIELD.fullmatch(node.strip())
        missing = [m for m in FIELD.findall(node) if m not in row]
        if missing:
            raise JyrError(f"row has no field(s) {missing} used at {where or 'root'}")
        if whole:
            return _coerce(row[whole.group(1)])
        return FIELD.sub(lambda m: str(row[m.group(1)]), node)
    return node


def expand(template: dict, rows: list[dict]) -> list[dict]:
    plans = []
    for i, row in enumerate(rows):
        row = {**row, "_index": i + 1}
        p = fill(template, row)
        p["name"] = p.get("name") or f"批量-{i + 1}"
        plans.append(p)
    return plans
