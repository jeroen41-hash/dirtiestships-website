#!/usr/bin/env python3
"""
Check EU MRV EMSA for updated emission report Excel files.

Calls the THETIS-MRV public API to check for new versions of downloadable
Excel files. Sends an email notification when updates are detected.
Optionally downloads the updated files.

Run daily via cron:
0 8 * * * cd /path/to/dirtiestships-website && python3 mrv_update_checker.py

Configure:
  NOTIFY_EMAIL  - email address to send notifications to
  DOWNLOAD_DIR  - directory to save downloaded Excel files (set to None to skip downloads)
"""

import json
import os
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.text import MIMEText
from pathlib import Path

import requests

# ---- Configuration ----
NOTIFY_EMAIL = "jeroen41@gmail.com"
API_URL = "https://mrv.emsa.europa.eu/api/public-emission-report/downloadable-files"
DOWNLOAD_URL = "https://mrv.emsa.europa.eu/api/public-emission-report/reporting-period-document/binary/{period}/{version}"
BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "json" / "mrv_versions.json"
DOWNLOAD_DIR = BASE_DIR / "data"  # Set to None to skip downloading
YEARS_TO_TRACK = [2020, 2021, 2022, 2023, 2024]


def load_state():
    """Load previously saved version state."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def save_state(state):
    """Save current version state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def check_for_updates():
    """Query the EMSA API and return list of updated files."""
    try:
        response = requests.get(API_URL, headers={
            "Accept": "application/json",
            "User-Agent": "MRV-Update-Checker/1.0"
        }, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching API: {e}")
        return None, None

    current = {}
    for item in data.get("results", []):
        period = item["reportingPeriod"]
        if period in YEARS_TO_TRACK:
            current[str(period)] = {
                "version": item["version"],
                "generationDate": item["generationDate"],
                "fileName": item["fileName"]
            }

    saved = load_state()
    updates = []

    for year_str, info in current.items():
        old = saved.get(year_str)
        if old is None:
            updates.append({
                "year": year_str,
                "old_version": None,
                "new_version": info["version"],
                "date": info["generationDate"],
                "fileName": info["fileName"]
            })
        elif old["version"] != info["version"]:
            updates.append({
                "year": year_str,
                "old_version": old["version"],
                "new_version": info["version"],
                "date": info["generationDate"],
                "fileName": info["fileName"]
            })

    return updates, current


def download_file(period, version, filename):
    """Download the updated Excel file."""
    if DOWNLOAD_DIR is None:
        return False

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    url = DOWNLOAD_URL.format(period=period, version=version)
    dest = DOWNLOAD_DIR / f"{filename}.xlsx"

    try:
        print(f"  Downloading {filename}.xlsx ...")
        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  Saved to {dest}")
        return True
    except Exception as e:
        print(f"  Download error: {e}")
        return False


def send_email(updates):
    """Send notification email about updates."""
    if NOTIFY_EMAIL == "CHANGE_ME@example.com":
        print("  WARNING: NOTIFY_EMAIL not configured, skipping email.")
        return False

    subject = f"MRV Data Update - {len(updates)} file(s) updated"

    lines = ["EU MRV emission report data has been updated:\n"]
    for u in updates:
        if u["old_version"]:
            lines.append(f"  {u['year']}: v{u['old_version']} -> v{u['new_version']}  ({u['date']})")
        else:
            lines.append(f"  {u['year']}: NEW v{u['new_version']}  ({u['date']})")
    lines.append(f"\nDownload at: https://mrv.emsa.europa.eu/#public/emission-report")
    lines.append(f"\nChecked at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    body = "\n".join(lines)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = f"MRV Checker <{NOTIFY_EMAIL}>"
    msg["To"] = NOTIFY_EMAIL

    try:
        with smtplib.SMTP("localhost") as server:
            server.send_message(msg)
        print(f"  Email sent to {NOTIFY_EMAIL}")
        return True
    except Exception as e:
        print(f"  Email error: {e}")
        # Fallback: try using mail command
        try:
            proc = subprocess.run(
                ["mail", "-s", subject, NOTIFY_EMAIL],
                input=body.encode(), timeout=10
            )
            if proc.returncode == 0:
                print(f"  Email sent via mail command to {NOTIFY_EMAIL}")
                return True
        except Exception:
            pass
        print(f"  Could not send email. Install postfix or configure SMTP.")
        return False


def main():
    print(f"[{datetime.now()}] Checking MRV for updates...")

    updates, current = check_for_updates()

    if updates is None:
        print("  Failed to check for updates.")
        sys.exit(1)

    if not updates:
        print("  No updates found.")
        return

    print(f"  Found {len(updates)} update(s):")
    for u in updates:
        old = f"v{u['old_version']}" if u['old_version'] else "NEW"
        print(f"    {u['year']}: {old} -> v{u['new_version']}  ({u['date']})")

    # Download updated files
    for u in updates:
        download_file(u["year"], u["new_version"], u["fileName"])

    # Send notification
    send_email(updates)

    # Save new state
    save_state(current)
    print("  State saved.")


if __name__ == "__main__":
    main()
