# Soil Depth Interpolation

## Overview

This skill provides depth-interpolated soil property tables for agricultural fields
by querying the USDA NRCS Soil Data Access (SDA) API and applying standard soil-science
weighting procedures.

## What It Does

For each field boundary polygon, the skill:

1. **Queries SDA** for all map units (mukeys) intersecting the field
2. **Fetches full SSURGO data** including all components and all horizons (no depth cutoff, no `majcompflag` filter)
3. **Saves raw data** to `ssurgo_full_with_components.csv` with complete cokeys, chkeys, and all 28 chorizon attributes
4. **Computes depth interpolation** at 10 cm resolution (0-10, 10-20, ..., 90-100 cm)
5. **Saves interpolated data** to `ssurgo_full_depth_interpolated.csv`

## Output Files

Both files are created in the field's `soil/` directory, alongside the existing `ssurgo_full.csv`:

- `ssurgo_full_with_components.csv` — Raw full SSURGO with all components and horizons
- `ssurgo_full_depth_interpolated.csv` — One row per mukey per 10 cm depth slice

## Algorithm

For each map unit (mukey) in a field:

1. Collect all components and their horizon stacks
2. For each 10 cm depth slice [top, bottom):
   - Compute horizon overlap with the slice
   - Weight by component percentage (`comppct_r`)
   - Calculate weighted average for each numeric attribute
3. Use the dominant component's drainage class for categorical output

## Usage

See [GUIDE.md](GUIDE.md) for detailed CLI instructions.

## Data Source

- **USDA NRCS Soil Data Access (SDA)** REST API
- **SSURGO** (Soil Survey Geographic Database)
- No API key required

## License

Apache-2.0
