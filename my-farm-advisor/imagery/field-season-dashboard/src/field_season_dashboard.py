#!/usr/bin/env python3
"""Generate aligned field-season mini-dashboard for one field-year.

Assignment 3: Combines Sentinel-2 NDVI, daily weather (precipitation, temperature
extremes), and cumulative GDD into a single 4-panel PNG dashboard with a shared
day-of-year time axis.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CROP_GDD_BASE: dict[str, float] = {
    "Corn": 10.0,
    "Soybeans": 10.0,
    "default": 10.0,
}

DEFAULT_GS_START = 121  # May 1
DEFAULT_GS_END = 273    # Sep 30

# Color scheme
COLOR_NDVI = "forestgreen"
COLOR_PRECIP = "steelblue"
COLOR_TEMP_FILL = "orange"
COLOR_TEMP_MEAN = "black"
COLOR_GDD = "green"
COLOR_GS_BAND = "green"

# State FIPS to name mapping (for title generation)
STATE_FIPS_NAMES: dict[str, str] = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa",
    "20": "Kansas", "21": "Kentucky", "22": "Louisiana", "23": "Maine",
    "24": "Maryland", "25": "Massachusetts", "26": "Michigan", "27": "Minnesota",
    "28": "Mississippi", "29": "Missouri", "30": "Montana", "31": "Nebraska",
    "32": "Nevada", "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota", "39": "Ohio",
    "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming",
}

# Month labels for x-axis (Mar-Nov)
MONTH_LABELS: dict[int, str] = {
    3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov",
}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate aligned field-season mini-dashboard"
    )
    parser.add_argument("--grower-slug", required=True, help="Grower identifier")
    parser.add_argument("--farm-slug", required=True, help="Farm identifier")
    parser.add_argument("--field-id", required=True, help="Field identifier")
    parser.add_argument("--year", type=int, required=True, help="Growing season year")
    parser.add_argument(
        "--gdd-base-temp",
        type=float,
        default=None,
        help="GDD base temperature in °C (auto-detected from crop if omitted)",
    )
    parser.add_argument(
        "--gs-start-doy",
        type=int,
        default=DEFAULT_GS_START,
        help="Growing season start day-of-year (default: 121 = May 1)",
    )
    parser.add_argument(
        "--gs-end-doy",
        type=int,
        default=DEFAULT_GS_END,
        help="Growing season end day-of-year (default: 273 = Sep 30)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom output directory (default: runtime imagery/field-season-dashboard/output)",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def resolve_paths(args: argparse.Namespace) -> dict[str, Path]:
    data_root = Path(
        os.environ.get("DATA_PIPELINE_DATA_ROOT", "/home/coder/my-farm-advisor-runtime")
    ) / "data-pipeline"

    farm_dir = data_root / "growers" / args.grower_slug / "farms" / args.farm_slug
    field_dir = farm_dir / "fields" / args.field_id

    # Farm-level CDL table name follows the pattern: <farm_slug>_cdl_2021_2025_full_composition_updated.csv
    # with _farm stripped from the prefix if present
    farm_prefix = args.farm_slug.replace("-", "_")
    if farm_prefix.endswith("_farm"):
        farm_prefix = farm_prefix[: -len("_farm")]

    return {
        "data_root": data_root,
        "boundary": field_dir / "boundary" / "field_boundary.geojson",
        "weather": field_dir / "weather" / "daily_weather.csv",
        "cdl": farm_dir / "derived" / "tables" / f"{farm_prefix}_cdl_2021_2025_full_composition_updated.csv",
        "sentinel": field_dir / "satellite" / "sentinel" / str(args.year),
        "output_dir": (
            Path(args.output_dir)
            if args.output_dir
            else data_root / "imagery" / "field-season-dashboard" / "output"
        ),
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_crop_type(cdl_path: Path, field_id: str, year: int) -> str:
    """Load primary crop type from CDL composition table."""
    if not cdl_path.exists():
        # Fallback: try without stripping _farm
        alt_path = cdl_path.parent / f"{cdl_path.stem.replace('_full_composition_updated', '')}_full_composition_updated.csv"
        if alt_path.exists():
            cdl_path = alt_path
        else:
            return "default"

    cdl = pd.read_csv(cdl_path)
    field_cdl = cdl[(cdl["field_id"] == field_id) & (cdl["year"] == year)]
    if field_cdl.empty:
        return "default"

    primary = field_cdl.loc[field_cdl["pct"].idxmax()]
    return str(primary["crop_name"])


def extract_ndvi(sentinel_dir: Path, boundary_path: Path) -> pd.DataFrame:
    """Extract mean NDVI from all Sentinel-2 scenes for the year."""
    boundary = gpd.read_file(boundary_path)
    records: list[dict] = []

    for scene_dir in sorted(sentinel_dir.glob("sentinel_*")):
        # Parse date from dirname: sentinel_20210306
        parts = scene_dir.name.split("_")
        if len(parts) < 2:
            continue
        date_str = parts[1]
        try:
            date = datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            continue

        doy = date.timetuple().tm_yday
        ndvi_tif = scene_dir / f"{scene_dir.name}_ndvi.tif"
        if not ndvi_tif.exists():
            continue

        with rasterio.open(ndvi_tif) as src:
            boundary_proj = boundary.to_crs(src.crs)
            clipped, _ = mask(src, boundary_proj.geometry, crop=True, filled=False)
            arr = np.ma.filled(clipped[0], np.nan).astype(float)
            mean_ndvi = float(np.nanmean(arr))

        records.append({
            "date": date,
            "doy": doy,
            "ndvi": mean_ndvi,
        })

    if not records:
        raise ValueError(f"No valid Sentinel-2 NDVI scenes found in {sentinel_dir}")

    return pd.DataFrame(records).sort_values("doy").reset_index(drop=True)


def c_to_f(c: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


def load_weather(weather_path: Path, year: int) -> pd.DataFrame:
    """Load and filter daily weather for the target year, converting temps to Fahrenheit."""
    weather = pd.read_csv(weather_path, parse_dates=["date"])
    weather["year"] = weather["date"].dt.year
    weather = weather[weather["year"] == year].copy()
    weather["doy"] = weather["date"].dt.dayofyear
    # Convert temperatures from Celsius to Fahrenheit
    for col in ["T2M", "T2M_MIN", "T2M_MAX"]:
        weather[col] = weather[col].apply(c_to_f)
    return weather.sort_values("doy").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def calculate_gdd(weather: pd.DataFrame, base_temp_c: float) -> pd.DataFrame:
    """Calculate daily and cumulative GDD using Fahrenheit."""
    weather = weather.copy()
    base_temp_f = c_to_f(base_temp_c)  # Convert base temp to Fahrenheit
    t_avg = (weather["T2M_MIN"] + weather["T2M_MAX"]) / 2.0
    weather["gdd"] = np.maximum(0, t_avg - base_temp_f)
    weather["gdd_cumulative"] = weather["gdd"].cumsum()
    return weather


# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

def detect_events(
    weather: pd.DataFrame, ndvi: pd.DataFrame, gs_start: int, gs_end: int
) -> list[dict]:
    """Detect notable weather and NDVI events."""
    events: list[dict] = []
    gs = weather[(weather["doy"] >= gs_start) & (weather["doy"] <= gs_end)]

    # ---- NDVI events ----
    # Peak NDVI
    peak_idx = ndvi["ndvi"].idxmax()
    peak_row = ndvi.loc[peak_idx]
    events.append({
        "doy": int(peak_row["doy"]),
        "type": "ndvi_peak",
        "value": float(peak_row["ndvi"]),
        "label": f"Peak NDVI: {peak_row['ndvi']:.3f}",
        "panel": 0,
        "score": float(peak_row["ndvi"]) * 100,
    })

    # Rapid growth (largest positive difference between consecutive scenes)
    ndvi_diff = ndvi["ndvi"].diff()
    max_rise_idx = ndvi_diff.idxmax()
    if not pd.isna(max_rise_idx) and max_rise_idx > 0:
        max_rise_row = ndvi.loc[max_rise_idx]
        prev_row = ndvi.loc[max_rise_idx - 1]
        rise = float(max_rise_row["ndvi"] - prev_row["ndvi"])
        events.append({
            "doy": int(max_rise_row["doy"]),
            "type": "ndvi_rise",
            "value": rise,
            "label": f"Rapid growth: +{rise:.3f}",
            "panel": 0,
            "score": rise * 200,
        })

    # ---- Weather events ----
    # Heavy rain (>25mm)
    heavy_rain = weather[weather["PRECTOTCORR"] > 25]
    for _, row in heavy_rain.iterrows():
        events.append({
            "doy": int(row["doy"]),
            "type": "heavy_rain",
            "value": float(row["PRECTOTCORR"]),
            "label": f"Heavy rain: {row['PRECTOTCORR']:.1f}mm",
            "panel": 1,
            "score": float(row["PRECTOTCORR"]),
        })

    # Hottest day of the year
    max_temp_idx = weather["T2M_MAX"].idxmax()
    max_temp_row = weather.loc[max_temp_idx]
    events.append({
        "doy": int(max_temp_row["doy"]),
        "type": "hot_day",
        "value": float(max_temp_row["T2M_MAX"]),
        "label": f"Hottest: {max_temp_row['T2M_MAX']:.1f}°F",
        "panel": 2,
        "score": float(max_temp_row["T2M_MAX"]) * 2,
    })

    # Frost risk during growing season (T2M_MIN < 36°F)
    if not gs.empty:
        frost = gs[gs["T2M_MIN"] < 36]
        if not frost.empty:
            frost_row = frost.loc[frost["T2M_MIN"].idxmin()]
            events.append({
                "doy": int(frost_row["doy"]),
                "type": "frost",
                "value": float(frost_row["T2M_MIN"]),
                "label": f"Late frost: {frost_row['T2M_MIN']:.1f}°F",
                "panel": 2,
                "score": 50.0,  # High agronomic relevance
            })

    return events


# ---------------------------------------------------------------------------
# Dashboard construction
# ---------------------------------------------------------------------------

def add_event_annotations(
    axes: list[plt.Axes],
    events: list[dict],
    weather: pd.DataFrame,
    ndvi: pd.DataFrame,
) -> None:
    """Add concise event annotations to the appropriate panels, keeping all inside."""
    # Select top 5 events by score
    top_events = sorted(events, key=lambda e: e["score"], reverse=True)[:5]

    for i, event in enumerate(top_events):
        panel_idx = event["panel"]
        ax = axes[panel_idx]
        doy = event["doy"]

        # Get axis bounds
        x_min, x_max = ax.get_xlim()
        y_min, y_max = ax.get_ylim()
        x_range = x_max - x_min
        y_range = y_max - y_min

        # Get y position based on panel and event type
        if panel_idx == 0:  # NDVI
            ndvi_match = ndvi[ndvi["doy"] == doy]
            if not ndvi_match.empty:
                y_pos = float(ndvi_match.iloc[0]["ndvi"])
            else:
                y_pos = float(ndvi["ndvi"].max())
            # Position based on event type
            if event["type"] == "ndvi_peak":
                # Peak: text to the right of the dot, slightly above
                text_y = y_min + y_range * 0.75
            elif event["type"] == "ndvi_rise":
                # Rapid growth: text up and to the left
                text_y = y_min + y_range * 0.80
            else:
                text_y = y_min + y_range * (0.15 + (i % 3) * 0.35)

        elif panel_idx == 1:  # Precipitation
            precip_match = weather[weather["doy"] == doy]
            if not precip_match.empty:
                y_pos = float(precip_match.iloc[0]["PRECTOTCORR"])
            else:
                y_pos = float(weather["PRECTOTCORR"].max()) * 0.8
            # Keep text well above the bars (70-85% of y range)
            text_y = y_min + y_range * (0.70 + (i % 2) * 0.15)

        elif panel_idx == 2:  # Temperature
            temp_match = weather[weather["doy"] == doy]
            if not temp_match.empty:
                y_pos = float(temp_match.iloc[0]["T2M_MAX"])
            else:
                y_pos = float(weather["T2M_MAX"].max())
            # Frost goes lower-left, hot goes upper-right to avoid overlap
            if event["type"] == "frost":
                text_y = y_min + y_range * 0.25
            elif event["type"] == "hot_day":
                text_y = y_min + y_range * 0.85
            else:
                text_y = y_min + y_range * (0.50 + (i % 2) * 0.25)

        else:
            continue

        # Calculate safe x position for text with SHORT arrows (5% of x-range)
        margin = x_range * 0.08
        arrow_offset = x_range * 0.05  # Short arrows
        if panel_idx == 0 and event["type"] == "ndvi_rise":
            # Rapid growth: text to the left
            text_x = max(doy - arrow_offset, x_min + margin)
            ha = "right"
        elif panel_idx == 2 and event["type"] == "frost":
            # Frost: text to the left
            text_x = max(doy - arrow_offset, x_min + margin)
            ha = "right"
        elif panel_idx == 2 and event["type"] == "hot_day":
            # Hottest: text to the right
            text_x = min(doy + arrow_offset, x_max - margin)
            ha = "left"
        elif doy < x_min + x_range * 0.5:
            # Event is in left half: text goes to the right
            text_x = min(doy + arrow_offset, x_max - margin)
            ha = "left"
        else:
            # Event is in right half: text goes to the left
            text_x = max(doy - arrow_offset, x_min + margin)
            ha = "right"

        # Ensure y text stays within bounds
        text_y = max(y_min + y_range * 0.08, min(text_y, y_max - y_range * 0.08))

        # Choose color based on event type
        if event["type"] == "frost":
            color = "#1d4ed8"  # Blue for cold
            bbox_color = "#dbeafe"
        elif event["type"] == "hot_day":
            color = "#b45309"  # Orange for heat
            bbox_color = "#fef3c7"
        elif event["type"] == "heavy_rain":
            color = "#1e40af"  # Dark blue for rain
            bbox_color = "#dbeafe"
        else:  # NDVI events
            color = "#166534"  # Green for vegetation
            bbox_color = "#dcfce7"

        ax.annotate(
            event["label"],
            xy=(doy, y_pos),
            xytext=(text_x, text_y),
            fontsize=8,
            fontweight="bold",
            color=color,
            ha=ha,
            va="center",
            arrowprops=dict(
                arrowstyle="->",
                color=color,
                alpha=0.7,
                lw=0.9,
            ),
            bbox=dict(
                boxstyle="round,pad=0.35",
                facecolor=bbox_color,
                alpha=0.85,
                edgecolor=color,
                linewidth=0.8,
            ),
            zorder=10,
        )


def build_dashboard(
    weather: pd.DataFrame,
    ndvi: pd.DataFrame,
    events: list[dict],
    field_id: str,
    year: int,
    crop: str,
    acres: float,
    base_temp: float,
    gs_start: int,
    gs_end: int,
    state_name: str,
) -> plt.Figure:
    """Build the 4-panel aligned dashboard."""

    # Growing season totals
    gs = weather[(weather["doy"] >= gs_start) & (weather["doy"] <= gs_end)]
    gs_precip = float(gs["PRECTOTCORR"].sum()) if not gs.empty else 0.0
    gs_gdd = float(gs["gdd"].sum()) if not gs.empty else 0.0

    # Create figure with 4 stacked panels
    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(12, 16))
    fig.suptitle(
        f"Field-season Weather and NDVI Storyline for {year} - {state_name} Field ID {field_id}",
        fontsize=13,
        fontweight="bold",
        y=0.98,
    )

    # Common x-axis setup: Mar (DOY ~60) to Nov (DOY ~335)
    x_min, x_max = 60, 335
    month_ticks = [60, 91, 121, 152, 182, 213, 244, 274, 305]
    month_labels = ["Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov"]

    for ax in axes:
        ax.set_xlim(x_min, x_max)
        ax.set_xticks(month_ticks)
        ax.set_xticklabels(month_labels, fontsize=9)
        ax.axvspan(gs_start, gs_end, alpha=0.06, color=COLOR_GS_BAND, zorder=0)
        ax.grid(True, alpha=0.25, axis="y", linestyle="-", linewidth=0.5)

    # ---- Panel 1: NDVI Time Series ----
    ax = axes[0]
    ax.scatter(
        ndvi["doy"],
        ndvi["ndvi"],
        color=COLOR_NDVI,
        s=70,
        zorder=5,
        edgecolors="white",
        linewidths=0.8,
    )
    ax.plot(
        ndvi["doy"],
        ndvi["ndvi"],
        color=COLOR_NDVI,
        linewidth=1.5,
        alpha=0.7,
        zorder=4,
    )
    ax.set_ylabel("Mean NDVI", fontsize=10, fontweight="bold")
    ax.set_title(
        "Field Mean NDVI Time Series  (Sentinel-2)",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=8,
    )
    # Auto-scale with padding
    ndvi_min = float(ndvi["ndvi"].min())
    ndvi_max = float(ndvi["ndvi"].max())
    padding = (ndvi_max - ndvi_min) * 0.15
    ax.set_ylim(ndvi_min - padding, ndvi_max + padding)

    # ---- Panel 2: Daily Precipitation ----
    ax = axes[1]
    # Daily precipitation bars (left y-axis, mm)
    bars = ax.bar(
        weather["doy"],
        weather["PRECTOTCORR"],
        color=COLOR_PRECIP,
        alpha=0.6,
        width=1.0,
        edgecolor="none",
        zorder=3,
        label="Daily Precipitation",
    )
    ax.set_ylabel("Daily Precipitation (mm)", fontsize=10, fontweight="bold", color=COLOR_PRECIP)
    ax.tick_params(axis="y", labelcolor=COLOR_PRECIP)
    ax.set_title(
        "Daily and Cumulative Precipitation",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=8,
    )
    ax.set_ylim(0, float(weather["PRECTOTCORR"].max()) * 1.25)

    # Cumulative precipitation line (right y-axis, inches)
    weather["precip_cumulative_in"] = weather["PRECTOTCORR"].cumsum() / 25.4
    ax2 = ax.twinx()
    ax2.plot(
        weather["doy"],
        weather["precip_cumulative_in"],
        color="darkred",
        linewidth=1.8,
        alpha=0.85,
        zorder=4,
        label="Cumulative Precipitation",
    )
    ax2.set_ylabel("Cumulative Precipitation (in)", fontsize=10, fontweight="bold", color="darkred")
    ax2.tick_params(axis="y", labelcolor="darkred")
    ax2.set_ylim(0, float(weather["precip_cumulative_in"].max()) * 1.25)

    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8, framealpha=0.9)

    # ---- Panel 3: Temperature Extremes ----
    ax = axes[2]
    ax.fill_between(
        weather["doy"],
        weather["T2M_MIN"],
        weather["T2M_MAX"],
        alpha=0.25,
        color=COLOR_TEMP_FILL,
        label="Daily min–max",
        zorder=2,
    )
    ax.plot(
        weather["doy"],
        weather["T2M"],
        color=COLOR_TEMP_MEAN,
        linewidth=0.9,
        alpha=0.9,
        label="Daily mean",
        zorder=3,
    )
    # Threshold lines (50°F and 68°F)
    ax.axhline(
        50, color="green", linestyle="--", alpha=0.4, linewidth=0.8, zorder=1
    )
    ax.axhline(
        68, color="darkgreen", linestyle="--", alpha=0.4, linewidth=0.8, zorder=1
    )
    ax.set_ylabel("Temperature (°F)", fontsize=10, fontweight="bold")
    ax.set_title(
        "Temperature and Extremes",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=8,
    )
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    # Force y-axis to start at 0°F
    _, y_max_temp = ax.get_ylim()
    ax.set_ylim(0, y_max_temp)

    # ---- Panel 4: Cumulative GDD ----
    ax = axes[3]
    ax.plot(
        weather["doy"],
        weather["gdd_cumulative"],
        color=COLOR_GDD,
        linewidth=2.2,
        zorder=3,
    )
    # Threshold lines (900 and 1800 °F·days)
    for threshold in [900, 1800]:
        ax.axhline(
            threshold,
            color="gray",
            linestyle="--",
            alpha=0.4,
            linewidth=0.8,
            zorder=1,
        )
        ax.text(
            338,
            threshold,
            f"{threshold} GDD",
            fontsize=7,
            color="gray",
            va="center",
            ha="left",
        )
    ax.set_ylabel("Cumulative GDD (°F·days)", fontsize=10, fontweight="bold")
    ax.set_title(
        f"Cumulative Growing Degree Days  (base {c_to_f(base_temp):.0f}°F)",
        fontsize=11,
        fontweight="bold",
        loc="left",
        pad=8,
    )
    ax.set_xlabel("Month", fontsize=10, fontweight="bold")

    # ---- Event annotations ----
    add_event_annotations(axes, events, weather, ndvi)

    # Final layout
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])
    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = resolve_paths(args)

    # Validate inputs
    if not paths["boundary"].exists():
        print(f"ERROR: Boundary not found: {paths['boundary']}", file=sys.stderr)
        return 1
    if not paths["weather"].exists():
        print(f"ERROR: Weather not found: {paths['weather']}", file=sys.stderr)
        return 1
    if not paths["sentinel"].exists():
        print(f"ERROR: Sentinel directory not found: {paths['sentinel']}", file=sys.stderr)
        return 1

    # Load boundary and derive state name
    print(f"Loading boundary: {paths['boundary']}")
    boundary = gpd.read_file(paths["boundary"])
    acres = float(boundary.iloc[0].get("area_acres", 0))
    state_fips = str(boundary.iloc[0].get("state_fips", ""))
    state_name = STATE_FIPS_NAMES.get(state_fips, "Unknown")

    # Load CDL crop type
    print(f"Loading CDL: {paths['cdl']}")
    crop = load_crop_type(paths["cdl"], args.field_id, args.year)

    # Load weather
    print(f"Loading weather: {paths['weather']}")
    weather = load_weather(paths["weather"], args.year)

    # Extract NDVI
    print(f"Extracting NDVI from: {paths['sentinel']}")
    ndvi = extract_ndvi(paths["sentinel"], paths["boundary"])
    print(f"  Found {len(ndvi)} Sentinel scenes")

    # Determine GDD base temp
    base_temp = args.gdd_base_temp or CROP_GDD_BASE.get(crop, CROP_GDD_BASE["default"])
    print(f"Crop: {crop}, GDD base temp: {base_temp}°C")

    # Calculate GDD
    weather = calculate_gdd(weather, base_temp)

    # Detect events
    events = detect_events(weather, ndvi, args.gs_start_doy, args.gs_end_doy)
    print(f"Detected {len(events)} events, annotating top 5")
    for ev in sorted(events, key=lambda e: e["score"], reverse=True)[:5]:
        print(f"  • {ev['label']} (DOY {ev['doy']}, score {ev['score']:.1f})")

    # Build dashboard
    print("Building dashboard...")
    fig = build_dashboard(
        weather,
        ndvi,
        events,
        args.field_id,
        args.year,
        crop,
        acres,
        base_temp,
        args.gs_start_doy,
        args.gs_end_doy,
        state_name,
    )

    # Save
    paths["output_dir"].mkdir(parents=True, exist_ok=True)
    output_path = paths["output_dir"] / f"{args.field_id}_{args.year}_dashboard.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"\n✓ Saved: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
