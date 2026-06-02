#!/usr/bin/env python3
"""Convert the ORF fixes workbook into the JSON file loaded by the sim."""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "Assets" / "FIXES ORF.xlsx"
DEFAULT_OUTPUT = ROOT / "Assets" / "orf-fixes.json"
DMS_RE = re.compile(
    r"^\s*(?P<deg>\d+(?:\.\d+)?)\D+"
    r"(?P<min>\d+(?:\.\d+)?)\D+"
    r"(?P<sec>\d+(?:\.\d+)?)?\s*"
    r"(?P<hem>[NSEW])?\s*$",
    re.IGNORECASE,
)


def parse_coordinate(value: object) -> float:
    if value is None:
        return math.nan
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return math.nan
    try:
        return float(text)
    except ValueError:
        pass

    match = DMS_RE.match(text.replace("°", "-").replace("'", "-").replace('"', " "))
    if not match:
        return math.nan

    degrees = float(match.group("deg"))
    minutes = float(match.group("min"))
    seconds = float(match.group("sec") or 0)
    decimal = degrees + minutes / 60 + seconds / 3600
    hemisphere = (match.group("hem") or "").upper()
    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal


def build_fixes(workbook_path: Path) -> list[dict[str, object]]:
    workbook = pd.ExcelFile(workbook_path)
    rows = []
    seen = set()

    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook_path, sheet_name=sheet_name)
        frame.columns = [str(column).strip().upper() for column in frame.columns]

        name_col = next((col for col in frame.columns if col in {"NAME", "IDENT", "FIX"}), None)
        identifier_col = next((col for col in frame.columns if col in {"IDENTIFIER", "DATA ID", "DATA_ID", "SHORT", "SHORT_ID"}), None)
        type_col = next((col for col in frame.columns if col == "TYPE"), None)
        lat_col = next((col for col in frame.columns if col in {"LAT", "LATITUDE"}), None)
        lon_col = next((col for col in frame.columns if col in {"LON", "LONGITUDE"}), None)
        if not name_col or not lat_col or not lon_col:
            continue

        for _, row in frame.iterrows():
            ident = str(row.get(name_col, "")).strip().upper()
            if not ident or ident == "NAN" or ident in seen:
                continue
            lat = parse_coordinate(row.get(lat_col))
            lon = parse_coordinate(row.get(lon_col))
            if not math.isfinite(lat) or not math.isfinite(lon):
                continue
            seen.add(ident)
            fix_type = str(row.get(type_col, "FIX")).strip().upper() if type_col else "FIX"
            entry = {
                "ident": ident,
                "type": fix_type if fix_type and fix_type != "NAN" else "FIX",
                "lat": round(lat, 7),
                "lon": round(lon, 7),
            }
            if identifier_col:
                identifier = str(row.get(identifier_col, "")).strip().upper()
                if identifier and identifier != "NAN":
                    entry["identifier"] = re.sub(r"[^A-Z0-9*]", "", identifier)[:3]
            rows.append(entry)

    return rows


def main() -> int:
    workbook_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_WORKBOOK
    output_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_OUTPUT
    fixes = build_fixes(workbook_path)
    if not fixes:
        raise SystemExit(f"No fixes found in {workbook_path}")
    output_path.write_text(json.dumps(fixes, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(fixes)} fixes to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
