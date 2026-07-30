#!/usr/bin/env python3
"""Soil depth interpolation for USDA NRCS SSURGO data.

This module provides functions to:
1. Fetch full SSURGO data (all components, all horizons, no filters)
2. Save raw full data with complete cokeys, chkeys, and all attributes
3. Compute depth-interpolated soil properties at 10 cm resolution (0-100 cm)
4. Weight values by horizon overlap and component percentage

Usage:
    python soil_depth_interpolation.py \
        --field-geojson field_boundaries.geojson \
        --output-dir soil/ \
        --field-id osm-1417080803
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"

# Valid chorizon numeric columns confirmed against SDA (2026-07-28)
CHORIZON_NUMERIC_COLS = [
    "hzdept_r",
    "hzdepb_r",
    "om_r",
    "ph1to1h2o_r",
    "awc_r",
    "claytotal_r",
    "sandtotal_r",
    "silttotal_r",
    "dbthirdbar_r",
    "cec7_r",
    "kwfact",
    "kffact",
    "ec_r",
    "wthirdbar_r",
    "wfifteenbar_r",
    "wsatiated_r",
    "ll_r",
    "pi_r",
    "caco3_r",
    "gypsum_r",
    "sar_r",
    "ksat_r",
    "dbovendry_r",
    "ph01mcacl2_r",
    "aashind_r",
]

# Component text/identifier columns
COMPONENT_ID_COLS = [
    "cokey",
    "compname",
    "drainagecl",
    "majcompflag",
    "taxclname",
    "compkind",
    "otherph",
    "localphase",
    "erocl",
    "earthcovkind1",
    "earthcovkind2",
]

# Component numeric columns
COMPONENT_NUMERIC_COLS = [
    "comppct_r",
    "slope_l",
    "slope_r",
    "slope_h",
    "slopelenusle_r",
    "runoff",
    "tfact",
    "wei",
    "weg",
]

# All columns for the raw full output
RAW_OUTPUT_COLS = (
    ["field_id", "mukey", "muname"]
    + COMPONENT_ID_COLS
    + COMPONENT_NUMERIC_COLS
    + ["chkey", "hzname"]
    + CHORIZON_NUMERIC_COLS
)

# Columns for the interpolated output (one row per component per depth slice)
INTERPOLATED_ID_COLS = [
    "field_id",
    "mukey",
    "depth_zone",
    "depth_top_cm",
    "depth_bot_cm",
    "compname",
    "comppct_r",
    "drainagecl",
    "is_dominant",
]

INTERPOLATED_NUMERIC_COLS = CHORIZON_NUMERIC_COLS[2:]  # Exclude hzdept_r, hzdepb_r

INTERPOLATED_META_COLS = [
    "n_components",
    "n_horizons",
    "total_depth_cm",
]


def query_sda(sql: str, timeout: int = 120) -> list[list[Any]]:
    """Execute SQL query against NRCS SDA REST API.

    Args:
        sql: SQL query string.
        timeout: Request timeout in seconds.

    Returns:
        List of result rows (each row is a list of values).
    """
    response = requests.post(
        SDA_URL,
        data={"query": sql, "format": "JSON"},
        timeout=timeout,
    )
    response.raise_for_status()
    result = response.json()
    return result.get("Table", [])


def build_full_ssurgo_query(wkt: str) -> str:
    """Build SQL query for full SSURGO data (all components, all horizons).

    Args:
        wkt: WKT geometry string (polygon) in WGS84.

    Returns:
        SQL query string.
    """
    chorizon_cols = ", ".join(f"ch.{c}" for c in CHORIZON_NUMERIC_COLS)
    component_id_cols = ", ".join(f"c.{c}" for c in COMPONENT_ID_COLS)
    component_numeric_cols = ", ".join(f"c.{c}" for c in COMPONENT_NUMERIC_COLS)

    sql = f"""
    SELECT
        mu.mukey,
        mu.muname,
        {component_id_cols},
        {component_numeric_cols},
        ch.chkey,
        ch.hzname,
        {chorizon_cols}
    FROM mapunit mu
    INNER JOIN component c ON mu.mukey = c.mukey
    LEFT JOIN chorizon ch ON c.cokey = ch.cokey
    WHERE mu.mukey IN (
        SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('{wkt}')
    )
    ORDER BY mu.mukey, c.comppct_r DESC, ch.hzdept_r ASC
    """
    return sql


def fetch_full_ssurgo_for_field(
    field_wkt: str,
    field_id: str,
    timeout: int = 120,
) -> pd.DataFrame:
    """Fetch full SSURGO data for a single field.

    Args:
        field_wkt: WKT polygon string in WGS84.
        field_id: Field identifier.
        timeout: SDA API timeout.

    Returns:
        DataFrame with full SSURGO data. Empty if no data found.
    """
    sql = build_full_ssurgo_query(field_wkt)
    rows = query_sda(sql, timeout=timeout)

    if not rows:
        return pd.DataFrame(columns=RAW_OUTPUT_COLS)

    # Build column names matching SELECT order
    columns = (
        ["mukey", "muname"]
        + COMPONENT_ID_COLS
        + COMPONENT_NUMERIC_COLS
        + ["chkey", "hzname"]
        + CHORIZON_NUMERIC_COLS
    )

    df = pd.DataFrame(rows, columns=columns)
    df.insert(0, "field_id", field_id)

    # Convert numeric columns
    all_numeric = COMPONENT_NUMERIC_COLS + CHORIZON_NUMERIC_COLS
    for col in all_numeric:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def write_ssurgo_full_with_components(df: pd.DataFrame, output_path: Path) -> None:
    """Write raw full SSURGO data to CSV.

    Args:
        df: DataFrame with full SSURGO data.
        output_path: Path for output CSV.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


def interpolate_soil_depths(
    df: pd.DataFrame,
    max_depth_cm: int = 100,
    depth_interval_cm: int = 10,
) -> pd.DataFrame:
    """Compute depth-interpolated soil properties in long format.

    For each mukey and depth slice, outputs one row per component.
    Interpolated values are computed once per (mukey, depth_slice) using
    all components, then repeated on every component row.
    Components are sorted by comppct_r descending (dominant first).

    Args:
        df: DataFrame with full SSURGO data.
        max_depth_cm: Maximum depth for interpolation.
        depth_interval_cm: Depth slice interval in cm.

    Returns:
        DataFrame with one row per (field_id, mukey, depth_zone, compname).
    """
    if df.empty:
        return pd.DataFrame(columns=INTERPOLATED_ID_COLS + INTERPOLATED_NUMERIC_COLS + INTERPOLATED_META_COLS)

    results = []

    for field_id in df["field_id"].unique():
        field_data = df[df["field_id"] == field_id].copy()

        for mukey in field_data["mukey"].unique():
            mukey_data = field_data[field_data["mukey"] == mukey].copy()

            # Get unique components sorted by comppct_r descending
            components = (
                mukey_data.groupby("cokey", as_index=False)
                .agg({
                    "compname": "first",
                    "comppct_r": "first",
                    "drainagecl": "first",
                })
                .sort_values("comppct_r", ascending=False)
                .reset_index(drop=True)
            )

            # Component and horizon counts
            n_components = len(components)
            n_horizons = mukey_data["chkey"].notna().sum()
            total_depth_cm = mukey_data["hzdepb_r"].max()

            # Generate depth slices
            for top in range(0, max_depth_cm, depth_interval_cm):
                bot = top + depth_interval_cm
                depth_zone = f"{top}-{bot}cm"

                # Compute weighted averages for this slice (once per mukey x depth)
                slice_values: dict[str, float] = {}
                total_weight = 0.0

                for _, row in mukey_data.iterrows():
                    comp_weight = row["comppct_r"] / 100.0 if pd.notna(row["comppct_r"]) else 0.0
                    hz_top = row["hzdept_r"]
                    hz_bot = row["hzdepb_r"]

                    # Skip if no horizon data
                    if pd.isna(hz_top) or pd.isna(hz_bot):
                        continue

                    # Compute overlap
                    overlap_top = max(float(hz_top), float(top))
                    overlap_bot = min(float(hz_bot), float(bot))
                    overlap = max(0.0, overlap_bot - overlap_top)

                    if overlap > 0 and comp_weight > 0:
                        slice_weight = overlap * comp_weight
                        total_weight += slice_weight

                        for attr in INTERPOLATED_NUMERIC_COLS:
                            val = row[attr]
                            if pd.notna(val):
                                slice_values[attr] = slice_values.get(attr, 0.0) + float(val) * slice_weight

                # Normalize by total weight
                if total_weight > 0:
                    for attr in slice_values:
                        slice_values[attr] = slice_values[attr] / total_weight

                # Output one row per component
                for idx, comp in components.iterrows():
                    result: dict[str, Any] = {
                        "field_id": field_id,
                        "mukey": mukey,
                        "depth_zone": depth_zone,
                        "depth_top_cm": top,
                        "depth_bot_cm": bot,
                        "compname": comp["compname"],
                        "comppct_r": comp["comppct_r"],
                        "drainagecl": comp["drainagecl"],
                        "is_dominant": "Yes" if idx == 0 else "No",
                        "n_components": n_components,
                        "n_horizons": n_horizons,
                        "total_depth_cm": total_depth_cm,
                    }

                    for attr in INTERPOLATED_NUMERIC_COLS:
                        result[attr] = slice_values.get(attr, None)

                    results.append(result)

    return pd.DataFrame(results)


def write_ssurgo_depth_interpolated(df: pd.DataFrame, output_path: Path) -> None:
    """Write depth-interpolated data to CSV.

    Args:
        df: DataFrame with interpolated data.
        output_path: Path for output CSV.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)


# Columns matching the original ssurgo_full.csv + cokey/chkey for traceability
REGENERATED_COLS = [
    "field_id",
    "mukey",
    "cokey",
    "chkey",
    "compname",
    "comppct_r",
    "drainagecl",
    "hzdept_r",
    "hzdepb_r",
    "om_r",
    "ph1to1h2o_r",
    "awc_r",
    "claytotal_r",
    "sandtotal_r",
    "silttotal_r",
    "dbthirdbar_r",
    "cec7_r",
]


def write_ssurgo_full_regenerated(df: pd.DataFrame, output_path: Path) -> None:
    """Write regenerated ssurgo_full.csv with all components and horizons.

    Uses the same column structure as the original ssurgo_full.csv
    but adds cokey and chkey for traceability, and includes all
    components (not just major) and all horizons (no depth cutoff).

    Args:
        df: DataFrame with full SSURGO data from fetch_full_ssurgo_for_field().
        output_path: Path for output CSV.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    available_cols = [c for c in REGENERATED_COLS if c in df.columns]
    df[available_cols].to_csv(output_path, index=False)


def process_field(
    field_geojson: Path,
    output_dir: Path,
    field_id: str,
    max_depth_cm: int = 100,
    depth_interval_cm: int = 10,
    timeout: int = 120,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process a single field: fetch full SSURGO and compute depth interpolation.

    Args:
        field_geojson: Path to field boundaries GeoJSON.
        output_dir: Field's soil directory.
        field_id: Field identifier to process.
        max_depth_cm: Maximum depth for interpolation.
        depth_interval_cm: Depth slice interval.
        timeout: SDA API timeout.

    Returns:
        Tuple of (raw_df, interpolated_df).
    """
    # Load field boundaries
    fields = gpd.read_file(field_geojson)
    if fields.empty:
        raise ValueError(f"No fields found in {field_geojson}")

    # Find the target field
    field_match = fields[fields["field_id"].astype(str) == str(field_id)]
    if field_match.empty:
        raise ValueError(f"Field ID '{field_id}' not found in {field_geojson}")

    # Convert to WGS84 and get WKT
    field_wgs84 = field_match.to_crs(epsg=4326)
    field_wkt = field_wgs84.geometry.iloc[0].wkt

    print(f"Fetching full SSURGO for field {field_id}...")
    raw_df = fetch_full_ssurgo_for_field(field_wkt, field_id, timeout=timeout)

    if raw_df.empty:
        print(f"  No SSURGO data found for field {field_id}")
        return raw_df, pd.DataFrame()

    print(f"  Retrieved {len(raw_df)} horizon records for {raw_df['mukey'].nunique()} mukeys")

    # Write raw full file
    raw_path = output_dir / "ssurgo_full_with_components.csv"
    write_ssurgo_full_with_components(raw_df, raw_path)
    print(f"  Saved raw full data: {raw_path}")

    # Write regenerated file (original format + cokey/chkey, all components, all horizons)
    regenerated_path = output_dir / "ssurgo_full_regenerated.csv"
    write_ssurgo_full_regenerated(raw_df, regenerated_path)
    print(f"  Saved regenerated data: {regenerated_path}")

    # Compute depth interpolation
    print(f"Computing depth interpolation (0-{max_depth_cm} cm, {depth_interval_cm} cm slices)...")
    interpolated_df = interpolate_soil_depths(raw_df, max_depth_cm, depth_interval_cm)

    # Write interpolated file
    interpolated_path = output_dir / "ssurgo_full_depth_interpolated.csv"
    write_ssurgo_depth_interpolated(interpolated_df, interpolated_path)
    print(f"  Saved interpolated data: {interpolated_path}")
    n_mukeys = interpolated_df['mukey'].nunique()
    n_depths = interpolated_df['depth_zone'].nunique()
    n_components = interpolated_df['compname'].nunique()
    print(f"  {len(interpolated_df)} rows ({n_mukeys} mukeys × {n_depths} depth slices × ~{len(interpolated_df)//max(1, n_mukeys * n_depths)} components)")

    return raw_df, interpolated_df


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch full SSURGO data and compute depth-interpolated soil properties."
    )
    parser.add_argument(
        "--field-geojson",
        required=True,
        type=Path,
        help="Path to field boundaries GeoJSON file",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Path to field's soil output directory",
    )
    parser.add_argument(
        "--field-id",
        required=True,
        help="Field ID to process",
    )
    parser.add_argument(
        "--max-depth-cm",
        type=int,
        default=100,
        help="Maximum depth for interpolation in cm (default: 100)",
    )
    parser.add_argument(
        "--depth-interval-cm",
        type=int,
        default=10,
        help="Depth slice interval in cm (default: 10)",
    )
    parser.add_argument(
        "--sda-timeout",
        type=int,
        default=120,
        help="SDA API timeout in seconds (default: 120)",
    )
    args = parser.parse_args()

    if not args.field_geojson.exists():
        print(f"ERROR: Field GeoJSON not found: {args.field_geojson}", file=sys.stderr)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    try:
        process_field(
            field_geojson=args.field_geojson,
            output_dir=args.output_dir,
            field_id=args.field_id,
            max_depth_cm=args.max_depth_cm,
            depth_interval_cm=args.depth_interval_cm,
            timeout=args.sda_timeout,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
