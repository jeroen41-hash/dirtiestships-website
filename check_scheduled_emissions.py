#!/usr/bin/env python3
"""
check_scheduled_emissions.py — Auto-publish scheduled emissions news items.

Runs on the Debian PC via cron every 15 minutes.
Checks json/news.json for items with a 'scheduled' time that has passed
and publishes them via draft_api.py.

Cron entry (*/15 * * * *):
    */15 * * * * cd ~/dirtiestships-website && ~/ship-registry/venv/bin/python3 check_scheduled_emissions.py >> ~/logs/check_scheduled_emissions.log 2>&1
"""

import os
import json
import subprocess
from datetime import datetime

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
NEWS_JSON = os.path.join(BASE_DIR, "json", "news.json")
DRAFT_API = os.path.expanduser("~/ship-registry/draft_api.py")
PYTHON    = os.path.expanduser("~/ship-registry/venv/bin/python3")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def main():
    now    = datetime.now()
    items  = load_json(NEWS_JSON, [])
    due    = [i for i in items if i.get("scheduled") and
              _parse(i["scheduled"]) and now >= _parse(i["scheduled"])]

    if not due:
        print(f"{now.strftime('%Y-%m-%d %H:%M')} No scheduled posts due.")
        return

    for item in due:
        item_id = str(item.get("id", ""))
        title   = item.get("title", "")[:60]
        print(f"{now.strftime('%Y-%m-%d %H:%M')} Publishing: {item_id} – {title}")
        result = subprocess.run(
            [PYTHON, DRAFT_API, "publish", "emissions", item_id],
            cwd=BASE_DIR, capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"  OK: {result.stdout.strip()}")
        else:
            print(f"  ERROR: {result.stderr.strip() or result.stdout.strip()}")


def _parse(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except Exception:
        return None


if __name__ == "__main__":
    main()
