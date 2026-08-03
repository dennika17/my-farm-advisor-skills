# Data Pipeline Runtime Setup

This subskill ships the scripts that build the data-pipeline reports and
posters. Each runtime host creates its own virtualenv inside the data tree on
first run; the scripts auto-bootstrap that environment before continuing.

## Quick start

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/ingest/bootstrap_farm_from_county.py \
  --state-fips 17 \
  --county-name DeKalb \
  --count 5 \
  --seed 77 \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --farm-name "DeKalb Demo Farm" \
  --run-pipeline \
  --force
```

For a first run that also initializes shared data and seeds fields for a grower in a state, use the installer directly from the checkout:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh \
  --prepare-shared-data \
  --seed-grower-slug acme-grower \
  --seed-state Illinois \
  --seed-field-count 12 \
  --seed-farm-name "Acme Illinois Farm"
```

That command installs the runtime source and venv, builds shared geoadmin L0/L1/L2 payloads, shared NASA POWER county weather, GDD, annual corn RM, annual soybean MG, five-year FIPS-average corn RM and soybean MG datasets, and last-five-year CONUS CDL rasters. It then selects a top-crop county in the requested state, samples the requested number of OSM fields, and runs the full farm pipeline so derived tables, field weather, soil outputs, CDL history, satellite/NDVI products, reports, cards, posters, and HTML/Markdown farm reports are generated automatically.

If the runtime is already installed, run the equivalent from the runtime source copy:

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/farm_dashboard.py create \
  --prepare-shared-data \
  --grower-slug acme-grower \
  --state Illinois \
  --field-count 12 \
  --farm-name "Acme Illinois Farm"
```

`DATA_PIPELINE_DATA_ROOT` is required. Set it to an absolute writable path outside the skill checkout before running the installer or any pipeline entrypoint. There is no implicit fallback to a platform workspace path or to a checkout-local `data/` directory.

The installer creates and refreshes the runtime tree under:

- runtime base: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline`
- runtime source copy: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`
- default runtime venv: `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv`

Generated outputs, manifests, reports, logs, and downloaded payloads belong under the runtime base, for example `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers` and `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared`. The committed checkout remains the source for installer scripts and baseline `src/` files, but runtime execution happens from the copied source.

Farm weather now uses NASA POWER's public S3 Zarr stores by default at actual field centroids. The default farm weather controls are `--weather-backend zarr`, `--weather-start-year 2021`, `--weather-end-year 2025`, and `--weather-time-standard lst`. The output path and CSV schema stay compatible with existing reports:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/<farm>_weather_2021_2025.csv
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/weather/daily_weather.csv
```

Run or override those defaults from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug il-dekalb-grower \
  --farm-slug dekalb-demo-farm \
  --farm-name "DeKalb Demo Farm" \
  --weather-backend zarr \
  --weather-start-year 2021 \
  --weather-end-year 2025 \
  --weather-time-standard lst
```

Use `--weather-backend api` only when explicitly debugging the legacy NASA POWER point API path for small field sets.

Shared county weather for maturity-by-FIPS uses NASA POWER's public S3 Zarr stores by default instead of issuing one `power.larc.nasa.gov` point API request per county grid cell. This avoids API rate-limit failures for L2 geoadmin scopes while preserving the existing output path and schema:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/weather/nasa-power/<year>/daily_weather_by_fips.parquet
```

For the full shared lower48 baseline, initialize the runtime with multi-year county weather, GDD, corn RM, soybean MG, corn/soybean five-year FIPS averages, and CDL raster outputs. The default shared maturity range is 2021-2025 to match the farm weather and CDL helper defaults; CDL initialization fetches the last five available CONUS rasters by default:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh --prepare-shared-data
```

That install flag runs the equivalent of:

```bash
python scripts/run_maturity_years_by_fips.py \
  --start-year 2021 \
  --end-year 2025 \
  --coverage lower48 \
  --weather-backend zarr \
  --weather-time-standard lst
python scripts/ingest/download_cdl.py \
  --raster-only \
  --cdl-scope conus \
  --cdl-latest-year 2025 \
  --cdl-window-years 5
```

`--prepare-shared-maturity` remains available for weather/GDD/corn/soy maturity only, but it does not prepare CDL rasters.

The maturity runner writes annual files like `shared/corn_maturity/tables/rm_by_fips_2025.parquet` and final five-year average files like `shared/corn_maturity/tables/rm_by_fips_2021_2025_average.parquet` and `shared/soybean_maturity/tables/mg_by_fips_2021_2025_average.parquet`.

For a single annual refresh, run:

```bash
python scripts/run_maturity_by_fips.py \
  --year 2025 \
  --coverage lower48 \
  --weather-backend zarr \
  --weather-time-standard lst
```

Use `--weather-backend api` only when explicitly debugging the legacy NASA POWER point API path for county weather.

To persist the default data root for future login sessions, write the user environment file and still export the variable in the current shell before running commands:

```bash
mkdir -p "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d"
cat > "${XDG_CONFIG_HOME:-$HOME/.config}/environment.d/60-my-farm-advisor.conf" <<'EOF'
DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
EOF
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
```

The `environment.d` file applies to future sessions only. It does not update an already-running shell.

## Running inside OpenClaw CLI

When invoking the pipeline from the control UI or `openclaw-cli`, you can still
activate the environment explicitly, but the entrypoints will install and re-exec
themselves if the runtime venv is missing.

```bash
bash -lc 'export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime && \
  cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src" && \
  "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
    scripts/run_farm_pipeline.py --grower-slug ... --farm-slug ...'
```

This ensures every pipeline step (including geopandas/rasterio operations) uses
the shared environment that lives alongside the replicated scripts.

## Grower Field Weather Dashboard

The data-pipeline includes an offline, single-file **Grower Field Weather Dashboard** generator. It produces a self-contained HTML file with embedded Plotly.js, farm/field GeoJSON data, per-field weather time series, and an optional satellite basemap — all inlined so the file works from `file://` with zero runtime external dependencies.

### What it produces

- One HTML file per farm, placed by default at `<farm-dir>/<farm-slug>_weather_dashboard.html`
- Interactive Plotly map of field polygons with click-to-toggle selection
- Growing Degree Days chart (cumulative GDD, base 10°C) with frost-date markers
- Rainfall chart (daily bars + cumulative line) with dual Y-axes
- Custom multi-select dropdowns for fields and years, with synchronized chart axes
- Responsive layout: two-column on desktop, stacked on narrow screens

### Full-pipeline vs standalone

**Full pipeline (opt-in):**
```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug <grower> \
  --farm-slug <farm> \
  --generate-dashboard
```

The `--generate-dashboard` flag appends dashboard generation as a final pipeline step. It remains backward compatible: dashboards are **not** generated by default.

**Standalone (direct generation):**
```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_weather_dashboard.py \
  --farm-dir <farm-dir> \
  --output <custom-path.html>
```

Standalone generation reads only existing farm outputs. It does **not** invoke weather downloads, boundary processing, or any upstream pipeline stages.

**Via `farm_dashboard.py` wrapper:**
```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/farm_dashboard.py dashboard generate \
  --farm-dir <farm-dir> \
  --no-basemap \
  --output <custom-path.html>
```

### Farm directory inputs

The generator accepts a farm directory via these precedence rules:

1. `--farm-dir <path>` — explicit farm output directory
2. `--growers-dir <path>` — growers root; discovers exactly one valid farm beneath it
3. `DATA_PIPELINE_DATA_ROOT` environment variable — searches under the runtime root
4. Auto-discovery under `~` — searches for `*/data-pipeline/growers/*/farms/*/` with structural validation

A directory is treated as a valid farm only when it contains at minimum:
- `boundary/field_boundaries.geojson`
- `fields/`

If multiple valid farms are discovered and none is explicitly selected, the generator fails with a clear actionable error listing candidate paths.

### Input data assumptions

The generator expects the canonical farm layout:

```text
<farm-dir>/
├── boundary/field_boundaries.geojson   (GeoJSON FeatureCollection, WGS84)
├── fields/<field-id>/
│   ├── field.json                      (per-field metadata, optional)
│   └── weather/daily_weather.csv       (daily weather, optional)
└── derived/tables/*.csv                (farm aggregates, optional fallback)
```

Weather CSVs must contain at minimum `date`, `T2M_MIN`, `T2M_MAX`, and `PRECTOTCORR`. Header-only or empty CSVs are tolerated: the field is labeled `(no data)` but generation continues.

### Weather calculations and units

- **Growing Degree Days (GDD):**
  - `dailyGdd = max((T2M_MAX + T2M_MIN) / 2 - 10.0, 0)`
  - `cumulativeGdd` is the running total beginning on the last frost date
- **Rainfall:**
  - `dailyRainfallIn = PRECTOTCORR * 0.0393701`
  - `cumulativeRainfallIn` is the running total beginning on the last frost date
- **Last frost date:**
  - Latest day before July 1 where `T2M_MIN <= 0.0`
  - If no qualifying frost exists, January 1 of that year is used
- Cumulative totals span only valid observations (no zero-filling for missing days)

### Offline and runtime dependency guarantee

The generated HTML has zero runtime external dependencies:

- No CDN `<script>` or `<link>` tags
- No API calls
- No external fonts, images, tiles, or data files
- Plotly.js is downloaded once at build time, cached under `shared/assets/`, and fully inlined
- The file works when opened directly from disk via `file://`

### Basemap behavior

At generation time, the generator optionally acquires Esri World Imagery tiles, stitches them with Pillow, crops to the buffered farm extent, and base64-encodes the result into the HTML. Use `--no-basemap` to skip tile acquisition and produce a neutral-background dashboard with a visible note that imagery was unavailable. If tile download fails for any reason, the generator falls back gracefully to the same neutral background.

### Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| `No valid farm directory found` | Provide `--farm-dir` explicitly, or ensure the directory contains `boundary/field_boundaries.geojson` and `fields/`. |
| `Multiple farms found` | Use `--farm-dir` to select a specific farm, or `--growers-dir` to narrow the search scope. |
| `No valid fields found` | The boundary GeoJSON is empty or all features lack a `field_id` property. |
| `Failed to download Plotly bundle` | Build-time network is required for the first run (or pre-stage `shared/assets/plotly-<version>.min.js`). |
| `Basemap unavailable` | Esri tiles may be unreachable; use `--no-basemap` for a fully offline dashboard. |

### Implementation and file locations

This dashboard capability was added to the `my-farm-advisor/data-pipeline` sub-skill. The new generator modules live in the skill checkout at:

```text
my-farm-advisor/data-pipeline/src/scripts/reporting/
├── generate_weather_dashboard.py   (main generator)
├── dashboard_html_template.py      (HTML/JS template)
└── dashboard_assets.py             (Plotly bundling + basemap tiles)
```

Tests and fixtures were added under:

```text
my-farm-advisor/data-pipeline/tests/
├── test_weather_dashboard.py
└── fixtures/mock-farm/
```

Pipeline integration is handled by:

- `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py` — added `--generate-dashboard` flag
- `my-farm-advisor/data-pipeline/src/scripts/farm_dashboard.py` — added `dashboard generate` subcommand
- `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` — added `farm_weather_dashboard_path()` helper

Generated dashboard artifacts are written to the **runtime tree** (not the checkout), defaulting to:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/<farm>_weather_dashboard.html
```

The build-time Plotly.js bundle is cached under:

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/shared/assets/plotly-<version>.min.js
```

For the current Iowa fixture, the generated example dashboard is at:

```text
~/my-farm-advisor-runtime/data-pipeline/growers/northern-iowa-grower/farms/iowa-farm/iowa-farm_weather_dashboard.html
```

---

## NDVI Crop Health Monitoring Dashboard

The data-pipeline includes an offline, self-contained **NDVI-based Crop Health Monitoring Dashboard** generator. It produces two companion HTML files with embedded Plotly.js, farm/field GeoJSON data, per-field NDVI time series from Sentinel-2 composites, per-field weather-derived GDD and rainfall, soil property quadrant analysis, and an optional satellite basemap — all inlined so the files work from `file://` with zero runtime external dependencies.

### What it produces

Two companion dashboards per farm:

**1. Main Crop Health Dashboard** (`<farm-dir>/<farm-slug>_crop_health_dashboard.html`)
- Interactive Plotly map of field polygons with click-to-toggle selection and hover showing field ID + acres
- Mean NDVI Time Series chart (per-scene connected lines across all years, not yearly means)
- Rainfall chart (Daily Rainfall bars + Cumulative Rainfall line) with dual Y-axes
- Growing Degree Days chart (cumulative GDD, base 50°F) with frost-date markers
- Custom multi-select dropdowns for fields and years, with synchronized chart axes and count labels (e.g., "Fields (3/10)")
- Insight box with data-backed take-home messages (e.g., peak timing by crop, no-data fields, west-to-east spatial gradients)
- Responsive layout: two-column on desktop, stacked on narrow screens

**2. Soil-NDVI Analysis Dashboard** (`<farm-dir>/<farm-slug>_soil_ndvi_dashboard.html`)
- Two side-by-side quadrant analysis panels:
  - Mean NDVI by Percent Soil Organic Matter
  - Mean NDVI by Soil Available Water Storage (Inches)
- 10 field-level NDVI curves (all years pooled) colored by soil-NDVI quadrant:
  - **URGENT** (red): Low OM/AWS + Low NDVI → build soil health
  - **RESILIENT** (yellow): Low OM/AWS + High NDVI → maintain practice
  - **INVESTIGATE** (blue): High OM/AWS + Low NDVI → check drainage/disease
  - **EXEMPLARY** (green): High OM/AWS + High NDVI → replicate practices
- Vertical "Last Frost" reference line (computed from actual weather data, not hardcoded)
- Independent field/year dropdowns (not linked to main dashboard)

### Full-pipeline vs standalone

**Full pipeline (opt-in):**

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/run_farm_pipeline.py \
  --grower-slug <grower> \
  --farm-slug <farm> \
  --generate-crop-health-dashboard
```

The `--generate-crop-health-dashboard` flag appends dashboard generation as a final pipeline step. Both main and soil-NDVI dashboards are produced automatically. Dashboards are **not** generated by default.

**Standalone (direct generation):**
```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_crop_health_dashboard.py \
  --farm-dir <farm-dir> \
  --output <custom-path.html>
```

Standalone generation reads only existing farm outputs. It does **not** invoke weather downloads, boundary processing, satellite downloads, or any upstream pipeline stages.

### Input data sources

The generator expects these pre-computed farm outputs:

```text
<farm-dir>/
├── boundary/field_boundaries.geojson          (GeoJSON FeatureCollection, WGS84)
├── derived/tables/<farm>_weather_2021_2025.csv  (farm-level daily weather)
├── derived/tables/<farm>_ssurgo_summary.csv    (per-field soil aggregation)
├── derived/tables/<farm>_cdl_2021_2025_full_composition.csv  (crop history)
├── fields/<field-id>/
│   ├── field.json                              (per-field metadata)
│   ├── weather/daily_weather.csv                (per-field daily weather, optional)
│   ├── satellite/sentinel/manifest.json         (Sentinel-2 scene inventory)
│   └── derived/features/ndvi_year_YYYY_composite.tif  (NDVI composites)
```

### Calculated metrics

- **Per-scene NDVI time series**: Mean NDVI per Sentinel-2 scene date, connected chronologically by DOY per field-year
- **GDD (Fahrenheit)**: `dailyGdd = max((T2M_MAX + T2M_MIN) / 2 - 10.0, 0)`, then converted to °F (`GDD_F = GDD_C × 1.8`); cumulative from last frost date
- **Rainfall**: `dailyRainfallIn = PRECTOTCORR * 0.0393701`; cumulative from last frost date
- **Soil quadrants**: Median-split classification per field for OM%, AWS, and mean NDVI into Low/High buckets
- **Last frost date**: Computed dynamically from actual weather data — latest day before July 1 where `T2M_MIN <= 0.0°C`; fallback to January 1 if no frost found
- **Spatial gradient**: Pearson correlation of metrics vs. longitude/latitude for advisory insights

### Dashboard paths

Both dashboards are written to the **runtime tree** (not the checkout):

```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/<farm>_crop_health_dashboard.html
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/<farm>_soil_ndvi_dashboard.html
```

For the current Illinois fixture:

```text
~/my-farm-advisor-runtime/data-pipeline/growers/northern-illinois-grower/farms/illinois-farm/illinois-farm_crop_health_dashboard.html
~/my-farm-advisor-runtime/data-pipeline/growers/northern-illinois-grower/farms/illinois-farm/illinois-farm_soil_ndvi_dashboard.html
```

### Offline and runtime dependency guarantee

Both generated HTML files have zero runtime external dependencies:
- No CDN `<script>` or `<link>` tags
- No API calls
- No external fonts, images, tiles, or data files
- Plotly.js is downloaded once at build time, cached under `shared/assets/`, and fully inlined
- Files work when opened directly from disk via `file://`
- **Note**: Navigation between the two dashboards via hyperlink does not work over `file://` in all browsers (Chrome/Edge/Safari security restrictions). Open each file separately, or serve via local HTTP server (`python3 -m http.server`).

### Known limitations

- **Field `osm-2000000006`** (585.84 acres) has **zero Sentinel-2 scenes** across all 5 years (2021–2025) and appears in the dashboard with "No satellite imagery available" annotation
- **Per-scene NDVI availability** is determined by `satellite/sentinel/manifest.json` scene inventory, not by Sentinel-2 orbit coverage gaps
- **Companion dashboard hyperlinks** (`file://` to `file://`) are unreliable across browsers; remove hyperlinks or serve via `http://localhost`
- **Weather data** is sourced from NASA POWER point API or S3 Zarr at field centroids; spatial heterogeneity within large fields is not captured
- **GDD base temperature** is 50°F (10°C equivalent), computed from Celsius then converted — this differs from some agronomic standards that use 86°F max cap

### Implementation and file locations

The dashboard capability was added to the `my-farm-advisor/data-pipeline` sub-skill. Generator modules live in the skill checkout at:

```text
my-farm-advisor/data-pipeline/src/scripts/reporting/
├── generate_crop_health_dashboard.py   (main generator: both dashboards)
├── dashboard_assets.py                 (NDVI extraction, weather transforms, soil quadrants)
└── dashboard_html_template.py          (shared HTML/JS patterns)
```

Tests were added under:

```text
my-farm-advisor/data-pipeline/src/scripts/tests/
└── test_crop_health_dashboard.py
```

Pipeline integration is handled by:

- `my-farm-advisor/data-pipeline/src/scripts/run_farm_pipeline.py` — added `--generate-crop-health-dashboard` flag
- `my-farm-advisor/data-pipeline/src/scripts/lib/paths.py` — added `farm_crop_health_dashboard_path()` helper
