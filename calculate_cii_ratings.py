#!/usr/bin/env python3
"""
Calculate CII (Carbon Intensity Indicator) ratings for ships based on 2024 MRV data.

This script:
1. Loads fuel consumption and fuel per distance from MRV Excel to calculate distance
2. Gets DWT/GT from individual ship JSON files
3. Uses the open-imo-cii-calculator library to calculate CII ratings
4. Updates ship JSON files with cii_rating, cii_attained, cii_required fields
"""

import json
import os
import sys
import base64
from pathlib import Path
import pandas as pd
import warnings

# Add the local CII calculator to path
sys.path.insert(0, str(Path(__file__).parent / "py-open-IMO-CII-calculator"))

from open_imo_cii_calculator.ship_carbon_intensity_calculator import ShipCarbonIntensityCalculator
from open_imo_cii_calculator.models.fuel_type import TypeOfFuel
from open_imo_cii_calculator.models.ship_type import ShipType
from open_imo_cii_calculator.models.dto.fuel_type_consumption import FuelTypeConsumption

warnings.filterwarnings('ignore')

# Constants
BASE_DIR = Path(__file__).parent
EXCEL_FILE = BASE_DIR / "data" / "2024-v173-07022026-EU MRV Publication of information.xlsx"
SHIPS_DATA_FILE = BASE_DIR / "json" / "2024_ships_data.json"
SHIP_JSON_DIR = BASE_DIR / "json" / "ship"

# CO2-eq to CO2 conversion factor (2024 uses CO2-eq which includes methane)
CO2EQ_TO_CO2_FACTOR = 0.97

# Ship type mapping from MRV types to CII calculator ShipType enum
SHIP_TYPE_MAPPING = {
    "Bulk carrier": ShipType.BULK_CARRIER,
    "Container ship": ShipType.CONTAINER_SHIP,
    "Container/ro-ro cargo ship": ShipType.RORO_CARGO_SHIP,
    "Oil tanker": ShipType.TANKER,
    "Chemical tanker": ShipType.TANKER,
    "Gas carrier": ShipType.GAS_CARRIER,
    "LNG carrier": ShipType.LNG_CARRIER,
    "General cargo ship": ShipType.GENERAL_CARGO_SHIP,
    "Combination carrier": ShipType.COMBINATION_CARRIER,
    "Refrigerated cargo carrier": ShipType.REFRIGERATED_CARGO_CARRIER,
    "Ro-ro ship": ShipType.RORO_CARGO_SHIP,
    "Vehicle carrier": ShipType.RORO_CARGO_SHIP_VEHICLE_CARRIER,
    "Ro-pax ship": ShipType.RORO_PASSENGER_SHIP,
    "Passenger ship": ShipType.CRUISE_PASSENGER_SHIP,
    "Passenger ship (Cruise Passenger ship)": ShipType.CRUISE_PASSENGER_SHIP,
}

# CII rating names
RATING_NAMES = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E"}


def encode_imo(imo: str) -> str:
    """Encode IMO number to base64 filename (without padding)."""
    return base64.b64encode(imo.encode()).decode().rstrip('=')


def load_mrv_excel():
    """Load MRV Excel data and extract fuel consumption and distance info."""
    print(f"Loading MRV Excel from {EXCEL_FILE}...")

    df_full = pd.read_excel(EXCEL_FILE, sheet_name="2024 Full ERs", header=2)
    df_partial = pd.read_excel(EXCEL_FILE, sheet_name="2024 Partial ERs", header=2)

    # Combine both sheets; Full ERs takes precedence (keep_duplicates='first')
    df = pd.concat([df_full, df_partial], ignore_index=True)
    df = df.drop_duplicates(subset=['IMO Number'], keep='first')

    # Convert relevant columns to numeric
    df['IMO Number'] = df['IMO Number'].astype(str).str.strip()
    df['Total fuel consumption [m tonnes]'] = pd.to_numeric(
        df['Total fuel consumption [m tonnes]'], errors='coerce'
    )
    df['Fuel consumption per distance [kg / n mile]'] = pd.to_numeric(
        df['Fuel consumption per distance [kg / n mile]'], errors='coerce'
    )

    # Calculate distance for each ship
    # Distance (nm) = Total Fuel (tonnes) * 1000 / Fuel per Distance (kg/nm)
    df['calculated_distance_nm'] = (
        df['Total fuel consumption [m tonnes]'] * 1000 /
        df['Fuel consumption per distance [kg / n mile]']
    )

    # Create a lookup by IMO
    mrv_data = {}
    for _, row in df.iterrows():
        imo = str(row['IMO Number']).strip()
        if imo and imo != 'nan':
            fuel_tonnes = row['Total fuel consumption [m tonnes]']
            distance_nm = row['calculated_distance_nm']
            ship_type = row['Ship type']

            if pd.notna(fuel_tonnes) and pd.notna(distance_nm) and distance_nm > 0:
                mrv_data[imo] = {
                    'fuel_consumption_tonnes': fuel_tonnes,
                    'distance_nm': distance_nm,
                    'ship_type': ship_type
                }

    print(f"Loaded {len(mrv_data)} ships with distance data from MRV Excel (Full + Partial ERs)")
    return mrv_data


def load_ships_data():
    """Load the 2024 ships data JSON."""
    print(f"Loading ships data from {SHIPS_DATA_FILE}...")
    with open(SHIPS_DATA_FILE, 'r') as f:
        data = json.load(f)

    # Create lookup by IMO
    ships = {ship['imo']: ship for ship in data['ships']}
    print(f"Loaded {len(ships)} ships from JSON")
    return ships


def load_ship_specs(imo: str):
    """Load individual ship specs from JSON file."""
    encoded = encode_imo(imo)
    ship_file = SHIP_JSON_DIR / f"{encoded}.json"

    if ship_file.exists():
        with open(ship_file, 'r') as f:
            return json.load(f)
    return None


def save_ship_specs(imo: str, specs: dict):
    """Save ship specs back to JSON file."""
    encoded = encode_imo(imo)
    ship_file = SHIP_JSON_DIR / f"{encoded}.json"

    with open(ship_file, 'w') as f:
        json.dump(specs, f, indent=4)


def map_ship_type(mrv_type: str) -> ShipType:
    """Map MRV ship type to CII calculator ShipType."""
    return SHIP_TYPE_MAPPING.get(mrv_type, ShipType.UNKNOWN)


def calculate_cii_rating(
    ship_type: ShipType,
    gross_tonnage: float,
    deadweight: float,
    distance_nm: float,
    fuel_consumption_tonnes: float,
    is_lng_carrier: bool = False
) -> dict:
    """
    Calculate CII rating for a ship.

    Returns dict with rating, attained_cii, required_cii or None if calculation fails.
    """
    calculator = ShipCarbonIntensityCalculator()

    # Convert fuel consumption to grams (library expects grams)
    fuel_consumption_grams = fuel_consumption_tonnes * 1_000_000

    # Determine fuel type - LNG carriers typically use LNG
    if is_lng_carrier:
        fuel_type = TypeOfFuel.LIQUIFIED_NATURAL_GAS
    else:
        fuel_type = TypeOfFuel.HEAVY_FUEL_OIL

    try:
        result = calculator.calculate_attained_cii_rating(
            ship_type=ship_type,
            gross_tonnage=gross_tonnage,
            deadweight_tonnage=deadweight,
            distance_travelled=distance_nm,
            fuel_type_consumptions=[FuelTypeConsumption(fuel_type, fuel_consumption_grams)],
            target_year=2024
        )

        if result and result.results:
            year_result = result.results[0]  # First result is for target year
            rating_value = int(year_result.rating) if hasattr(year_result.rating, 'value') else year_result.rating
            rating_letter = RATING_NAMES.get(rating_value, "?")

            return {
                'cii_rating': rating_letter,
                'cii_attained': round(year_result.attained_cii, 3) if year_result.attained_cii else None,
                'cii_required': round(year_result.required_cii, 3) if year_result.required_cii else None,
                'cii_year': 2024
            }
    except Exception as e:
        # Silently skip errors - many ships will have edge cases
        pass

    return None


def main(test_mode=False, test_limit=10):
    """Main function to calculate CII ratings for all ships."""

    # Load data sources
    mrv_data = load_mrv_excel()
    ships_data = load_ships_data()

    # Statistics
    stats = {
        'total': 0,
        'processed': 0,
        'skipped_no_mrv': 0,
        'skipped_no_specs': 0,
        'skipped_no_dwt_gt': 0,
        'skipped_unknown_type': 0,
        'skipped_calc_failed': 0,
        'ratings': {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}
    }

    # Get all IMOs to process
    imos = list(ships_data.keys())
    if test_mode:
        imos = imos[:test_limit]
        print(f"\n=== TEST MODE: Processing only {test_limit} ships ===\n")

    stats['total'] = len(imos)

    for i, imo in enumerate(imos):
        if i % 500 == 0:
            print(f"Processing {i}/{len(imos)}...")

        # Check if we have MRV data for this ship
        if imo not in mrv_data:
            stats['skipped_no_mrv'] += 1
            continue

        mrv = mrv_data[imo]
        ship_type_str = mrv['ship_type']

        # Map ship type
        ship_type = map_ship_type(ship_type_str)
        if ship_type == ShipType.UNKNOWN:
            stats['skipped_unknown_type'] += 1
            continue

        # Load ship specs (DWT/GT)
        specs = load_ship_specs(imo)
        if not specs:
            stats['skipped_no_specs'] += 1
            continue

        # Get DWT and GT
        try:
            deadweight = float(specs.get('deadweight', 0))
            gross_tonnage = float(specs.get('gross_tonnage', 0))
        except (ValueError, TypeError):
            deadweight = 0
            gross_tonnage = 0

        if deadweight <= 0 and gross_tonnage <= 0:
            stats['skipped_no_dwt_gt'] += 1
            continue

        # Calculate CII rating
        is_lng = ship_type == ShipType.LNG_CARRIER
        cii_result = calculate_cii_rating(
            ship_type=ship_type,
            gross_tonnage=gross_tonnage,
            deadweight=deadweight,
            distance_nm=mrv['distance_nm'],
            fuel_consumption_tonnes=mrv['fuel_consumption_tonnes'],
            is_lng_carrier=is_lng
        )

        if cii_result is None:
            stats['skipped_calc_failed'] += 1
            continue

        # Update ship specs with CII data
        specs.update(cii_result)
        save_ship_specs(imo, specs)

        stats['processed'] += 1
        stats['ratings'][cii_result['cii_rating']] += 1

        if test_mode:
            print(f"  {imo}: {ships_data[imo].get('name', 'Unknown')} - {ship_type_str} -> {cii_result['cii_rating']} (attained: {cii_result['cii_attained']}, required: {cii_result['cii_required']})")

    # Print summary
    print("\n" + "=" * 60)
    print("CII CALCULATION SUMMARY")
    print("=" * 60)
    print(f"Total ships in data:         {stats['total']}")
    print(f"Successfully processed:      {stats['processed']}")
    print(f"Skipped (no MRV data):       {stats['skipped_no_mrv']}")
    print(f"Skipped (no ship specs):     {stats['skipped_no_specs']}")
    print(f"Skipped (no DWT/GT):         {stats['skipped_no_dwt_gt']}")
    print(f"Skipped (unknown type):      {stats['skipped_unknown_type']}")
    print(f"Skipped (calc failed):       {stats['skipped_calc_failed']}")
    print()
    print("Rating Distribution:")
    for rating in ['A', 'B', 'C', 'D', 'E']:
        count = stats['ratings'][rating]
        pct = (count / stats['processed'] * 100) if stats['processed'] > 0 else 0
        bar = '#' * int(pct / 2)
        print(f"  {rating}: {count:5d} ({pct:5.1f}%) {bar}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Calculate CII ratings for ships")
    parser.add_argument('--test', action='store_true', help="Test mode - only process first 10 ships")
    parser.add_argument('--limit', type=int, default=10, help="Number of ships to process in test mode")

    args = parser.parse_args()
    main(test_mode=args.test, test_limit=args.limit)
