#!/usr/bin/env python3
"""Generate an offline, self-contained NDVI-based Crop Health Monitoring Dashboard HTML file.

Usage (standalone):
    python scripts/reporting/generate_crop_health_dashboard.py \
        --farm-dir ~/my-farm-advisor-runtime/data-pipeline/growers/<grower>/farms/<farm>

    python scripts/reporting/generate_crop_health_dashboard.py --no-basemap
    python scripts/reporting/generate_crop_health_dashboard.py --output /path/to/out.html

Usage (from pipeline):
    This script is idempotent and only reads existing farm outputs. It does not
    download weather, boundaries, satellite imagery, or any upstream data.

Environment:
    DATA_PIPELINE_DATA_ROOT — required runtime root.
    AG_GROWER_SLUG / AG_FARM_SLUG — default grower/farm when using discovery.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
import numpy as np
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
    farm_crop_health_dashboard_path,
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
    build_neutral_basemap_image,
    compute_daily_gdd,
    compute_weather_transforms,
    compute_mercator_extent,
    extract_ndvi_from_composite,
    fetch_basemap_image,
    get_plotly_bundle,
    image_to_base64,
    wgs84_to_mercator,
)

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
    text = weather_path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) <= 1:
        return None
    try:
        df = pd.read_csv(weather_path, parse_dates=["date"])
    except Exception:
        try:
            df = pd.read_csv(weather_path)
        except Exception:
            return None
    df.columns = [str(c).strip() for c in df.columns]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def _extract_ndvi_time_series(field_dir: Path, boundary_geojson: dict) -> list[dict[str, Any]]:
    """Extract per-scene NDVI time series from Sentinel-2 manifest.

    Process:
    1. Read satellite/sentinel/manifest.json
    2. For each scene with ndvi_tif:
       a. Resolve absolute path using the runtime base
       b. Open with rasterio, mask using field boundary polygon
       c. Compute mean NDVI (excluding NaN/nodata)
       d. Compute day-of-year from scene_date
    3. Return chronologically sorted list of scene records

    Args:
        field_dir: Path to the field directory
        boundary_geojson: GeoJSON-like dict with boundary geometry

    Returns:
        List of dicts with keys:
            scene_date, day_of_year, mean_ndvi, cloud_cover, scene_id, year
    """
    manifest_path = field_dir / "satellite" / "sentinel" / "manifest.json"
    if not manifest_path.exists():
        return []

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _print(f"  [WARN] Failed to read manifest: {exc}")
        return []

    # Use the resolved runtime base from the global runtime paths
    runtime_base = _RUNTIME_PATHS.runtime_base

    records: list[dict[str, Any]] = []
    years_data = manifest.get("years", [])
    if not years_data:
        return []

    for year_entry in years_data:
        year = year_entry.get("year")
        scenes = year_entry.get("scenes", [])
        for scene in scenes:
            scene_date_str = scene.get("scene_date")
            ndvi_rel_path = scene.get("ndvi_tif")
            if not scene_date_str or not ndvi_rel_path:
                continue

            try:
                scene_date = datetime.strptime(scene_date_str, "%Y-%m-%d")
                doy = scene_date.timetuple().tm_yday
            except ValueError:
                continue

            # Build absolute path to NDVI TIFF
            ndvi_path = runtime_base / ndvi_rel_path
            if not ndvi_path.exists():
                _print(f"  [WARN] NDVI TIFF not found: {ndvi_path}")
                continue

            try:
                mean_ndvi, std_ndvi, pixel_count = extract_ndvi_from_composite(ndvi_path, boundary_geojson)
            except Exception as exc:
                _print(f"  [WARN] NDVI extraction failed for {ndvi_path.name}: {exc}")
                continue

            if pixel_count == 0 or np.isnan(mean_ndvi):
                continue

            records.append({
                "year": year,
                "scene_date": scene_date_str,
                "day_of_year": doy,
                "mean_ndvi": round(float(mean_ndvi), 4),
                "cloud_cover": round(float(scene.get("cloud_cover", 0.0)), 2),
                "scene_id": scene.get("scene_id", ""),
            })

    # Sort chronologically
    records.sort(key=lambda r: (r["year"], r["day_of_year"]))
    return records


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


def _geometry_to_geojson(geometry: shapely.geometry.base.BaseGeometry) -> dict:
    """Convert shapely geometry to GeoJSON-like dict."""
    from shapely.geometry import mapping
    return mapping(geometry)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an offline self-contained NDVI-based Crop Health Monitoring Dashboard HTML file."
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
        help="Explicit output HTML path (default: <farm-dir>/<farm-slug>_crop_health_dashboard.html)",
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
    _print("NDVI Crop Health Monitoring Dashboard Generator")
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
    ndvi_by_field_year: list[dict[str, Any]] = []
    total_weather_records = 0
    total_ndvi_records = 0
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

        # Load NDVI time series from Sentinel-2 scenes
        boundary_geojson = _geometry_to_geojson(raw_geom)
        ndvi_records = _extract_ndvi_time_series(field_dir_path, boundary_geojson)
        has_ndvi = len(ndvi_records) > 0
        ndvi_years = sorted(set(r["year"] for r in ndvi_records))

        field_color = _COLORBLIND_PALETTE[len(fields_data) % len(_COLORBLIND_PALETTE)]
        fields_data.append({
            "fieldId": field_id,
            "fieldName": display_name,
            "acres": round(acres, 2),
            "color": field_color,
            "mercatorPolygons": merc_polys,
            "hasWeatherData": has_weather,
            "hasNdviData": has_ndvi,
            "availableYears": available_years,
            "ndviYears": ndvi_years,
        })

        # Process weather data per year
        if weather_df is not None and not weather_df.empty:
            try:
                transforms_df = compute_weather_transforms(weather_df)
                if not transforms_df.empty:
                    for year, group in transforms_df.groupby("year"):
                        group = group.sort_values("date")
                        daily_records = []
                        for _, row in group.iterrows():
                            daily_records.append({
                                "date": row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
                                "dayOfYear": int(row["doy"]),
                                "dailyGdd": round(float(row["daily_gdd"]), 2),
                                "cumulativeGdd": round(float(row["cumulative_gdd"]), 2),
                                "dailyRainfallIn": round(float(row["daily_rainfall_in"]), 2),
                                "cumulativeRainfallIn": round(float(row["cumulative_rainfall_in"]), 2),
                            })
                        if daily_records:
                            weather_by_field_year.append({
                                "fieldId": field_id,
                                "year": int(year),
                                "lastFrostDate": str(group["last_frost_date"].iloc[0]),
                                "lastFrostDoy": int(group["last_frost_doy"].iloc[0]),
                                "daily": daily_records,
                            })
                            total_weather_records += len(daily_records)
            except Exception as exc:
                _print(f"  [WARN] Weather transformation failed for {field_id}: {exc}")

        # Add NDVI time series records
        for rec in ndvi_records:
            ndvi_by_field_year.append({
                "fieldId": field_id,
                "year": rec["year"],
                "sceneDate": rec["scene_date"],
                "dayOfYear": rec["day_of_year"],
                "meanNdvi": rec["mean_ndvi"],
                "cloudCover": rec["cloud_cover"],
                "sceneId": rec["scene_id"],
            })
            total_ndvi_records += 1

    n_fields = len(fields_data)
    n_weather_combos = len(weather_by_field_year)
    n_ndvi_combos = len(ndvi_by_field_year)
    _print(f"Fields discovered: {n_fields}")
    _print(f"Field-year weather combos: {n_weather_combos}")
    _print(f"Total daily weather records: {total_weather_records}")
    _print(f"Field-year NDVI combos: {n_ndvi_combos}")
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
    ndvi_json = json.dumps(ndvi_by_field_year, sort_keys=False)

    generated_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    # Build HTML
    no_basemap_note = ""
    if not basemap_available:
        no_basemap_note = f"Satellite imagery unavailable ({basemap_status}). Using neutral map background."

    html = _build_crop_health_html(
        farm_id=farm_slug,
        farm_name=farm_name,
        generated_at=generated_at,
        basemap_available=basemap_available,
        basemap_b64=basemap_b64,
        fields_json=fields_json,
        weather_json=weather_json,
        ndvi_json=ndvi_json,
        plotly_bundle=plotly_bundle,
        no_basemap_note=no_basemap_note,
    )

    # Determine output path
    if args.output:
        output_path = Path(args.output).expanduser().resolve(strict=False)
    else:
        output_path = farm_path / f"{farm_slug}_crop_health_dashboard.html"

    # Atomic write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(".tmp")
    temp_path.write_text(html, encoding="utf-8")
    shutil.move(str(temp_path), str(output_path))

    size_kb = output_path.stat().st_size / 1024
    _print(f"✓ Dashboard saved → {output_path}")
    _print(f"  Size: {size_kb:.0f} KB")
    _print(f"  Fields: {n_fields}")
    _print(f"  Weather-bearing field-year combos: {n_weather_combos}")
    _print(f"  NDVI field-year combos: {n_ndvi_combos}")
    _print("=" * 60)


def _build_crop_health_html(
    farm_id: str,
    farm_name: str,
    generated_at: str,
    basemap_available: bool,
    basemap_b64: str,
    fields_json: str,
    weather_json: str,
    ndvi_json: str,
    plotly_bundle: str,
    no_basemap_note: str,
) -> str:
    """Build the self-contained HTML dashboard with embedded Plotly and data."""
    # Determine available years across all data
    # Default: 2025 if available, else latest
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NDVI-based Crop Health Monitoring Dashboard — {farm_name}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f4f5f7;
  color: #1e293b;
  line-height: 1.45;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
header {{
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  padding: 0.6rem 1rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}}
header h1 {{
  font-size: 1.1rem;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
}}
header .subtitle {{
  font-size: 0.82rem;
  color: #64748b;
}}
header .note {{
  font-size: 0.75rem;
  color: #94a3b8;
  margin-left: auto;
}}
.controls {{
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}}
.dropdown-wrap {{
  position: relative;
  display: inline-block;
}}
.dropdown-toggle {{
  background: #fff;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0.35rem 0.7rem;
  font-size: 0.85rem;
  cursor: pointer;
  white-space: nowrap;
}}
.dropdown-toggle:hover {{ border-color: #94a3b8; }}
.dropdown-menu {{
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 100;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
  min-width: 180px;
  max-height: 300px;
  overflow-y: auto;
  padding: 0.4rem;
}}
.dropdown-menu.open {{ display: block; }}
.dropdown-item {{
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.4rem;
  font-size: 0.82rem;
  cursor: pointer;
  border-radius: 4px;
}}
.dropdown-item:hover {{ background: #f1f5f9; }}
.dropdown-item input[type="checkbox"] {{
  cursor: pointer;
}}
.dropdown-item .muted {{
  color: #94a3b8;
  font-size: 0.75rem;
}}
.dropdown-actions {{
  display: flex;
  gap: 0.4rem;
  padding: 0.3rem 0.4rem;
  border-top: 1px solid #e2e8f0;
  margin-top: 0.3rem;
}}
.dropdown-actions button {{
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 0.2rem 0.5rem;
  font-size: 0.75rem;
  cursor: pointer;
}}
.dropdown-actions button:hover {{ background: #e2e8f0; }}
.reset-btn {{
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.35rem 0.7rem;
  font-size: 0.85rem;
  cursor: pointer;
}}
.reset-btn:hover {{ background: #e2e8f0; }}
main {{
  flex: 1;
  display: flex;
  overflow: hidden;
  gap: 0.5rem;
  padding: 0.5rem;
}}
.map-pane {{
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
}}
.map-pane .plotly-graph-div {{ flex: 1; }}
.charts-pane {{
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}}
.chart-card {{
  flex: 1;
  min-height: 0;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}}
.chart-card .plotly-graph-div {{ flex: 1; }}
.empty-state {{
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #94a3b8;
  font-size: 0.9rem;
}}
@media (max-width: 900px) {{
  main {{ flex-direction: column; }}
  .map-pane {{ min-height: 300px; }}
}}
</style>
</head>
<body>
<header>
  <div>
    <h1>NDVI-based Crop Health Monitoring Dashboard</h1>
    <div class="subtitle">{farm_name} — Generated {generated_at}</div>
  </div>
  <div class="controls">
    <div class="dropdown-wrap" id="fieldDropdownWrap">
      <button class="dropdown-toggle" id="fieldToggle">Fields ▼</button>
      <div class="dropdown-menu" id="fieldMenu"></div>
    </div>
    <div class="dropdown-wrap" id="yearDropdownWrap">
      <button class="dropdown-toggle" id="yearToggle">Years ▼</button>
      <div class="dropdown-menu" id="yearMenu"></div>
    </div>
    <button class="reset-btn" id="resetBtn">Reset view</button>
  </div>
  <div class="note" id="summaryNote"></div>
</header>
<main>
  <div class="map-pane" id="mapDiv"></div>
  <div class="charts-pane">
    <div class="chart-card" id="ndviDiv"></div>
    <div class="chart-card" id="rainDiv"></div>
    <div class="chart-card" id="gddDiv"></div>
  </div>
</main>
<script>
// Embedded farm data
const FARM_DATA = {{
  farmId: "{farm_id}",
  farmName: "{farm_name}",
  generatedAt: "{generated_at}",
  basemapAvailable: {str(basemap_available).lower()},
  noBasemapNote: "{no_basemap_note.replace('"', '\\"')}"
}};

const FIELDS = {fields_json};
const WEATHER_DATA = {weather_json};
const NDVI_DATA = {ndvi_json};

// Basemap image
const BASEMAP_B64 = "{basemap_b64}";

// Color palette (stable)
const PALETTE = {json.dumps(_COLORBLIND_PALETTE)};

// State
let selectedFields = new Set(FIELDS.map(f => f.fieldId));
let selectedYears = new Set();
let sharedXRange = null;
let _syncing = false;
let _ndviAnnotations = [];

// Determine default years
function getDefaultYears() {{
  const allYears = new Set();
  WEATHER_DATA.forEach(w => allYears.add(w.year));
  NDVI_DATA.forEach(n => allYears.add(n.year));
  const years = Array.from(allYears).sort((a, b) => a - b);
  if (years.includes(2025)) return [2025];
  return years.length > 0 ? [years[years.length - 1]] : [];
}}

selectedYears = new Set(getDefaultYears());

// Utility: get field color
function getFieldColor(fieldId) {{
  const f = FIELDS.find(x => x.fieldId === fieldId);
  return f ? f.color : '#999';
}}

function getFieldName(fieldId) {{
  const f = FIELDS.find(x => x.fieldId === fieldId);
  return f ? f.fieldName : fieldId;
}}

// Build map traces
function buildMapTraces() {{
  const traces = [];
  FIELDS.forEach(field => {{
    const isSelected = selectedFields.has(field.fieldId);
    const alpha = isSelected ? '0.6' : '0.13';
    const lineWidth = isSelected ? 2.5 : 1;
    field.mercatorPolygons.forEach((ring, idx) => {{
      const x = ring.map(p => p[0]);
      const y = ring.map(p => p[1]);
      traces.push({{
        x: x,
        y: y,
        fill: 'toself',
        fillcolor: field.color + alpha,
        line: {{ color: field.color, width: lineWidth }},
        mode: 'lines',
        type: 'scatter',
        name: field.fieldName,
        hovertemplate: `<b>${{field.fieldId}}</b><br>${{field.acres.toFixed(1)}} acres<extra></extra>`,
        customdata: [field.fieldId],
        showlegend: false,
      }});
    }});
  }});
  return traces;
}}

// Compute map layout
function buildMapLayout() {{
  let allX = [], allY = [];
  FIELDS.forEach(f => {{
    if (selectedFields.has(f.fieldId)) {{
      f.mercatorPolygons.forEach(ring => {{
        ring.forEach(p => {{ allX.push(p[0]); allY.push(p[1]); }});
      }});
    }}
  }});
  if (allX.length === 0) {{
    FIELDS.forEach(f => {{
      f.mercatorPolygons.forEach(ring => {{
        ring.forEach(p => {{ allX.push(p[0]); allY.push(p[1]); }});
      }});
    }});
  }}
  const xmin = Math.min(...allX), xmax = Math.max(...allX);
  const ymin = Math.min(...allY), ymax = Math.max(...allY);
  const buf = Math.max(xmax - xmin, ymax - ymin) * 0.2;

  const layout = {{
    margin: {{ t: 10, b: 10, l: 10, r: 10 }},
    xaxis: {{ visible: false, range: [xmin - buf, xmax + buf] }},
    yaxis: {{ visible: false, range: [ymin - buf, ymax + buf], scaleanchor: 'x', scaleratio: 1 }},
    showlegend: false,
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    hovermode: 'closest',
    dragmode: 'pan',
  }};

  if (BASEMAP_B64) {{
    layout.images = [{{
      source: BASEMAP_B64,
      xref: 'x',
      yref: 'y',
      x: xmin - buf,
      y: ymax + buf,
      sizex: (xmax + buf) - (xmin - buf),
      sizey: (ymax + buf) - (ymin - buf),
      sizing: 'stretch',
      layer: 'below',
    }}];
  }}

  return layout;
}}

// Build NDVI traces — per-scene time series with connected lines
function buildNdviTraces() {{
  const traces = [];
  const annotations = [];

  // Group scenes by field-year
  const grouped = {{}};
  NDVI_DATA.forEach(rec => {{
    if (!selectedFields.has(rec.fieldId) || !selectedYears.has(rec.year)) return;
    const key = `${{rec.fieldId}}_${{rec.year}}`;
    if (!grouped[key]) grouped[key] = {{ fieldId: rec.fieldId, year: rec.year, scenes: [] }};
    grouped[key].scenes.push(rec);
  }});

  // Create connected line traces per field-year
  Object.values(grouped).forEach(group => {{
    // Sort scenes chronologically by day of year
    group.scenes.sort((a, b) => a.dayOfYear - b.dayOfYear);
    const color = getFieldColor(group.fieldId);
    const name = `${{getFieldName(group.fieldId)}} ${{group.year}}`;

    traces.push({{
      x: group.scenes.map(s => s.dayOfYear),
      y: group.scenes.map(s => s.meanNdvi),
      mode: 'lines+markers',
      type: 'scatter',
      name: name,
      line: {{ color: color, width: 2 }},
      marker: {{ color: color, size: 8, symbol: 'circle' }},
      customdata: group.scenes.map(s => [group.fieldId, group.year, s.sceneDate, s.cloudCover]),
      hovertemplate: '<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>%{{customdata[2]}} (DOY %{{x}})<br>Mean NDVI: %{{y:.4f}}<br>Cloud: %{{customdata[3]}}%<extra></extra>',
    }});
  }});

  // Annotation for fields with no satellite data
  FIELDS.forEach(field => {{
    if (selectedFields.has(field.fieldId) && !field.hasNdviData) {{
      annotations.push({{
        x: 0.5,
        y: 0.1 + (annotations.length * 0.08),
        xref: 'paper',
        yref: 'paper',
        text: `${{field.fieldName}} — No satellite imagery available`,
        showarrow: false,
        font: {{ color: '#94a3b8', size: 11 }},
      }});
    }}
  }});

  if (annotations.length > 0) {{
    _ndviAnnotations = annotations;
  }}

  return traces;
}}

function buildNdviLayout() {{
  const layout = {{
    title: {{ text: 'Mean NDVI', font: {{ size: 14 }} }},
    margin: {{ t: 40, b: 40, l: 50, r: 50 }},
    xaxis: {{
      title: 'Day of Year',
      range: [80, 320],
      dtick: 30,
    }},
    yaxis: {{ title: 'Mean NDVI', range: [0, 1] }},
    legend: {{ orientation: 'h', y: 1.12, x: 1, xanchor: 'right' }},
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    hovermode: 'closest',
    annotations: _ndviAnnotations || [],
  }};
  if (sharedXRange) layout.xaxis.range = sharedXRange;
  return layout;
}}

// Build rainfall traces
function buildRainTraces() {{
  const traces = [];
  WEATHER_DATA.forEach(rec => {{
    if (!selectedFields.has(rec.fieldId) || !selectedYears.has(rec.year)) return;
    const daily = rec.daily;
    if (!daily || daily.length === 0) return;
    const color = getFieldColor(rec.fieldId);
    const name = `${{getFieldName(rec.fieldId)}} ${{rec.year}}`;

    // Daily rainfall bars
    traces.push({{
      x: daily.map(d => d.dayOfYear),
      y: daily.map(d => d.dailyRainfallIn),
      type: 'bar',
      name: name + ' (daily)',
      marker: {{ color: color, opacity: 0.25 }},
      yaxis: 'y1',
      customdata: daily.map(d => [rec.fieldId, rec.year, d.date]),
      hovertemplate: '<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>%{{customdata[2]}} (DOY %{{x}})<br>Daily: %{{y:.2f}} in<extra></extra>',
      showlegend: false,
    }});

    // Cumulative rainfall line
    traces.push({{
      x: daily.map(d => d.dayOfYear),
      y: daily.map(d => d.cumulativeRainfallIn),
      mode: 'lines',
      type: 'scatter',
      name: name + ' (cumulative)',
      line: {{ color: color, width: 2 }},
      yaxis: 'y2',
      customdata: daily.map(d => [rec.fieldId, rec.year, d.date]),
      hovertemplate: '<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>%{{customdata[2]}} (DOY %{{x}})<br>Cumulative: %{{y:.2f}} in<extra></extra>',
    }});
  }});
  return traces;
}}

function buildRainLayout() {{
  const layout = {{
    title: {{ text: 'Rainfall', font: {{ size: 14 }} }},
    margin: {{ t: 40, b: 40, l: 50, r: 50 }},
    xaxis: {{
      title: 'Day of Year',
      range: [80, 320],
      dtick: 30,
    }},
    yaxis: {{ title: 'Daily rainfall (in)', side: 'left' }},
    yaxis2: {{ title: 'Cumulative rainfall (in)', overlaying: 'y', side: 'right' }},
    legend: {{ orientation: 'h', y: 1.12, x: 1, xanchor: 'right' }},
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    hovermode: 'closest',
  }};
  if (sharedXRange) layout.xaxis.range = sharedXRange;
  return layout;
}}

// Build GDD traces
function buildGddTraces() {{
  const traces = [];
  WEATHER_DATA.forEach(rec => {{
    if (!selectedFields.has(rec.fieldId) || !selectedYears.has(rec.year)) return;
    const daily = rec.daily;
    if (!daily || daily.length === 0) return;
    const color = getFieldColor(rec.fieldId);
    const name = `${{getFieldName(rec.fieldId)}} ${{rec.year}}`;

    traces.push({{
      x: daily.map(d => d.dayOfYear),
      y: daily.map(d => d.cumulativeGdd),
      mode: 'lines',
      type: 'scatter',
      name: name,
      line: {{ color: color, width: 2 }},
      customdata: daily.map(d => [rec.fieldId, rec.year, d.date]),
      hovertemplate: '<b>%{{customdata[0]}}</b> (%{{customdata[1]}})<br>%{{customdata[2]}} (DOY %{{x}})<br>Cumulative GDD: %{{y:.1f}}<extra></extra>',
    }});

    // Frost marker
    traces.push({{
      x: [rec.lastFrostDoy],
      y: [0],
      mode: 'markers',
      marker: {{ color: color, symbol: 'line-ns', size: 16 }},
      showlegend: false,
      hoverinfo: 'skip',
    }});
  }});
  return traces;
}}

function buildGddLayout() {{
  const layout = {{
    title: {{ text: 'Growing Degree Days', font: {{ size: 14 }} }},
    margin: {{ t: 40, b: 40, l: 50, r: 50 }},
    xaxis: {{
      title: 'Day of Year',
      range: [80, 320],
      dtick: 30,
    }},
    yaxis: {{ title: 'Cumulative GDD (base 50°F)' }},
    legend: {{ orientation: 'h', y: 1.12, x: 1, xanchor: 'right' }},
    paper_bgcolor: '#fff',
    plot_bgcolor: '#fff',
    hovermode: 'closest',
  }};
  if (sharedXRange) layout.xaxis.range = sharedXRange;
  return layout;
}}

// Render all charts
function renderAll() {{
  _ndviAnnotations = [];  // Clear NDVI annotations before rebuild
  const mapTraces = buildMapTraces();
  const mapLayout = buildMapLayout();
  Plotly.newPlot('mapDiv', mapTraces, mapLayout, {{ responsive: true, displayModeBar: false }});

  // Click handler on map
  document.getElementById('mapDiv').on('plotly_click', function(data) {{
    if (data.points && data.points[0] && data.points[0].customdata) {{
      const fid = data.points[0].customdata[0];
      if (selectedFields.has(fid)) {{
        selectedFields.delete(fid);
      }} else {{
        selectedFields.add(fid);
      }}
      updateControls();
      renderAll();
    }}
  }});

  const ndviTraces = buildNdviTraces();
  const ndviLayout = buildNdviLayout();
  if (ndviTraces.length === 0) {{
    document.getElementById('ndviDiv').innerHTML = '<div class="empty-state">No NDVI data for selected fields/years</div>';
  }} else {{
    Plotly.newPlot('ndviDiv', ndviTraces, ndviLayout, {{ responsive: true }});
    attachRelayoutSync('ndviDiv');
  }}

  const rainTraces = buildRainTraces();
  const rainLayout = buildRainLayout();
  if (rainTraces.length === 0) {{
    document.getElementById('rainDiv').innerHTML = '<div class="empty-state">No weather data for selected fields/years</div>';
  }} else {{
    Plotly.newPlot('rainDiv', rainTraces, rainLayout, {{ responsive: true }});
    attachRelayoutSync('rainDiv');
  }}

  const gddTraces = buildGddTraces();
  const gddLayout = buildGddLayout();
  if (gddTraces.length === 0) {{
    document.getElementById('gddDiv').innerHTML = '<div class="empty-state">No weather data for selected fields/years</div>';
  }} else {{
    Plotly.newPlot('gddDiv', gddTraces, gddLayout, {{ responsive: true }});
    attachRelayoutSync('gddDiv');
  }}

  updateSummary();
}}

// X-axis synchronization
function attachRelayoutSync(chartId) {{
  const el = document.getElementById(chartId);
  el.on('plotly_relayout', function(evt) {{
    if (_syncing) return;
    if (evt['xaxis.range[0]'] && evt['xaxis.range[1]']) {{
      _syncing = true;
      sharedXRange = [evt['xaxis.range[0]'], evt['xaxis.range[1]']];
      const ids = ['ndviDiv', 'rainDiv', 'gddDiv'];
      ids.forEach(id => {{
        if (id !== chartId) {{
          Plotly.relayout(id, {{ 'xaxis.range': sharedXRange }});
        }}
      }});
      _syncing = false;
    }}
  }});
}}

// Build dropdown menus
function buildFieldMenu() {{
  const menu = document.getElementById('fieldMenu');
  menu.innerHTML = '';

  const allItem = document.createElement('div');
  allItem.className = 'dropdown-actions';
  allItem.innerHTML = '<button id="selectAllFields">Select all</button><button id="clearAllFields">Clear all</button>';
  menu.appendChild(allItem);

  FIELDS.forEach(field => {{
    const item = document.createElement('label');
    item.className = 'dropdown-item';
    const noData = !field.hasWeatherData && !field.hasNdviData;
    item.innerHTML = `<input type="checkbox" ${{selectedFields.has(field.fieldId) ? 'checked' : ''}} data-field="${{field.fieldId}}"> <span>${{field.fieldName}}</span> ${{noData ? '<span class="muted">(no data)</span>' : ''}}`;
    menu.appendChild(item);
  }});

  document.getElementById('selectAllFields').onclick = () => {{
    FIELDS.forEach(f => selectedFields.add(f.fieldId));
    updateControls();
    renderAll();
  }};
  document.getElementById('clearAllFields').onclick = () => {{
    selectedFields.clear();
    updateControls();
    renderAll();
  }};

  menu.querySelectorAll('input[data-field]').forEach(cb => {{
    cb.addEventListener('change', () => {{
      const fid = cb.getAttribute('data-field');
      if (cb.checked) selectedFields.add(fid);
      else selectedFields.delete(fid);
      updateControls();
      renderAll();
    }});
  }});
}}

function buildYearMenu() {{
  const menu = document.getElementById('yearMenu');
  menu.innerHTML = '';

  const allYears = new Set();
  WEATHER_DATA.forEach(w => allYears.add(w.year));
  NDVI_DATA.forEach(n => allYears.add(n.year));
  const years = Array.from(allYears).sort((a, b) => a - b);

  if (years.length === 0) {{
    menu.innerHTML = '<div class="dropdown-item"><span class="muted">No years available</span></div>';
    return;
  }}

  const allItem = document.createElement('div');
  allItem.className = 'dropdown-actions';
  allItem.innerHTML = '<button id="selectAllYears">Select all</button><button id="clearAllYears">Clear all</button>';
  menu.appendChild(allItem);

  years.forEach(year => {{
    const item = document.createElement('label');
    item.className = 'dropdown-item';
    item.innerHTML = `<input type="checkbox" ${{selectedYears.has(year) ? 'checked' : ''}} data-year="${{year}}"> <span>${{year}}</span>`;
    menu.appendChild(item);
  }});

  document.getElementById('selectAllYears').onclick = () => {{
    years.forEach(y => selectedYears.add(y));
    updateControls();
    renderAll();
  }};
  document.getElementById('clearAllYears').onclick = () => {{
    selectedYears.clear();
    updateControls();
    renderAll();
  }};

  menu.querySelectorAll('input[data-year]').forEach(cb => {{
    cb.addEventListener('change', () => {{
      const year = parseInt(cb.getAttribute('data-year'));
      if (cb.checked) selectedYears.add(year);
      else selectedYears.delete(year);
      updateControls();
      renderAll();
    }});
  }});
}}

function updateControls() {{
  const fCount = selectedFields.size;
  const yCount = selectedYears.size;
  document.getElementById('fieldToggle').textContent = `Fields (${{fCount}}) ▼`;
  document.getElementById('yearToggle').textContent = `Years (${{yCount}}) ▼`;
}}

function updateSummary() {{
  const fCount = selectedFields.size;
  const yCount = selectedYears.size;
  const note = `${{fCount}} field${{fCount !== 1 ? 's' : ''}}, ${{yCount}} year${{yCount !== 1 ? 's' : ''}}`;
  document.getElementById('summaryNote').textContent = note;
}}

// Dropdown toggles
function setupDropdown(wrapId, toggleId, menuId) {{
  const wrap = document.getElementById(wrapId);
  const toggle = document.getElementById(toggleId);
  const menu = document.getElementById(menuId);

  toggle.addEventListener('click', (e) => {{
    e.stopPropagation();
    const isOpen = menu.classList.contains('open');
    // Close all
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('open'));
    if (!isOpen) menu.classList.add('open');
  }});
}}

document.addEventListener('click', () => {{
  document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('open'));
}});

// Reset
function resetView() {{
  selectedFields = new Set(FIELDS.map(f => f.fieldId));
  selectedYears = new Set(getDefaultYears());
  sharedXRange = null;
  updateControls();
  renderAll();
}}

document.getElementById('resetBtn').addEventListener('click', resetView);

// Initialize
setupDropdown('fieldDropdownWrap', 'fieldToggle', 'fieldMenu');
setupDropdown('yearDropdownWrap', 'yearToggle', 'yearMenu');
buildFieldMenu();
buildYearMenu();
updateControls();
renderAll();
</script>
<script>
{plotly_bundle}
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
