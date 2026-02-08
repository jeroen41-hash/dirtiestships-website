#!/usr/bin/env python3
"""Convert EMSA MRV Excel file to website JSON files."""

import json
import openpyxl
import sys
from collections import defaultdict

EXCEL_FILE = 'data/2024-v173-07022026-EU MRV Publication of information.xlsx'
SHEET_NAME = '2024 Full ERs'
HEADER_ROWS = 3  # skip first 3 rows (headers)

# Column indices (0-based)
COL_IMO = 0
COL_NAME = 1
COL_TYPE = 2
COL_EFFICIENCY = 4
COL_REGISTRY = 5
COL_COMPANY_IMO = 8   # Company/DoC holder IMO number
COL_COMPANY = 9
COL_CO2EQ = 58       # Total CO2eq emissions [m tonnes]
COL_FPT_MASS = 74    # Fuel consumption per transport work (mass)
COL_FPT_VOLUME = 76  # (volume)
COL_FPT_DWT = 78     # (dwt)
COL_FPT_PAX = 80     # (pax)
COL_FPT_FREIGHT = 82 # (freight)

FPT_COLS = {
    'mass': COL_FPT_MASS,
    'volume': COL_FPT_VOLUME,
    'dwt': COL_FPT_DWT,
    'pax': COL_FPT_PAX,
    'freight': COL_FPT_FREIGHT,
}

# Company grouping by company IMO numbers (subsidiaries share parent IMO)
# group_name -> list of company IMO numbers
COMPANY_GROUPS = {
    'MSC Group': ['1535947', '0750415', '5908969'],
    'Maersk': ['5808451', '1135952'],
    'CMA CGM Group': ['5427869', '5463827', '0194433', '6376154', '1826240'],
    'Carnival Corporation': ['0196718', '5375992', '1996500', '2057932', '1890038'],
    'Evergreen Marine': ['0344771', '4201057'],
}


def parse_float(val):
    """Parse a cell value to float, returning None for invalid values."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val != 0 else None
    s = str(val).strip()
    if s in ('', 'N/A', 'Division by zero!', '0', '0.0'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_str(val):
    """Parse a cell value to string."""
    if val is None:
        return ''
    return str(val).strip()


def load_registry_mapping():
    """Load registry -> country mapping from existing data."""
    with open('data/registry_country_mapping.json') as f:
        return json.load(f)


def build_company_imo_lookup():
    """Build company_imo -> group_name lookup from COMPANY_GROUPS."""
    lookup = {}
    for group, imos in COMPANY_GROUPS.items():
        for imo in imos:
            lookup[imo] = group
    return lookup


def main():
    print(f"Loading {EXCEL_FILE}...")
    wb = openpyxl.load_workbook(EXCEL_FILE, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]

    registry_map = load_registry_mapping()

    ships = []
    skipped = 0

    for i, row in enumerate(ws.iter_rows(min_row=HEADER_ROWS + 1, values_only=True)):
        imo = parse_str(row[COL_IMO])
        if not imo or imo == 'N/A':
            skipped += 1
            continue

        co2eq = parse_float(row[COL_CO2EQ])
        if co2eq is None or co2eq <= 0:
            skipped += 1
            continue

        # Build fuel_per_transport
        fpt = {}
        for key, col in FPT_COLS.items():
            val = parse_float(row[col])
            if val is not None:
                fpt[key] = round(val, 2)

        registry = parse_str(row[COL_REGISTRY])
        country = registry_map.get(registry, registry)

        ship = {
            'imo': imo,
            'name': parse_str(row[COL_NAME]),
            'type': parse_str(row[COL_TYPE]),
            'efficiency': parse_str(row[COL_EFFICIENCY]),
            'registry': registry,
            'company': parse_str(row[COL_COMPANY]),
            'company_imo': parse_str(row[COL_COMPANY_IMO]),
            'co2eq': round(co2eq, 2),
            'country': country,
            'fuel_per_transport': fpt,
        }
        ships.append(ship)

    wb.close()
    print(f"Loaded {len(ships)} ships ({skipped} skipped)")

    # Sort by co2eq descending, assign ranks
    ships.sort(key=lambda s: s['co2eq'], reverse=True)
    for i, ship in enumerate(ships):
        ship['rank'] = i + 1

    # Strip company_imo from output (only used for grouping)
    ships_output = []
    for ship in ships:
        s = {k: v for k, v in ship.items() if k != 'company_imo'}
        ships_output.append(s)

    total_co2eq = round(sum(s['co2eq'] for s in ships), 2)

    # 1. Write main ships data
    ships_data = {
        'total_ships': len(ships_output),
        'total_co2eq': total_co2eq,
        'ships': ships_output,
    }
    with open('json/2024_ships_data.json', 'w') as f:
        json.dump(ships_data, f, separators=(',', ':'))
    print(f"Wrote json/2024_ships_data.json: {len(ships)} ships, {total_co2eq:,.2f} total CO2eq")

    # 2. Ships by type
    type_agg = defaultdict(lambda: {'co2eq': 0.0, 'count': 0})
    for ship in ships:
        t = ship['type']
        type_agg[t]['co2eq'] += ship['co2eq']
        type_agg[t]['count'] += 1

    ships_by_type = sorted(
        [{'type': t, 'co2eq': round(d['co2eq'], 2), 'count': d['count']}
         for t, d in type_agg.items()],
        key=lambda x: x['co2eq'], reverse=True
    )
    with open('json/2024_ships_by_type.json', 'w') as f:
        json.dump(ships_by_type, f, separators=(',', ':'))
    print(f"Wrote json/2024_ships_by_type.json: {len(ships_by_type)} types")

    # 3. Countries top 20
    country_agg = defaultdict(lambda: {'co2eq': 0.0, 'count': 0})
    for ship in ships:
        c = ship['country']
        if c:
            country_agg[c]['co2eq'] += ship['co2eq']
            country_agg[c]['count'] += 1

    countries_all = sorted(
        [{'country': c, 'co2eq': round(d['co2eq'], 2), 'count': d['count']}
         for c, d in country_agg.items()],
        key=lambda x: x['co2eq'], reverse=True
    )
    with open('json/2024_countries_top20.json', 'w') as f:
        json.dump(countries_all[:20], f, separators=(',', ':'))
    print(f"Wrote json/2024_countries_top20.json")

    # 4. Companies top 15 (grouped by company IMO, then by exact name)
    company_imo_lookup = build_company_imo_lookup()

    # First pass: aggregate by company IMO
    cimo_agg = defaultdict(lambda: {'co2eq': 0.0, 'count': 0, 'names': defaultdict(int)})
    for ship in ships:
        cimo = ship['company_imo']
        cimo_agg[cimo]['co2eq'] += ship['co2eq']
        cimo_agg[cimo]['count'] += 1
        cimo_agg[cimo]['names'][ship['company']] += 1

    # Second pass: merge grouped company IMOs, keep others as-is
    group_agg = defaultdict(lambda: {'co2eq': 0.0, 'count': 0})
    for cimo, data in cimo_agg.items():
        group = company_imo_lookup.get(cimo)
        if group:
            group_agg[group]['co2eq'] += data['co2eq']
            group_agg[group]['count'] += data['count']
        else:
            # Use the most common company name for this IMO
            label = max(data['names'], key=data['names'].get)
            group_agg[label]['co2eq'] += data['co2eq']
            group_agg[label]['count'] += data['count']

    companies_top = sorted(
        [{'company': g, 'co2eq': round(d['co2eq'], 2), 'count': d['count']}
         for g, d in group_agg.items()],
        key=lambda x: x['co2eq'], reverse=True
    )[:15]
    with open('json/2024_companies_top15.json', 'w') as f:
        json.dump(companies_top, f, separators=(',', ':'))
    print(f"Wrote json/2024_companies_top15.json")

    # Verification: check top 3 ships
    print("\nTop 3 ships:")
    for s in ships[:3]:
        print(f"  #{s['rank']} {s['name']} ({s['imo']}): {s['co2eq']:,.2f} CO2eq")


if __name__ == '__main__':
    main()
