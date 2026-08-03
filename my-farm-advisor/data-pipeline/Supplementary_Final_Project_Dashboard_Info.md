# Supplementary Information: NDVI Crop Health Monitoring Dashboard

## Project Overview

**Branch:** `Final-Project-Dashboard`  
**Repository:** `my-farm-advisor` skill catalog  
**Objective:** Build an offline, self-contained NDVI-based Crop Health Monitoring Dashboard for a northern Illinois grower managing 10 fields across 5 growing seasons (2021–2025).

**Deliverable:** Two companion HTML dashboards that operate entirely offline via `file://` protocol with zero runtime external dependencies:

1. **Main Crop Health Dashboard** — operational monitoring with interactive map, NDVI time series, rainfall, and GDD charts
2. **Soil-NDVI Analysis Dashboard** — strategic planning with soil-NDVI quadrant analysis across organic matter and water storage metrics

---

## Dataset Preparation Steps and Processing

### 1. Field Boundaries
- **Source:** OpenStreetMap field polygons extracted via `bootstrap_farm_from_county.py`
- **Processing:** Converted to GeoJSON FeatureCollection with WGS84 coordinates, clipped to DeKalb County, Illinois
- **Output:** `boundary/field_boundaries.geojson` (10 field features with `field_id` properties)

### 2. Weather Data
- **Source:** NASA POWER S3 Zarr stores at each field centroid
- **Processing:** Extracted daily T2M_MIN, T2M_MAX, PRECTOTCORR; computed GDD (base 10°C then converted to Fahrenheit) and cumulative rainfall in inches
- **Last frost:** Computed dynamically per year — latest date before DOY 180 where T2M_MIN ≤ 0.0°C (actual range: DOY 106–123, April 16 to May 3)
- **Output:** Per-field `weather/daily_weather.csv` + farm-level aggregate `derived/tables/<farm>_weather_2021_2025.csv`

### 3. NDVI Time Series
- **Source:** Sentinel-2 Level-2A surface reflectance composites per field-year
- **Processing:** 
  - Cloud masking applied to each scene
  - NDVI computed per pixel: `(NIR - RED) / (NIR + RED)`
  - Field boundary polygon masks raster via `rasterio.mask.mask()`
  - Mean, std-dev, and valid pixel count computed excluding NaN nodata
  - Scenes grouped chronologically by DOY with connected line traces
- **Output:** 369 per-scene NDVI records across 9 fields (1 field has 0 scenes)

### 4. Soil Properties
- **Source:** USDA SSURGO Soil Survey Geographic Database via Soil Data Access (SDA) SQL API
- **Processing:** 
  - Spatial query: `mukey`, `compname`, `comppct_r`, `drainagecl`, `om_r`, `ph1to1h2o_r`, `awc_r`, `claytotal_r`, `sandtotal_r`
  - Aggregated per field: mean OM%, mean pH, total AWS (inches), mean clay%, mean sand%
  - Dominant soil series and drainage class extracted
- **Output:** Per-field `soil/ssurgo_summary.csv` + farm aggregate `derived/tables/<farm>_ssurgo_summary.csv`

### 5. Crop History
- **Source:** USDA NASS Cropland Data Layer (CDL) 2021–2025 CONUS rasters
- **Processing:** Field boundary zonal statistics per year; dominant crop by pixel count and percentage
- **Output:** `derived/tables/<farm>_cdl_2021_2025_full_composition.csv`

---

## Dataset Description

| Metric | Value |
|--------|-------|
| **Total fields** | 10 |
| **Total acreage** | ~3,200 acres |
| **Years covered** | 2021, 2022, 2023, 2024, 2025 |
| **NDVI scene records** | 369 (9 fields with data; 1 field with 0 scenes) |
| **Field-year weather combos** | 50 |
| **Total daily weather records** | 12,576 |
| **Dominant crops** | Corn, Soybeans, Grass/Pasture, Alfalfa, Winter Wheat |
| **OM% range** | 2.21% to 11.43% |
| **AWS range** | 0.79" to 6.38" |
| **Mean NDVI range** | 0.2959 to 0.3796 |
| **Latitude span** | 41.70°N to 42.15°N (~31 miles N-S) |
| **Longitude span** | -88.89°W to -88.58°W (~18 miles W-E) |

---

## Output Organization

### Farm Root Directory
```
illinois-farm/
├── illinois-farm_crop_health_dashboard.html       (5,349 KB) ← Main dashboard
├── illinois-farm_soil_ndvi_dashboard.html          (3,608 KB) ← Soil-NDVI companion
├── boundary/
│   └── field_boundaries.geojson                  (WGS84, 10 features)
├── derived/
│   └── tables/
│       ├── illinois_weather_2021_2025.csv        (farm-level weather aggregate)
│       ├── illinois_ssurgo_summary.csv           (soil aggregation, 10 rows)
│       ├── illinois_cdl_2021_2025_full_composition.csv  (crop history)
│       ├── illinois_fields_soil.csv              (raw horizon records)
│       └── illinois_full_ssurgo.csv              (extended SSURGO)
├── fields/
│   └── <field-id>/
│       ├── field.json                            (per-field metadata)
│       ├── boundary/                             (clipped GeoJSON)
│       ├── weather/
│       │   └── daily_weather.csv                 (daily records, 2021–2025)
│       ├── soil/
│       │   ├── ssurgo_summary.csv                (single-row summary)
│       │   ├── ssurgo_full.csv                   (raw horizon data)
│       │   └── soil_properties.png               (visual summary)
│       ├── satellite/
│       │   └── sentinel/
│       │       └── manifest.json                 (scene inventory)
│       └── derived/
│           └── features/
│               └── ndvi_year_YYYY_composite.tif    (yearly composites)
├── logs/                                           (pipeline execution logs)
└── manifests/                                      (rebuild fingerprints)
```

### Runtime vs. Checkout
- **Skill checkout** (`my-farm-advisor/data-pipeline/src/`): Contains generator scripts, templates, and test suites
- **Runtime tree** (`~/my-farm-advisor-runtime/data-pipeline/`): Contains generated outputs, cached Plotly bundle, and farm data
- Dashboards are written to the **runtime tree**, not the skill checkout

---

## Dashboard Explanation

### 1. Main Crop Health Dashboard
`illinois-farm_crop_health_dashboard.html`

| Component | Description |
|-----------|-------------|
| **Interactive Map** | Plotly scatter map of field polygons colored by selection state; hover shows `fieldId` + `acres`; click toggles selection |
| **Mean NDVI Time Series** | Per-scene connected line traces by field-year (369 records); x-axis = DOY 80–320; y-axis = Mean NDVI 0–1 |
| **Rainfall** | Daily Rainfall bars (left axis) + Cumulative Rainfall line (right axis) |
| **Growing Degree Days** | Cumulative GDD (base 50°F) with vertical "Last Frost" reference line |
| **Controls** | Fields dropdown (count label: Fields X/10), Years dropdown (count label: Years Y/5), Reset View button |
| **Insight Box** | Data-backed take-home messages: corn vs. soybean peak timing, no-data field warning, west-to-east spatial gradient |

### 2. Soil-NDVI Analysis Dashboard
`illinois-farm_soil_ndvi_dashboard.html`

| Component | Description |
|-----------|-------------|
| **Quadrant Legend Panel** | 4 color-coded categories with action labels |
| **OM Panel** | Mean NDVI by Percent Soil Organic Matter — 10 field curves colored by quadrant |
| **AWS Panel** | Mean NDVI by Soil Available Water Storage (Inches) — same structure |
| **Controls** | Independent Fields/Years dropdowns (not linked to main dashboard), Reset View button |

#### Quadrant Color Coding
| Color | Category | Soil State | NDVI State | Advisory Action |
|-------|----------|-----------|------------|-----------------|
| 🔴 **Red** | URGENT | Low OM/AWS | Low NDVI | Build soil health |
| 🟡 **Yellow** | RESILIENT | Low OM/AWS | High NDVI | Maintain current practice |
| 🔵 **Blue** | INVESTIGATE | High OM/AWS | Low NDVI | Check drainage/disease |
| 🟢 **Green** | EXEMPLARY | High OM/AWS | High NDVI | Replicate practices elsewhere |

---

## Analytical Interpretation

### NDVI Peak Timing by Crop
| Crop | Median Peak DOY | Typical Date | Interpretation |
|------|----------------|--------------|------------------|
| **Corn** | 227 | August 15 | Earlier canopy closure, tassel/silk stage |
| **Soybeans** | 240 | August 28 | Later canopy closure, pod-fill stage |
| **Difference** | ~13 days | ~2 weeks | Soybeans need sustained inputs later in season |

**Key finding:** Corn peaks NDVI approximately 2 weeks earlier than soybeans across all 5 years. This informs differential scouting and input timing by crop type.

### Spatial Gradients (West-to-East)
| Metric | vs. Longitude Correlation (r) | Interpretation |
|--------|------------------------------|----------------|
| **OM%** | **-0.456** (moderate) | Higher OM in western fields |
| **NDVI** | **-0.357** (moderate) | Higher NDVI in western fields |
| **AWS** | +0.214 (weak) | Slight eastward water storage trend |

**Key finding:** Western fields (osm-2000000002, osm-2000000006) show consistently higher organic matter and NDVI. Eastern fields (osm-2000000003, osm-2000000001) should be prioritized for soil-building investments.

### Soil-NDVI Quadrant Breakdown
| Field | Acres | OM% | AWS | Mean NDVI | Quadrant (OM) | Quadrant (AWS) | Action |
|-------|-------|-----|-----|-----------|---------------|----------------|--------|
| osm-2000000002 | 500.3 | **11.43** | 2.77 | 0.3245 | EXEMPLARY | EXEMPLARY | Benchmark |
| osm-2000000000 | 654.7 | 2.80 | 3.49 | 0.3103 | RESILIENT | EXEMPLARY | Build OM |
| osm-1333296916 | 1.7 | 2.21 | 0.79 | **0.3796** | RESILIENT | RESILIENT | Intensive mgmt compensates |
| osm-1417080803 | 225.8 | 4.21 | 1.19 | 0.2959 | INVESTIGATE | URGENT | Fix water/drainage |

### Zero-Coverage Field
- **Field:** `osm-2000000006` (585.84 acres)
- **Issue:** Zero Sentinel-2 scenes across all 5 years (2021–2025)
- **Implication:** Invisible to remote sensing; requires alternative monitoring (e.g., drone imagery, ground-truthing, or on-farm sensors)
- **Dashboard behavior:** Shows "No satellite imagery available" annotation; excluded from NDVI curves but included in soil/weather analysis

---

## Offline Operation Confirmation

**Both dashboards are fully operable without an internet connection.**

| Dependency | Status |
|-----------|--------|
| External CDN `<script>` tags | ❌ None |
| API calls | ❌ None |
| External fonts, images, tiles | ❌ None |
| Plotly.js source | ✅ Inlined (~5MB minified JavaScript) |
| Basemap tiles | ✅ Base64-encoded at generation time |
| All data (weather, NDVI, soil, boundaries) | ✅ Embedded as JSON in HTML |

**Verification method:**
1. Download both HTML files to a local folder
2. Disconnect WiFi / turn off network
3. Double-click either file to open in browser
4. All charts, dropdowns, hover interactions, and insight text function correctly

**Note on companion navigation:** The two dashboards were designed with navigation links between them, but `file://` to `file://` hyperlinks are unreliable across browsers (Chrome/Edge/Safari security restrictions). Each dashboard should be opened independently for offline use.

---

## AI Usage Documentation

Large language model assistance (OpenCode/Kimi) was employed extensively during this project for the following purposes:

### 1. Debugging Python Errors
- **F-string escaping in HTML templates:** Fixed `{{` vs `{` confusion when embedding JavaScript inside Python f-strings for the dashboard HTML generator
- **Plotly bundle injection:** Corrected a critical bug where the minified Plotly JS was not wrapped in `<script>` tags, causing the entire dashboard to fail rendering
- **CSS property conflicts:** Resolved `flex: 1` (flex-basis: 0%) vs `flex-grow: 1` issue that caused the insight box to squeeze text unexpectedly

### 2. Improving Visualizations
- **Map hover reliability:** Proposed replacing unreliable `hoveron: 'fills'` with invisible centroid markers (`opacity: 0, size: 120`) that capture hover events anywhere inside a field polygon
- **Persistent tooltips:** Suggested `hoverdistance: 200` to keep hover tooltips active while moving the cursor across large field areas
- **Axis label truncation:** Identified that bottom margin `b: 40` was too tight for "Day of Year" labels; increased to `b: 55` with smaller title font (12px)
- **Blue "Reset View" button:** Recommended blue background with font-smoothing CSS for readability on high-DPI displays

### 3. Explaining Geospatial Workflows
- **Mercator conversion:** Explained WGS84 (lon/lat) to Web Mercator (meters) conversion needed for Plotly scatter map alignment with basemap tiles
- **Centroid computation:** Derived the averaging algorithm for all polygon vertices to find a reliable interior point for hover markers
- **Spatial correlation analysis:** Guided the Pearson correlation calculation between soil metrics and geographic coordinates to identify the west-to-east gradient

### 4. Generating Alternative Analytical Ideas
- **Soil-NDVI quadrant concept:** Proposed the 4-quadrant framework (URGENT/RESILIENT/INVESTIGATE/EXEMPLARY) as a way to connect soil properties directly to agronomic actions
- **Companion dashboard architecture:** Argued against cramming soil analysis into the main dashboard; designed separate but related second dashboard for strategic planning
- **Spatial insight messaging:** Converted raw correlation coefficients (-0.456 for OM vs longitude) into actionable farmer-facing language about prioritizing eastern fields

### 5. Improving Dashboard Layout Structure
- **Dropdown count labels:** Suggested `Fields (3/10)` and `Years (2/5)` format so users immediately see selection scope
- **Insight box placement:** Designed position to the right of controls row with contrasting colors (green for main, blue for soil) to distinguish advisory from interactive elements
- **Legend positioning:** Iterated from below-x-axis (`y: -0.15`) to inside-plot (`y: 0.92`) to better balance white space
- **Title standardization:** Capitalized chart titles consistently ("Mean NDVI Time Series", "Daily Rainfall (in)") and added units explicitly

### 6. Code Generation and Refactoring
- **JavaScript chart builders:** Generated Plotly layout and trace configurations for NDVI, Rainfall, and GDD panels with synchronized x-axis zooming
- **Soil quadrant computation:** Implemented median-split classification logic in Python (`_compute_soil_quadrants`) and client-side JavaScript (`computeSoilQuadrants`)
- **Test suite:** Created 22 pytest acceptance tests covering farm directory validation, HTML structure, embedded data, and empty weather handling

---

## Verification Checklist

- [x] Both HTML files generated and saved to runtime farm directory
- [x] File sizes: 5,349 KB (main) and 3,608 KB (soil) — confirms inlined Plotly bundle
- [x] No `https://` or `http://` references in HTML source
- [x] Dashboards open and render correctly via `file://` protocol
- [x] All dropdowns, hovers, chart zoom, and insight text functional offline
- [x] Source code committed to `Final-Project-Dashboard` branch
- [x] README.md updated with current dashboard descriptions
- [x] This supplementary document created
