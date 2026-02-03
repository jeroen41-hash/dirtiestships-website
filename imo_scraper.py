import requests
from bs4 import BeautifulSoup
import json
import os
import time
import logging
import re
import base64

# --- CONFIGURATION ---
# Path where the script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, "json", "ship")
LOG_FILE = os.path.join(BASE_DIR, "scraper.log")
# Create a text file named 'imo_list.txt' with one IMO per line
IMO_INPUT_FILE = os.path.join(BASE_DIR, "imo_list.txt") 

# Setup logging for headless monitoring
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def encode_imo(imo: str) -> str:
    """Encode IMO number to base64 filename (without padding)."""
    return base64.b64encode(imo.encode()).decode().rstrip('=')

def scrape_vessel(imo):
    if not os.path.exists(DATA_FOLDER):
        os.makedirs(DATA_FOLDER)

    url = f"https://www.vesselfinder.com/vessels/details/{imo}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }

    # Fields we want to extract (label text -> json key)
    target_fields = {
        "Year of Build": "year_of_build",
        "Length Overall": "length_overall",
        "Beam": "beam",
        "Gross Tonnage": "gross_tonnage",
        "Deadweight": "deadweight"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            vessel_data = {"imo": imo, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}

            # Extract MMSI from JavaScript variable
            script_text = soup.find(string=re.compile(r'var MMSI='))
            if script_text:
                mmsi_match = re.search(r'var MMSI=(\d+)', script_text)
                if mmsi_match:
                    vessel_data["mmsi"] = mmsi_match.group(1)

            # Extract data from tables with tpc1/tpc2 classes
            for row in soup.find_all("tr"):
                label_td = row.find("td", class_="tpc1")
                value_td = row.find("td", class_="tpc2")
                if label_td and value_td:
                    label_text = label_td.get_text(strip=True)
                    # Remove units like (m) or (t) from label
                    label_clean = re.sub(r'\s*\(.*?\)\s*', '', label_text).strip()

                    if label_clean in target_fields:
                        value_text = value_td.get_text(strip=True)
                        # Skip empty or placeholder values
                        if value_text and value_text != '-':
                            vessel_data[target_fields[label_clean]] = value_text

            # Only save if we got at least some data
            if len(vessel_data) > 2:
                encoded = encode_imo(imo)
                file_path = os.path.join(DATA_FOLDER, f"{encoded}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(vessel_data, f, indent=4)

                logging.info(f"Successfully saved IMO {imo}")
                return True
            else:
                logging.warning(f"IMO {imo} - no data found on page")
        else:
            logging.warning(f"IMO {imo} failed with status {response.status_code}")
    except Exception as e:
        logging.error(f"Critical error on IMO {imo}: {str(e)}")

    return False

def main():
    if not os.path.exists(IMO_INPUT_FILE):
        logging.error("Input file 'imo_list.txt' not found!")
        return

    with open(IMO_INPUT_FILE, "r") as f:
        imos = [line.strip() for line in f if line.strip()]

    logging.info(f"Starting batch for {len(imos)} ships.")

    for imo in imos:
        # Check if file already exists to avoid redundant scraping
        encoded = encode_imo(imo)
        if os.path.exists(os.path.join(DATA_FOLDER, f"{encoded}.json")):
            continue
            
        success = scrape_vessel(imo)
        
        # Vital for RPi/Headless: Don't get banned
        # Use a random delay to look more human
        time.sleep(7) 

if __name__ == "__main__":
    main()
