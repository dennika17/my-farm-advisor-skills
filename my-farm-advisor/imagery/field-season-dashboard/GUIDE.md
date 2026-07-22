---
name: field-season-dashboard
description: Generate an aligned field-season mini-dashboard combining Sentinel-2 NDVI, daily weather (precipitation, temperature extremes), and cumulative GDD for one field and one growing season. Produces a single PNG image with four vertically-stacked panels sharing a day-of-year time axis.
version: 1.0.0
author: Student / Assignment 3
tags: [imagery, ndvi, weather, gdd, dashboard, field-level, sentinel-2]
---

# Workflow: field-season-dashboard

## Description

Generate an aligned field-season mini-dashboard that combines four data streams on a shared time axis:

1. **NDVI** from Sentinel-2 scenes
2. **Precipitation** from NASA POWER daily weather
3. **Temperature extremes** (min/max/mean) from NASA POWER
4. **Cumulative GDD** calculated from daily temperatures

The dashboard is designed for quick advisor interpretation: scan vertically across the same dates to compare vegetation changes, rainfall, temperature events, and heat accumulation.

## When to Use

- Assignment 3 field-season analysis requiring aligned NDVI-weather-GDD visualization
- Any single-field, single-year agronomic retrospective
- When a static PNG summary is preferred over interactive dashboards

## Prerequisites

```bash
pip install -r requirements.txt
```

Dependencies: pandas, numpy, matplotlib, rasterio, geopandas

## Quick Start

```bash
export DATA_PIPELINE_DATA_ROOT=/path/to/my-farm-advisor-runtime
cd my-farm-advisor/imagery/field-season-dashboard
python src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021
```

## Output Files

PNG written to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/`:

| File | Description |
|------|-------------|
| `<field_id>_<year>_dashboard.png` | Aligned 4-panel dashboard |

## Panel Details

### Panel 1: NDVI Time Series
- Sentinel-2 mean NDVI extracted per scene using field boundary mask
- Scatter points with connecting line
- Auto-scaled y-axis
- Annotation: peak NDVI value and date

### Panel 2: Daily Precipitation
- Bar chart of PRECTOTCORR (mm/day)
- Linear scale
- Annotation: heaviest rain event(s)

### Panel 3: Temperature Extremes
- Fill-between T2M_MIN and T2M_MAX (orange, alpha=0.3)
- Mean T2M overlay (black line)
- 10°C and 20°C threshold lines (dashed)
- Annotation: hottest day, notable frost risk

### Panel 4: Cumulative GDD
- Cumulative line (green, linewidth=2)
- 500 and 1000 GDD threshold lines (dashed gray)
- Annotation: total seasonal GDD

## Shared Features

- **X-axis**: Day of Year (1-365) on Panel 4 only
- **Growing season band**: Light green vertical shading (configurable DOY range)
- **Title block**: Field ID, year, crop, acreage, GDD base, GS totals
- **Event annotations**: Concise callouts tied to data points

## Event Detection

The script automatically detects and annotates:

- **NDVI peak**: Highest mean NDVI value
- **Rapid NDVI growth**: Largest positive difference between consecutive scenes
- **Heavy rain**: Days with >25mm precipitation
- **Hot days**: Days with T2M_MAX > 30°C
- **Frost risk**: Growing season days with T2M_MIN < 2°C

## GDD Configuration

Crop-to-base-temp mapping (auto-detected from CDL):

| Crop | Base Temp (°C) |
|------|----------------|
| Corn | 10.0 |
| Soybeans | 10.0 |
| default | 10.0 |

Override via `--gdd-base-temp` CLI argument.

## Reusability

The script is fully parameterized. Change `--field-id` and `--year` for any field-year combination in the runtime. GDD base temp auto-detected from crop type. Sentinel scene discovery is automatic.

## Best Practices

- Always set `DATA_PIPELINE_DATA_ROOT` before running
- Output directory is auto-created
- Generated PNGs stay outside the skill checkout (runtime only)
- For comparison across years, generate multiple dashboards and view side-by-side

## Resources

- Parent index: `../INDEX.md`
- Skill router: `../../SKILL.md`
- Weather guide: `../../weather/nasa-power-weather/GUIDE.md`
- Sentinel-2 guide: `../sentinel2-imagery/GUIDE.md`
