# Assignment 3: Field-Season Mini-Dashboard

A reusable skill that produces an aligned field-season mini-dashboard combining Sentinel-derived NDVI, daily weather, and CDL crop information for one selected field and one growing season.

## Overview

This subskill generates a single PNG dashboard image with four vertically-stacked panels sharing a common day-of-year (DOY) time axis:

1. **NDVI Time Series** — Sentinel-2 mean NDVI per scene
2. **Daily Precipitation** — Bar chart of daily rainfall
3. **Temperature Extremes** — Fill-between daily min/max with mean overlay
4. **Cumulative GDD** — Growing degree day accumulation

The dashboard answers the focused question: *What seasonal weather and vegetation patterns show up for this field-year, and how can an advisor quickly read that story from the plot?*

## Output

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/<field_id>_<year>_dashboard.png
```

## Prerequisites

- A working My Farm Advisor data-pipeline runtime
- Field boundary GeoJSON, daily weather CSV, CDL composition CSV, and Sentinel-2 NDVI rasters already generated
- Python dependencies: pandas, numpy, matplotlib, rasterio, geopandas

## Quick Start

### Generate dashboard for default field-year

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/imagery/field-season-dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021
```

### View the result

```bash
open "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/osm-1417080803_2021_dashboard.png"
```

## Command-line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--grower-slug` | `AG_GROWER_SLUG` env var | Grower identifier |
| `--farm-slug` | `AG_FARM_SLUG` env var | Farm identifier |
| `--field-id` | Required | Field identifier (e.g., osm-1417080803) |
| `--year` | Required | Growing season year |
| `--gdd-base-temp` | Auto-detected from crop | GDD base temperature in °C |
| `--gs-start-doy` | 121 (May 1) | Growing season start (day-of-year) |
| `--gs-end-doy` | 273 (Sep 30) | Growing season end (day-of-year) |
| `--output-dir` | Runtime default | Custom output directory |

## Dashboard Features

- **Shared time axis**: All panels aligned by day-of-year (1-365)
- **Growing season highlight**: Light green vertical band marks the agronomic window
- **Auto-scaled NDVI**: Y-axis adapts to the field-year's NDVI range
- **Event annotations**: Concise callouts for peak NDVI, heavy rain, temperature extremes, and frost risk
- **Crop-aware GDD**: Base temperature auto-detected from CDL crop type (overridable via CLI)

## Reusability

The script is fully parameterized:
- Change `--field-id` and `--year` for any field-year in the runtime
- GDD base temp auto-detected from crop type
- Sentinel scene discovery is automatic
- Output path auto-generated from parameters

---

## Assignment 3

### Skill/Workflow

`field-season-dashboard` — Aligned Field-Season Mini-Dashboard

### Input Files (from data-pipeline)

| Source | Runtime Path |
|--------|-------------|
| Field boundary | `growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson` |
| Daily weather | `growers/<grower>/farms/<farm>/fields/<field>/weather/daily_weather.csv` |
| CDL crop composition | `growers/<grower>/farms/<farm>/derived/tables/*_cdl_YYYY_YYYY_full_composition_updated.csv` |
| Sentinel-2 NDVI | `growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/sentinel_*/sentinel_*_ndvi.tif` |

### Weather Metrics Calculated

- **Daily precipitation** (mm) and **cumulative precipitation** (inches)
- **Temperature extremes** — daily min/max/mean (°F)
- **Growing Degree Days** (GDD, °F·days, base 50°F)
- **Cumulative GDD** starting after last spring frost (detected automatically)

### Dashboard Image Path

Relative to `data-pipeline/`:

```
imagery/field-season-dashboard/output/<field_id>_<year>_dashboard.png
```

### How to Rerun

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/imagery/field-season-dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021
```

### Known Data Limitations

- **Sentinel-2 availability**: Scene count varies by year (7–9 scenes) depending on cloud cover and satellite revisit
- **Crop-specific GDD thresholds**: Soybeans (180/1000/1650 °F·days) vs Corn (125/500/1150 °F·days) — auto-detected from CDL
- **Last frost detection**: Limited to spring period (before DOY 180); uses 36°F threshold
- **Prerequisites**: Requires pre-generated runtime data (boundaries, weather, NDVI rasters, CDL tables)
- **Year coverage**: 2021–2025 available for field `osm-1417080803`
