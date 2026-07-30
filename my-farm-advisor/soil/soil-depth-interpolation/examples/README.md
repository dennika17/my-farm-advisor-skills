# Soil Depth Interpolation Examples

## Example 1: Single Field (Illinois)

```bash
cd /path/to/data-pipeline/src/scripts
python /path/to/soil-depth-interpolation/src/soil_depth_interpolation.py \
    --field-geojson growers/northern-illinois-grower/farms/illinois-farm/boundary/field_boundaries.geojson \
    --output-dir growers/northern-illinois-grower/farms/illinois-farm/fields/osm-1417080803/soil \
    --field-id osm-1417080803
```

**Output:**
- `soil/ssurgo_full_regenerated.csv` — Regenerated original format with all components + all horizons + cokey/chkey
- `soil/ssurgo_full_with_components.csv` — Full SSURGO with all 48 columns
- `soil/ssurgo_full_depth_interpolated.csv` — One row per component per depth slice (e.g., 140 rows for 5 mukeys × 10 depths × ~2.8 components)

## Example 2: All Fields in a Farm

```bash
FARM_DIR="growers/northern-illinois-grower/farms/illinois-farm"
BOUNDARY="$FARM_DIR/boundary/field_boundaries.geojson"

for field_dir in "$FARM_DIR"/fields/*/; do
    field_slug=$(basename "$field_dir")
    echo "Processing $field_slug..."
    python /path/to/soil-depth-interpolation/src/soil_depth_interpolation.py \
        --field-geojson "$BOUNDARY" \
        --output-dir "$field_dir/soil" \
        --field-id "$field_slug"
done
```

## Example 3: Python API

```python
from soil_depth_interpolation import process_field

raw_df, interpolated_df = process_field(
    field_geojson=Path("field_boundaries.geojson"),
    output_dir=Path("soil/"),
    field_id="osm-1417080803",
    max_depth_cm=100,
    depth_interval_cm=10,
)

print(f"Raw rows: {len(raw_df)}")
print(f"Interpolated rows: {len(interpolated_df)}")
print(interpolated_df[["mukey", "depth_zone", "om_r", "ph1to1h2o_r", "awc_r"]].head(10))
```

## Example Output Format

### ssurgo_full_with_components.csv (first few columns)

```
field_id,mukey,muname,cokey,compname,comppct_r,drainagecl,majcompflag,...,hzdept_r,hzdepb_r,om_r,...
osm-1417080803,183894,Elpaso,26939053,Elpaso,94,Poorly drained,Yes,...,0,53,5.5,...
```

### ssurgo_full_depth_interpolated.csv

One row per `(mukey, depth_zone, compname)`. Components sorted by `comppct_r` descending.

```
field_id,mukey,depth_zone,depth_top_cm,depth_bot_cm,compname,comppct_r,drainagecl,is_dominant,n_components,om_r,ph1to1h2o_r,awc_r,...
osm-1417080803,183894,0-10cm,0,10,Elpaso,94,Poorly drained,Yes,3,5.49,6.11,0.19,...
osm-1417080803,183894,0-10cm,0,10,Harpster,4,Poorly drained,No,3,5.49,6.11,0.19,...
osm-1417080803,183894,0-10cm,0,10,Peotone,2,Very poorly drained,No,3,5.49,6.11,0.19,...
osm-1417080803,183894,10-20cm,10,20,Elpaso,94,Poorly drained,Yes,3,5.48,6.11,0.19,...
osm-1417080803,183894,10-20cm,10,20,Harpster,4,Poorly drained,No,3,5.48,6.11,0.19,...
osm-1417080803,183894,10-20cm,10,20,Peotone,2,Very poorly drained,No,3,5.48,6.11,0.19,...
...
```

Notice:
- All three components appear for every depth slice
- `comppct_r` values (94 + 4 + 2 = 100%) are the same across all depths
- Interpolated values (`om_r`, `ph1to1h2o_r`, etc.) are identical for all components in the same `(mukey, depth_zone)` because they were computed using the full weighted average
- `is_dominant` is `Yes` only for the component with the highest `comppct_r`
