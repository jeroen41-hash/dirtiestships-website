#!/usr/bin/env python3
"""Fetch the current EU Carbon Permits (EUA) price from Trading Economics
and update json/eua_price.json. Also appends the daily price to
json/eua_price_history.json for historical tracking. Commits and pushes
to GitHub so the live site is updated.

Setup on headless Debian PC:
    cd /path/to/dirtiestships-website
    python3 -m venv venv
    venv/bin/pip install requests
    git remote set-url origin git@github.com:jeroen41-hash/dirtiestships-website.git

Cron (daily at 18:00):
    0 18 * * * cd /path/to/dirtiestships-website && venv/bin/python3 update_eua_price.py
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRICE_FILE = os.path.join(SCRIPT_DIR, "json", "eua_price.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "json", "eua_price_history.json")

URL = "https://tradingeconomics.com/commodity/carbon"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}


def fetch_eua_price():
    """Scrape the current EUA price from Trading Economics."""
    import requests
    r = requests.get(URL, headers=HEADERS, timeout=15)
    r.raise_for_status()

    # Price is in the TEChartsMeta JSON block: "value":78.730000
    match = re.search(r'TEChartsMeta\s*=\s*\[.*?"value"\s*:\s*([0-9.]+)', r.text, re.DOTALL)
    if match:
        return round(float(match.group(1)), 2)

    # Fallback: meta description "rose to 78.73 EUR"
    match = re.search(r'EU Carbon Permits\s+\w+\s+to\s+([0-9.]+)\s+EUR', r.text)
    if match:
        return round(float(match.group(1)), 2)

    raise ValueError("Could not find EUA price on page")


def update_price_file(price):
    """Write the current price to json/eua_price.json."""
    data = {
        "price": price,
        "currency": "EUR",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "Trading Economics"
    }
    with open(PRICE_FILE, "w") as f:
        json.dump(data, f, indent=4)
        f.write("\n")


def update_history(price):
    """Append today's price to json/eua_price_history.json (one entry per day)."""
    today = datetime.now().strftime("%Y-%m-%d")

    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    else:
        history = []

    # Update today's entry if it already exists, otherwise append
    for entry in history:
        if entry["date"] == today:
            entry["price"] = price
            break
    else:
        history.append({"date": today, "price": price})

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
        f.write("\n")


def git_commit_and_push():
    """Commit updated JSON files and push to GitHub."""
    os.chdir(SCRIPT_DIR)

    # Pull latest first to avoid conflicts (ignore failure e.g. no upstream set)
    subprocess.run(["git", "pull", "--rebase", "origin", "main"], capture_output=True)

    # Stage the two JSON files
    subprocess.run(
        ["git", "add", "json/eua_price.json", "json/eua_price_history.json"],
        check=True, capture_output=True
    )

    # Check if there are actually changes to commit
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], capture_output=True
    )
    if result.returncode == 0:
        print("No price change, nothing to commit.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    subprocess.run(
        ["git", "commit", "-m", f"Update EUA price ({today})"],
        check=True, capture_output=True
    )

    subprocess.run(["git", "push", "-u", "origin", "main"], check=True, capture_output=True)
    print("Committed and pushed to GitHub.")


def main():
    try:
        price = fetch_eua_price()
    except Exception as e:
        print(f"ERROR: Failed to fetch EUA price: {e}", file=sys.stderr)
        sys.exit(1)

    update_price_file(price)
    update_history(price)
    print(f"EUA price updated: \u20ac{price:.2f}")

    try:
        git_commit_and_push()
    except Exception as e:
        print(f"ERROR: Git commit/push failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
