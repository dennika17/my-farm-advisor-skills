# Soil Depth Interpolation Guide

## Algorithm Details

### Step 1: Fetch Full SSURGO Data

For each field boundary polygon, query the NRCS SDA API to obtain:

- **All map units** (mukeys) intersecting the field polygon
- **All components** within each map unit (not filtered by `majcompflag`)
- **All horizons** for each component (no depth cutoff)
- **All available numeric attributes** from the `chorizon` table
- **Component-level attributes** from the `component` table

### Step 2: Regenerated Output (`ssurgo_full_regenerated.csv`)

A regenerated version of the original `ssurgo_full.csv` that preserves the original
15-column structure but adds `cokey` and `chkey` for traceability, and includes
**all components** (not just major) and **all horizons** (no depth cutoff):

| Column | Description |
|--------|-------------|
| `field_id` | Field identifier |
| `mukey` | Map unit key |
| `cokey` | Component key (traceability) |
| `chkey` | Horizon key (traceability) |
| `compname` | Component name |
| `comppct_r` | Component percentage |
| `drainagecl` | Drainage class |
| `hzdept_r` | Horizon top depth |
| `hzdepb_r` | Horizon bottom depth |
| `om_r` through `cec7_r` | 10 original numeric soil properties |

### Step 3: Full Raw Output (`ssurgo_full_with_components.csv`)

The raw file contains one row per horizon with complete identifiers and all 48 columns:

| Column Group | Columns |
|--------------|---------|
| Identifiers | `field_id`, `mukey`, `muname`, `cokey`, `chkey` |
| Component | `compname`, `comppct_r`, `drainagecl`, `majcompflag`, `taxclname`, `compkind`, `otherph`, `localphase`, `slope_l`, `slope_r`, `slope_h`, `slopelenusle_r`, `runoff`, `tfact`, `wei`, `weg`, `erocl`, `earthcovkind1`, `earthcovkind2` |
| Horizon | `hzname`, `hzdept_r`, `hzdepb_r` |
| Numeric Properties | `om_r`, `ph1to1h2o_r`, `awc_r`, `claytotal_r`, `sandtotal_r`, `silttotal_r`, `dbthirdbar_r`, `cec7_r`, `kwfact`, `kffact`, `ec_r`, `wthirdbar_r`, `wfifteenbar_r`, `wsatiated_r`, `ll_r`, `pi_r`, `caco3_r`, `gypsum_r`, `sar_r`, `ksat_r`, `dbovendry_r`, `ph01mcacl2_r`, `aashind_r` |

### Step 3: Depth Interpolation

For each **mukey** and each **10 cm depth slice** (0-10, 10-20, ..., 90-100 cm):

```
overlap = max(0, min(hzdepb_r, slice_bottom) - max(hzdept_r, slice_top))
weight  = overlap * comppct_r
value   = Σ(attribute × weight) / Σ(weight)
```

The weighted average is computed **once per (mukey, depth_slice)** using all components, then repeated on every component row for that slice.

**Component columns (one row per component per depth slice):**
- `compname` — component name
- `comppct_r` — component percentage within the mukey
- `drainagecl` — drainage class of this specific component
- `is_dominant` — `Yes` if this component has the highest `comppct_r` in the mukey, otherwise `No`

Components are sorted by `comppct_r` descending (dominant first).

**Metadata columns:**
- `n_components` — number of components in the mukey
- `n_horizons` — total horizons across all components in the mukey
- `total_depth_cm` — maximum depth of any horizon in the mukey

### Step 5: Interpolated Output (`ssurgo_full_depth_interpolated.csv`)

One row per `(field_id, mukey, depth_zone, compname)`:

| Column | Description |
|--------|-------------|
| `field_id` | Field identifier |
| `mukey` | Map unit key |
| `depth_zone` | Depth slice label (e.g., "0-10cm") |
| `depth_top_cm` | Top of slice |
| `depth_bot_cm` | Bottom of slice |
| `compname` | Component name |
| `comppct_r` | Component percentage within this mukey |
| `drainagecl` | Drainage class of this component |
| `is_dominant` | `Yes` if dominant component, else `No` |
| *25 numeric attributes* | Depth-interpolated values (same for all components in same mukey × depth) |
| `n_components` | Total components in this mukey |
| `n_horizons` | Total horizons in this mukey |
| `total_depth_cm` | Maximum horizon depth |

## CLI Usage

### Basic Usage

```bash
cd /path/to/data-pipeline/src/scripts
python -m soil_depth_interpolation \
    --field-geojson growers/northern-illinois-grower/farms/illinois-farm/boundary/field_boundaries.geojson \
    --output-dir growers/northern-illinois-grower/farms/illinois-farm/fields/osm-1417080803/soil \
    --field-id osm-1417080803
```

### Batch All Fields in a Farm

```bash
for field_dir in growers/northern-illinois-grower/farms/illinois-farm/fields/*/; do
    field_slug=$(basename "$field_dir")
    python -m soil_depth_interpolation \
        --field-geojson growers/northern-illinois-grower/farms/illinois-farm/boundary/field_boundaries.geojson \
        --output-dir "$field_dir/soil" \
        --field-id "$field_slug"
done
```

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--field-geojson` | required | Path to field boundaries GeoJSON |
| `--output-dir` | required | Path to field's `soil/` directory |
| `--field-id` | required | Field ID to process |
| `--max-depth-cm` | 100 | Maximum depth for interpolation |
| `--depth-interval-cm` | 10 | Depth slice interval |
| `--sda-timeout` | 120 | SDA API timeout in seconds |

## Notes

- The existing `ssurgo_full.csv` is **never modified or removed**
- Three new files are created in the same `soil/` directory:
  1. `ssurgo_full_regenerated.csv` — All components + all horizons, original format + identifiers
  2. `ssurgo_full_with_components.csv` — Full raw data with all 48 columns
  3. `ssurgo_full_depth_interpolated.csv` — Long-format depth-interpolated
- Works for any field in any SSURGO-covered state (IL, IA, NE, and beyond)
- SDA API is free and requires no authentication
- Large fields with many mukeys may take 30-60 seconds per query
