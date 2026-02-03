#!/usr/bin/env python3
"""
Fetch current EU ETS carbon price (EUA - EU Allowance) and save to JSON.

Sources tried in order:
1. Yahoo Finance (ICE EUA Futures)
2. Ember Climate API
3. Fallback to last known value

Run daily via cron:
0 9 * * * cd /path/to/dirtiestships && python3 eua_price_scraper.py
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "json" / "eua_price.json"
DEFAULT_PRICE = 65.0  # Fallback if all sources fail


def fetch_yahoo_finance():
    """Fetch EUA price from Yahoo Finance."""
    # EUA futures on Yahoo Finance (CO2.L = ICE EUA Futures on London exchange)
    symbols = ["CO2.L", "EUUA.DE", "CKZ24.NYM"]

    for symbol in symbols:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result", [])
                if result:
                    price = result[0].get("meta", {}).get("regularMarketPrice")
                    if price and price > 0:
                        print(f"Yahoo Finance ({symbol}): €{price:.2f}")
                        return float(price)
        except Exception as e:
            print(f"Yahoo Finance ({symbol}) error: {e}")

    return None


def fetch_ember_climate():
    """Fetch EUA price from Ember Climate open data."""
    try:
        # Ember's carbon price tracker API
        url = "https://ember-climate.org/api/carbon-price-tracker/"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # Look for EU ETS price
            for entry in data.get("data", []):
                if "EU" in entry.get("region", ""):
                    price = entry.get("price")
                    if price:
                        print(f"Ember Climate: €{price:.2f}")
                        return float(price)
    except Exception as e:
        print(f"Ember Climate error: {e}")

    return None


def fetch_trading_economics():
    """Scrape EUA price from Trading Economics (no API key needed for basic data)."""
    try:
        url = "https://tradingeconomics.com/commodity/carbon"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            # Look for price in the HTML (basic scraping)
            import re
            match = re.search(r'id="p"[^>]*>(\d+\.?\d*)', response.text)
            if match:
                price = float(match.group(1))
                if 20 < price < 200:  # Sanity check
                    print(f"Trading Economics: €{price:.2f}")
                    return price
    except Exception as e:
        print(f"Trading Economics error: {e}")

    return None


def get_last_known_price():
    """Get the last saved price as fallback."""
    try:
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE, "r") as f:
                data = json.load(f)
                return data.get("price", DEFAULT_PRICE)
    except:
        pass
    return DEFAULT_PRICE


def save_price(price, source):
    """Save price to JSON file."""
    data = {
        "price": round(price, 2),
        "currency": "EUR",
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": source
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=4)

    print(f"Saved: €{price:.2f} from {source}")


def push_to_github():
    """Commit and push price update to GitHub."""
    try:
        env = os.environ.copy()
        env['GIT_SSH_COMMAND'] = 'ssh -i /home/jeroen/.ssh/id_ed25519 -o StrictHostKeyChecking=no'

        subprocess.run(["git", "add", "json/eua_price.json"], check=True, cwd=BASE_DIR, env=env)

        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True, cwd=BASE_DIR, env=env)
        if result.returncode == 0:
            print("No price change to commit.")
            return False

        commit_msg = f"Update EUA price: {datetime.now().strftime('%Y-%m-%d')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=True, cwd=BASE_DIR, env=env)
        subprocess.run(["git", "push"], check=True, cwd=BASE_DIR, env=env)
        print("Pushed to GitHub.")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        return False


def main():
    print(f"[{datetime.now()}] Fetching EUA price...")

    # Try sources in order
    price = fetch_yahoo_finance()
    source = "Yahoo Finance"

    if price is None:
        price = fetch_ember_climate()
        source = "Ember Climate"

    if price is None:
        price = fetch_trading_economics()
        source = "Trading Economics"

    if price is None:
        price = get_last_known_price()
        source = "Last known value"
        print(f"All sources failed, using fallback: €{price:.2f}")

    # Sanity check
    if price < 20 or price > 200:
        print(f"Price €{price:.2f} outside expected range (20-200), using fallback")
        price = get_last_known_price()
        source = "Last known value (sanity check)"

    save_price(price, source)
    push_to_github()


if __name__ == "__main__":
    main()
