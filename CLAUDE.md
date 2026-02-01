# Dirtiest Ships Website

## Repository
- GitHub: `jeroen41-hash/dirtiestships-website`
- Location: `/media/jeroen/work/16 Claude/dirtiestships website`
- Live site: https://dirtiestships.com (GitHub Pages)

## Overview
A website displaying CO2 emissions rankings for ships calling at EU/EEA ports, based on EU MRV (Monitoring, Reporting and Verification) Regulation data.

## Pages
- `index.html` - Ship Rankings: Paginated table of all ships, searchable by name/IMO, filterable by ship type
- `ship.html` - Individual Ship Profile: Shows ship details and historical emissions chart (accessed via `?imo=XXXXXXX`)
- `chart.html` - By Ship Type: Bar chart showing emissions by vessel category
- `companies.html` - By Company: Top 15 companies by emissions (2024 only)
- `countries.html` - By Country: Top 20 flag states by emissions
- `compare.html` - Peer Compare: Compare a ship's energy efficiency against peers of the same type (accessed via `?imo=XXXXXXX` or search)
- `FAQ.html` - Frequently Asked Questions about the data
- `disclaimer.html` - Disclaimer & Methodology

## Data Source
- EU MRV Regulation: https://mrv.emsa.europa.eu/
- Raw Excel files in `/data/` folder
- Processed JSON files in `/json/` folder

### Data Files
```
/data/
  2020-v207-...-EU MRV Publication of information.xlsx
  2021-v215-...-EU MRV Publication of information.xlsx
  2022-v240-...-EU MRV Publication of information.xlsx
  2023-v83-...-EU MRV Publication of information.xlsx
  2024-v160-...-EU MRV Publication of information.xlsx

/json/
  {year}_ships_data.json      - All ships with rankings (2020-2024)
  {year}_ships_by_type.json   - Aggregated by ship type (2020-2024)
  {year}_countries_top20.json - Top 20 flag states (2020-2024)
  2024_companies_top15.json   - Top 15 companies (2024 only)
```

### Data Notes
- 2024 uses `co2eq` (CO2 equivalent including methane etc.)
- 2020-2023 use `co2` (CO2 only)
- Company data only available in 2024 dataset
- Country = flag state (port of registry), not operating region
- Ships data includes `fuel_per_transport` metrics (pax, freight, mass, volume, dwt)
- Ships data includes `efficiency` field with design efficiency rating (e.g., "EEDI (5.41 gCO₂/t·nm)")
  - Format: `{type} ({value} gCO₂/t·nm)` where type is EEDI, EEXI, or EIV
  - Lower values = better efficiency
  - Used by compare.html to rank ships within same type

### Processing Excel Files
To process new Excel files into JSON:
```python
# Key columns in Excel (after skipping 3 header rows):
# 0: IMO Number, 1: Name, 2: Ship type, 5: Port of Registry
# 24: Total CO2 emissions [m tonnes]
# 34-38: Fuel per transport work (mass, volume, dwt, pax, freight)
```

## Tech Stack
- Static HTML/CSS/JavaScript (no build process)
- Chart.js for bar charts
- Google AdSense: `ca-pub-9641573711172527`
- GitHub Pages hosting

## Design
- Dark theme background: `#1a1a2e` to `#16213e` gradient
- Accent colors: teal `#4ecdc4`, coral `#ff6b6b`
- Header images: grayscale ship smoke photos with gradient masks
- Responsive design with mobile breakpoints

## Features
- Year selector (2020-2024)
- Search by ship name or IMO number
- Filter by ship type
- Sortable table columns
- Pagination (50 ships per page)
- Individual ship pages with historical emissions charts
- Transport work efficiency charts on ship pages
- Peer efficiency comparison (compare ship against same type vessels)
- SEO meta tags (Open Graph, Twitter Cards)

## File Structure
```
/
├── index.html        # Ship rankings
├── ship.html         # Individual ship profile (?imo=XXXXXXX)
├── chart.html        # By ship type
├── companies.html    # By company
├── countries.html    # By country
├── compare.html      # Peer efficiency comparison (?imo=XXXXXXX)
├── FAQ.html          # FAQ page
├── disclaimer.html   # Disclaimer & methodology
├── CNAME             # dirtiestships.com
├── .gitignore
├── /data/            # Raw Excel files
├── /json/            # Processed JSON data
├── /images/          # Header images
└── /launch instructins/  # Deployment notes
```

## Planned Improvements (Priority Order)

1. **Enhanced Ship Detail Cards** (ship.html)
   - Hero section with ship image (vessel finder API or placeholder by ship type)
   - Large CII rating badge with color gradient background
   - Emissions trend sparkline in header
   - Quick stats bar (rank, emissions, voyages)

2. **Interactive Chart Improvements**
   - Click-to-filter on chart segments (click ship type → filter table)
   - Animated number counters for stats
   - Hover tooltips with more context
   - Comparison overlays (year-over-year)

3. **Search Autocomplete**
   - Dropdown suggestions as you type
   - Ship type icons next to results
   - Recent searches memory
   - "Did you mean..." for typos

4. **Mobile Navigation Overhaul**
   - Hamburger menu with slide-out drawer
   - Bottom navigation bar for key pages
   - Swipe gestures for pagination
   - Touch-friendly filter controls

5. **Comparison Tool Upgrade** (compare.html)
   - Side-by-side ship cards instead of just table
   - Radar chart comparing efficiency metrics
   - "Add to compare" button on ship listings
   - Shareable comparison URLs
