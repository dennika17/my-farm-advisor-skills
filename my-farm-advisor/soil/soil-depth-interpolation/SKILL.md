---
name: soil-depth-interpolation
description: >
  Fetch full USDA SSURGO soil profiles (all components, all horizons) and compute
  depth-interpolated soil properties at 10 cm resolution from 0 to 100 cm.
  Produces two files per field: a raw full SSURGO table and a depth-interpolated table.
license: Apache-2.0
metadata:
  author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  version: "1.0.0"
  skill-author: Clayton Young / Superior Byte Works, LLC (@borealBytes)
  skill-version: "1.0.0"
---

# Soil Depth Interpolation

**Domain:** Agricultural Soil Science & SSURGO Data Processing
**License:** Apache-2.0
**Attribution:** Superior Byte Works LLC / borealBytes

---

## Purpose

Use this skill when you need depth-interpolated soil properties for agricultural fields
from USDA NRCS SSURGO data. Unlike the standard `ssurgo-soil` skill which returns the
dominant component's top horizon, this skill:

1. Fetches **all components** and **all horizons** for every map unit in a field
2. Saves the raw full SSURGO data with complete component and horizon stacks
3. Computes **depth-interpolated values** at 10 cm slices (0-10, 10-20, ..., 90-100 cm)
4. Weights values by **horizon overlap** and **component percentage**

## When to Use This Workflow

- **Full soil profiles**: Need all components and horizons, not just the dominant one
- **Depth-interpolated analysis**: Need soil properties at standard depth slices
- **Multi-component weighting**: Need weighted averages across all components in a map unit
- **Soil modeling**: Input for crop growth models, hydrology models, or fertility recommendations
- **Cross-field comparison**: Standardized depth slices enable comparison across fields

## Start Here

- [Usage Guide](GUIDE.md) - Algorithm details, CLI usage, and examples
- [Examples](examples/README.md) - Sample invocations and output format

## Routing Notes

- This skill is a **standalone script** run on-demand, not integrated into the main farm pipeline
- It creates two new files next to the existing `ssurgo_full.csv` without modifying it
- Works for any field boundary in Illinois, Iowa, Nebraska, or any SSURGO-covered area

## Dependencies

- Python 3.10+
- `geopandas`, `pandas`, `requests`
- Internet access to NRCS Soil Data Access (SDA) API
