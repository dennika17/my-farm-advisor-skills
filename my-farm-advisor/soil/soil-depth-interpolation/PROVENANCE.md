# Provenance

## Data Source

- **Source**: USDA NRCS Soil Data Access (SDA) REST API
- **URL**: https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest
- **Database**: SSURGO (Soil Survey Geographic Database)
- **Coverage**: United States agricultural areas
- **Authentication**: None required (public API)

## Columns Verified

### chorizon (28 columns confirmed valid in SDA as of 2026-07-28)

`chkey`, `cokey`, `hzname`, `hzdept_r`, `hzdepb_r`, `om_r`, `ph1to1h2o_r`, `awc_r`, `claytotal_r`, `sandtotal_r`, `silttotal_r`, `dbthirdbar_r`, `cec7_r`, `kwfact`, `kffact`, `ec_r`, `wthirdbar_r`, `wfifteenbar_r`, `wsatiated_r`, `ll_r`, `pi_r`, `caco3_r`, `gypsum_r`, `sar_r`, `ksat_r`, `dbovendry_r`, `ph01mcacl2_r`, `aashind_r`

### component (20 columns confirmed valid in SDA as of 2026-07-28)

`cokey`, `mukey`, `compname`, `comppct_r`, `drainagecl`, `majcompflag`, `taxclname`, `compkind`, `otherph`, `localphase`, `slope_l`, `slope_r`, `slope_h`, `slopelenusle_r`, `runoff`, `tfact`, `wei`, `weg`, `erocl`, `earthcovkind1`, `earthcovkind2`

### Not Valid (columns referenced in legacy code but not present)

`hydgrpcd`, `engdwobdcd` — not confirmed in current SDA schema.

## Output Files

For each field, the skill produces three new files in the field's `soil/` directory
alongside the existing `ssurgo_full.csv` (which is never modified):

1. **`ssurgo_full_regenerated.csv`** — Regenerated original-format file with all
   components and all horizons, plus `cokey` and `chkey` identifiers (17 columns).
2. **`ssurgo_full_with_components.csv`** — Full raw SSURGO with all 48 columns
   including component-level attributes and all 25 chorizon numeric properties.
3. **`ssurgo_full_depth_interpolated.csv`** — Long-format depth-interpolated data
   with one row per `(mukey, depth_zone, compname)` (35 columns).

## Skill Origin

Created 2026-07-28 as a new subskill under `my-farm-advisor/soil/` to extend the
existing `ssurgo-soil` workflow with full-component, full-horizon depth interpolation.

## License

Apache-2.0
