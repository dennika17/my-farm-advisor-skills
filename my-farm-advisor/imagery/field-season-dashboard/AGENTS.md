# Local Instructions

## Purpose

This folder owns the **field-season mini-dashboard** workflow for Assignment 3. It generates a single aligned dashboard image combining Sentinel-2 NDVI, daily weather (precipitation, temperature extremes), and cumulative GDD for one field and one growing season.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling imagery workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `README.md` first for the quick-start and invocation examples. Review `GUIDE.md` for the full workflow. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Command runbook

### Generate a field-season dashboard

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

Output:
```text
${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/osm-1417080803_2021_dashboard.png
```

### Example with custom GDD base temp and growing season window

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/imagery/field-season-dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021 \
  --gdd-base-temp 10.0 \
  --gs-start-doy 121 \
  --gs-end-doy 273
```

### Example with custom output directory

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/imagery/field-season-dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021 \
  --output-dir /tmp/dashboard-output
```

## Data contract

This subskill reads from the runtime data tree only. It does not write into the skill checkout.

Required runtime paths:
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/boundary/field_boundary.geojson`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/weather/daily_weather.csv`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/derived/tables/*_cdl_YYYY_YYYY_full_composition_updated.csv`
- `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/fields/<field>/satellite/sentinel/<year>/sentinel_YYYYMMDD/sentinel_YYYYMMDD_ndvi.tif`

## Output contract

All outputs go to:
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/`

Only static PNG files are produced. No interactive dashboards, no HTML, no commit to the skill checkout.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. To verify the subskill works:

```bash
export DATA_PIPELINE_DATA_ROOT=/home/coder/my-farm-advisor-runtime
cd ~/my-farm-advisor-skills/my-farm-advisor/imagery/field-season-dashboard
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  src/field_season_dashboard.py \
  --grower-slug northern-illinois-grower \
  --farm-slug illinois-farm \
  --field-id osm-1417080803 \
  --year 2021
ls ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/imagery/field-season-dashboard/output/
```

## Local-delta-only reminder

Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
