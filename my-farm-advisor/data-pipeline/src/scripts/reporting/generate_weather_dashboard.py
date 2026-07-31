#!/usr/bin/env python3
"""Generate an offline, self-contained Grower Field Weather Dashboard HTML file.

Usage (standalone):
    python scripts/reporting/generate_weather_dashboard.py \
        --farm-dir ~/my-farm-advisor-runtime/data-pipeline/growers/<grower>/farms/<farm>

    python scripts/reporting/generate_weather_dashboard.py --no-basemap
    python scripts/reporting/generate_weather_dashboard.py --output /path/to/out.html

Usage (from pipeline):
    This script is idempotent and only reads existing farm outputs. It does not
    download weather, boundaries, or any upstream data.

Environment:
    DATA_PIPELINE_DATA_ROOT — required runtime root.
    AG_GROWER_SLUG / AG_FARM_SLUG — default grower/farm when using discovery.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import pandas as pd
import shapely

# Ensure scripts dir is on path before importing bootstrap_runtime
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from bootstrap_runtime import ensure_runtime_environment

ensure_runtime_environment()

from lib.paths import (
    DATA_ROOT,
    GROWERS_ROOT,
    farm_dashboards_dir,
    farm_dir,
)
from lib.runtime_paths import resolve_runtime_paths

_RUNTIME_PATHS = resolve_runtime_paths()
_SCRIPTS = _RUNTIME_PATHS.runtime_scripts
_LIB = _RUNTIME_PATHS.runtime_scripts / "lib"
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_LIB))

from dashboard_assets import (
    _PLOTLY_VERSION,
    compute_mercator_extent,
    fetch_basemap_image,
    get_plotly_bundle,
    image_to_base64,
    wgs84_to_mercator,
)
from dashboard_html_template import build_html

_DEFAULT_GROWER = os.environ.get("AG_GROWER_SLUG", "default-grower")
_DEFAULT_FARM = os.environ.get("AG_FARM_SLUG", "default-farm")

_COLORBLIND_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]


def _print(*args: Any, **kwargs: Any) -> None:
    print(*args, **kwargs)


def _resolve_farm_dir(args: argparse.Namespace) -> Path:
    """Resolve farm directory using precedence: explicit arg > growers-dir > auto-discovery."""
    if args.farm_dir:
        path = Path(args.farm_dir).expanduser().resolve(strict=False)
        return _validate_farm_dir(path)

    if args.growers_dir:
        growers_path = Path(args.growers_dir).expanduser().resolve(strict=False)
        return _discover_single_farm(growers_path)

    # Try environment variables for runtime root
    runtime_root = _RUNTIME_PATHS.runtime_base
    if runtime_root.exists():
        growers = runtime_root / "growers"
        if growers.exists():
            try:
                return _discover_single_farm(growers)
            except RuntimeError:
                pass

    # Auto-discovery under home directory
    home = Path.home()
    candidates: list[Path] = []
    for child in home.iterdir():
        if not child.is_dir():
            continue
        growers = child / "data-pipeline" / "growers"
        if growers.exists():
            try:
                candidates.append(_discover_single_farm(growers))
            except RuntimeError:
                pass

    if not candidates:
        raise RuntimeError(
            "No valid farm directory found.\n"
            "Suggestions:\n"
            "  1. Provide --farm-dir explicitly.\n"
            "  2. Provide --growers-dir to search under a specific growers root.\n"
            "  3. Ensure a farm directory contains boundary/field_boundaries.geojson and fields/."
        )
    if len(candidates) == 1:
        return candidates[0]

    lines = [f"  {i+1}. {c}" for i, c in enumerate(candidates)]
    raise RuntimeError(
        f"Multiple valid farm directories discovered; please select one with --farm-dir:\n"
        + "\n".join(lines)
    )


def _validate_farm_dir(path: Path) -> Path:
    path = path.resolve(strict=False)
    if not path.exists():
        raise RuntimeError(f"Farm directory does not exist: {path}")
    boundary = path / "boundary" / "field_boundaries.geojson"
    if not boundary.exists():
        raise RuntimeError(
            f"Farm directory missing required boundary file: {boundary}\n"
            f"Provide a valid farm output directory."
        )
    fields_dir = path / "fields"
    if not fields_dir.exists():
        raise RuntimeError(
            f"Farm directory missing required fields/ subdirectory: {fields_dir}"
        )
    return path


def _discover_single_farm(growers_path: Path) -> Path:
    """Search growers_path for exactly one valid farm directory."""
    farms: list[Path] = []
    if not growers_path.exists():
        raise RuntimeError(f"Growers directory does not exist: {growers_path}")
    for grower_dir in sorted(growers_path.iterdir()):
        if not grower_dir.is_dir():
            continue
        farms_dir = grower_dir / "farms"
        if not farms_dir.exists():
            continue
        for farm_dir in sorted(farms_dir.iterdir()):
            if not farm_dir.is_dir():
                continue
            try:
                _validate_farm_dir(farm_dir)
                farms.append(farm_dir)
            except RuntimeError:
                continue
    if not farms:
        raise RuntimeError(f"No valid farm directories under {growers_path}")
    if len(farms) > 1:
        lines = [f"  {i+1}. {f}" for i, f in enumerate(farms)]
        raise RuntimeError(
            f"Multiple farms found under {growers_path}; select one with --farm-dir:\n"
            + "\n".join(lines)
        )
    return farms[0]


def _load_farm_json(farm_dir: Path) -> dict[str, Any]:
    path = farm_dir / "farm.json"
    if path.exists():
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    return {}


def _load_field_metadata(field_dir: Path) -> dict[str, Any]:
    path = field_dir / "field.json"
    if path.exists():
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    return {}


def _load_geojson_fields(boundary_path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(boundary_path)
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    return gdf


def _resolve_field_id_from_feature(props: dict[str, Any]) -> str:
    """Resolve stable field ID from GeoJSON feature properties using project conventions."""
    for key in ("field_id", "Field_ID", "fieldId", "id", "ID"):
        val = props.get(key)
        if val is not None:
            return str(val)
    return ""


def _parse_weather_csv(weather_path: Path) -> pd.DataFrame | None:
    """Parse a daily_weather.csv. Return None if file missing or header-only."""
    if not weather_path.exists():
        return None
    # Quick check for header-only or empty
    text = weather_path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) <= 1:
        return None
    try:
        df = pd.read_csv(weather_path, parse_dates=["date"])
    except Exception:
        # Try to infer date column
        try:
            df = pd.read_csv(weather_path)
        except Exception:
            return None
    # Strip whitespace from column names to tolerate spaces-after-commas CSVs
    df.columns = [str(c).strip() for c in df.columns]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _process_weather_for_field_year(df: pd.DataFrame, field_id: str, year: int) -> dict[str, Any] | None:
    """Process weather data for a single field-year.

    Returns a weather record dict with daily entries from last frost onward,
    or None if no usable data.
    """
    if df is None or df.empty:
        return None

    # Ensure required columns exist (case-insensitive fallback)
    col_map: dict[str, str] = {}
    for c in df.columns:
        col_map[c.lower()] = c

    tmin_col = col_map.get("t2m_min", "T2M_MIN")
    tmax_col = col_map.get("t2m_max", "T2M_MAX")
    precip_col = col_map.get("prectotcorr", "PRECTOTCORR")
    date_col = col_map.get("date", "date")

    for req in (tmin_col, tmax_col, precip_col, date_col):
        if req not in df.columns:
            return None

    # Filter to the requested year
    df = df.copy()
    df["_year"] = df[date_col].dt.year
    year_df = df[df["_year"] == year].copy()
    if year_df.empty:
        return None

    # Sort chronologically
    year_df = year_df.sort_values(date_col).reset_index(drop=True)

    # Drop rows with missing required values
    year_df = year_df.dropna(subset=[tmin_col, tmax_col, precip_col, date_col])
    if year_df.empty:
        return None

    # Determine last frost: latest day before July 1 where T2M_MIN <= 0.0
    pre_july = year_df[year_df[date_col].dt.dayofyear < 183].copy()
    frost_candidates = pre_july[pre_july[tmin_col] <= 0.0]
    if not frost_candidates.empty:
        last_frost_row = frost_candidates.iloc[-1]
        last_frost_date = last_frost_row[date_col]
        last_frost_doy = int(last_frost_row[date_col].dayofyear)
    else:
        last_frost_date = pd.Timestamp(year=year, month=1, day=1)
        last_frost_doy = 1

    # Build daily records from last frost onward
    after_frost = year_df[year_df[date_col] >= last_frost_date].copy()
    if after_frost.empty:
        return None

    daily_records: list[dict[str, Any]] = []
    cum_gdd = 0.0
    cum_rain = 0.0
    for _, row in after_frost.iterrows():
        tmin = float(row[tmin_col])
        tmax = float(row[tmax_col])
        precip_mm = float(row[precip_col])
        daily_gdd = max((tmax + tmin) / 2.0 - 10.0, 0.0)
        cum_gdd += daily_gdd
        daily_rain_in = precip_mm * 0.0393701
        cum_rain += daily_rain_in
        daily_records.append({
            "date": row[date_col].strftime("%Y-%m-%d"),
            "dayOfYear": int(row[date_col].dayofyear),
            "dailyGdd": round(daily_gdd, 2),
            "cumulativeGdd": round(cum_gdd, 2),
            "dailyRainfallIn": round(daily_rain_in, 2),
            "cumulativeRainfallIn": round(cum_rain, 2),
        })

    return {
        "fieldId": field_id,
        "year": year,
        "lastFrostDate": last_frost_date.strftime("%Y-%m-%d"),
        "lastFrostDoy": last_frost_doy,
        "daily": daily_records,
    }


def _compute_mercator_polygons(geometry: shapely.geometry.base.BaseGeometry) -> list[list[list[float]]]:
    """Convert a shapely geometry to a list of Mercator polygon rings."""
    polygons: list[list[list[float]]] = []
    if geometry is None:
        return polygons

    if geometry.geom_type == "Polygon":
        rings = [list(geometry.exterior.coords)]
        for interior in geometry.interiors:
            rings.append(list(interior.coords))
        merc_rings: list[list[list[float]]] = []
        for ring in rings:
            merc_ring = [[wgs84_to_mercator(lon, lat)[0], wgs84_to_mercator(lon, lat)[1]] for lon, lat in ring]
            merc_rings.append(merc_ring)
        polygons.extend(merc_rings)
    elif geometry.geom_type == "MultiPolygon":
        for poly in geometry.geoms:
            rings = [list(poly.exterior.coords)]
            for interior in poly.interiors:
                rings.append(list(interior.coords))
            merc_rings = []
            for ring in rings:
                merc_ring = [[wgs84_to_mercator(lon, lat)[0], wgs84_to_mercator(lon, lat)[1]] for lon, lat in ring]
                merc_rings.append(merc_ring)
            polygons.extend(merc_rings)
    return polygons


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an offline self-contained Grower Field Weather Dashboard HTML file."
    )
    parser.add_argument(
        "--farm-dir",
        default=None,
        help="Direct path to a farm output directory",
    )
    parser.add_argument(
        "--growers-dir",
        default=None,
        help="Path to the growers root directory (used for auto-discovery)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Explicit output HTML path (default: <farm-dir>/<farm-slug>_weather_dashboard.html)",
    )
    parser.add_argument(
        "--no-basemap",
        action="store_true",
        help="Skip satellite basemap acquisition; produce a neutral-background dashboard",
    )
    parser.add_argument(
        "--plotly-version",
        default=_PLOTLY_VERSION,
        help=f"Plotly.js version to inline (default: {_PLOTLY_VERSION})",
    )
    args = parser.parse_args()

    _print("=" * 60)
    _print("Grower Field Weather Dashboard Generator")
    _print("=" * 60)

    # Resolve farm directory
    try:
        farm_path = _resolve_farm_dir(args)
    except RuntimeError as exc:
        _print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    _print(f"Farm directory: {farm_path}")

    # Determine farm identity from path
    farm_slug = farm_path.name
    grower_slug = farm_path.parents[1].name

    # Load farm metadata
    farm_json = _load_farm_json(farm_path)
    farm_name = farm_json.get("display_name") or farm_slug.replace("-", " ").title()

    # Load boundary GeoJSON
    boundary_path = farm_path / "boundary" / "field_boundaries.geojson"
    fields_gdf = _load_geojson_fields(boundary_path)

    # Build field data model
    fields_dir = farm_path / "fields"
    fields_data: list[dict[str, Any]] = []
    weather_by_field_year: list[dict[str, Any]] = []
    total_weather_records = 0
    skipped_fields: list[str] = []

    for _, frow in fields_gdf.iterrows():
        props = dict(frow) if hasattr(frow, "keys") else {}
        raw_geom = frow.geometry
        field_id = _resolve_field_id_from_feature(props)
        if not field_id:
            _print(f"  [WARN] Skipping feature with no field_id in properties")
            continue

        # Validate geometry
        if raw_geom is None or raw_geom.is_empty:
            _print(f"  [WARN] Skipping field {field_id}: invalid/empty geometry")
            skipped_fields.append(field_id)
            continue

        # Load field metadata
        field_slug = field_id.replace("_", "-").lower()
        field_dir_path = fields_dir / field_slug
        if not field_dir_path.exists():
            # Try exact field_id as directory name
            field_dir_path = fields_dir / field_id
        meta = _load_field_metadata(field_dir_path)
        display_name = meta.get("display_name") or field_id
        acres = float(props.get("area_acres", 0.0)) if "area_acres" in props else 0.0

        # Compute mercator polygons
        merc_polys = _compute_mercator_polygons(raw_geom)

        # Load weather
        weather_path = field_dir_path / "weather" / "daily_weather.csv"
        weather_df = _parse_weather_csv(weather_path)
        has_weather = weather_df is not None and not weather_df.empty

        available_years: list[int] = []
        if weather_df is not None and not weather_df.empty:
            if "date" in weather_df.columns:
                try:
                    available_years = sorted(weather_df["date"].dt.year.dropna().unique().astype(int).tolist())
                except Exception:
                    pass
            elif "year" in weather_df.columns:
                try:
                    available_years = sorted(weather_df["year"].dropna().unique().astype(int).tolist())
                except Exception:
                    pass

        field_color = _COLORBLIND_PALETTE[len(fields_data) % len(_COLORBLIND_PALETTE)]
        fields_data.append({
            "fieldId": field_id,
            "fieldName": display_name,
            "acres": round(acres, 2),
            "color": field_color,
            "mercatorPolygons": merc_polys,
            "hasWeatherData": has_weather,
            "availableYears": available_years,
        })

        # Process each year of weather data
        if weather_df is not None and not weather_df.empty:
            years = available_years
            for year in years:
                record = _process_weather_for_field_year(weather_df, field_id, year)
                if record and record.get("daily"):
                    weather_by_field_year.append(record)
                    total_weather_records += len(record["daily"])

    n_fields = len(fields_data)
    n_combos = len(weather_by_field_year)
    _print(f"Fields discovered: {n_fields}")
    _print(f"Field-year weather combos: {n_combos}")
    _print(f"Total daily weather records: {total_weather_records}")
    if skipped_fields:
        _print(f"Skipped fields (invalid geometry): {', '.join(skipped_fields)}")

    if n_fields == 0:
        _print("[ERROR] No valid fields found. Check the boundary GeoJSON.", file=sys.stderr)
        sys.exit(1)

    # Build basemap
    basemap_b64 = ""
    basemap_available = False
    basemap_status = ""
    if not args.no_basemap:
        try:
            valid_geoms = [frow.geometry for _, frow in fields_gdf.iterrows() if frow.geometry and not frow.geometry.is_empty]
            if valid_geoms:
                extent = compute_mercator_extent(valid_geoms, buffer_pct=0.15)
                img, status = fetch_basemap_image(extent, no_basemap=False)
                basemap_status = status
                if img is not None:
                    basemap_b64 = image_to_base64(img)
                    basemap_available = True
                    _print(f"Basemap: {status}")
                else:
                    _print(f"Basemap unavailable: {status}")
            else:
                basemap_status = "no valid geometries"
                _print("Basemap unavailable: no valid geometries")
        except Exception as exc:
            basemap_status = f"error ({exc})"
            _print(f"Basemap error: {exc}")
    else:
        basemap_status = "skipped (--no-basemap)"
        _print("Basemap: skipped (--no-basemap)")

    # Download Plotly bundle
    try:
        plotly_bundle = get_plotly_bundle()
        _print("Plotly bundle: cached/loaded")
    except Exception as exc:
        _print(f"[ERROR] Failed to load Plotly bundle: {exc}", file=sys.stderr)
        sys.exit(1)

    # Serialize embedded data
    fields_json = json.dumps(fields_data, sort_keys=False)
    weather_json = json.dumps(weather_by_field_year, sort_keys=False)

    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    # Build HTML
    no_basemap_note = ""
    if not basemap_available:
        no_basemap_note = f"Satellite imagery unavailable ({basemap_status}). Using neutral map background."

    html = build_html(
        farm_id=farm_slug,
        farm_name=farm_name,
        generated_at=generated_at,
        basemap_available=basemap_available,
        basemap_b64=basemap_b64,
        fields_json=fields_json,
        weather_json=weather_json,
        plotly_bundle=plotly_bundle,
        no_basemap_note=no_basemap_note,
    )

    # Determine output path
    if args.output:
        output_path = Path(args.output).expanduser().resolve(strict=False)
    else:
        output_path = farm_path / f"{farm_slug}_weather_dashboard.html"

    # Atomic write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(".tmp")
    temp_path.write_text(html, encoding="utf-8")
    shutil.move(str(temp_path), str(output_path))

    size_kb = output_path.stat().st_size / 1024
    _print(f"✓ Dashboard saved → {output_path}")
    _print(f"  Size: {size_kb:.0f} KB")
    _print(f"  Fields: {n_fields}")
    _print(f"  Weather-bearing field-year combos: {n_combos}")
    _print("=" * 60)


if __name__ == "__main__":
    main()
