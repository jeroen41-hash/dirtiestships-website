#!/usr/bin/env python3
"""
Aggregate per-ship CII results (written by calculate_cii_ratings.py into
json/ship/<base64-imo>.json) into json/cii_data.json, the flat list the
CII scatter plot on cii.html fetches.

Re-run this every time calculate_cii_ratings.py is re-run, so cii_data.json
stays in sync. (It previously wasn't: the file was hand-built once in
February 2026 and never regenerated despite 2024 MRV data being refreshed
many times since - this script replaces that one-off step.)
"""
import base64
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
SHIPS_DATA_FILE = BASE_DIR / "json" / "2024_ships_data.json"
SHIP_JSON_DIR = BASE_DIR / "json" / "ship"
OUT_FILE = BASE_DIR / "json" / "cii_data.json"


def encode_imo(imo: str) -> str:
    return base64.b64encode(imo.encode()).decode().rstrip("=")


def main() -> None:
    with open(SHIPS_DATA_FILE, encoding="utf-8") as f:
        ships_data = json.load(f)
    ships_by_imo = {s["imo"]: s for s in ships_data["ships"]}

    out = []
    for imo, ship in ships_by_imo.items():
        spec_file = SHIP_JSON_DIR / f"{encode_imo(imo)}.json"
        if not spec_file.exists():
            continue
        with open(spec_file, encoding="utf-8") as f:
            specs = json.load(f)
        if "cii_rating" not in specs:
            continue
        try:
            dwt = float(specs.get("deadweight", 0))
        except (TypeError, ValueError):
            dwt = 0
        out.append({
            "imo": imo,
            "name": ship.get("name") or "Unknown Ship",
            "type": ship.get("type") or "Ship",
            "dwt": dwt,
            "cii_attained": specs["cii_attained"],
            "cii_required": specs["cii_required"],
            "cii_rating": specs["cii_rating"],
        })

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump({"ships": out}, f, separators=(",", ":"))

    print(f"Wrote {OUT_FILE}: {len(out)} ships")


if __name__ == "__main__":
    main()
