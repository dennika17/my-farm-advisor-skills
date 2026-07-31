#!/usr/bin/env python3
"""Asset management for weather dashboard generation.

Handles:
- Downloading and caching a pinned Plotly.js bundle
- Downloading, stitching, and cropping satellite imagery tiles
- Mercator coordinate conversions
"""

from __future__ import annotations

import base64
import io
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import cast

import requests
from PIL import Image

# Allow running both from runtime copy and during development
_LOCAL_LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(_LOCAL_LIB))

try:
    from lib.runtime_paths import resolve_runtime_paths
except ImportError:
    from runtime_paths import resolve_runtime_paths

_RUNTIME_PATHS = resolve_runtime_paths()
_SHARED_ASSETS = _RUNTIME_PATHS.runtime_base / "shared" / "assets"
_PLOTLY_VERSION = "2.27.0"
_PLOTLY_URL = f"https://cdn.plot.ly/plotly-{_PLOTLY_VERSION}.min.js"
_PLOTLY_CACHE = _SHARED_ASSETS / f"plotly-{_PLOTLY_VERSION}.min.js"

# Tile limits to avoid abuse or memory issues
_MAX_TILES = 64
_TILE_TIMEOUT = 15
_TILE_RETRIES = 2
_DEFAULT_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def _ensure_assets_dir() -> None:
    _SHARED_ASSETS.mkdir(parents=True, exist_ok=True)


def get_plotly_bundle() -> str:
    """Return the Plotly bundle as a string, downloading and caching if needed."""
    if _PLOTLY_CACHE.exists():
        return _PLOTLY_CACHE.read_text(encoding="utf-8")

    _ensure_assets_dir()
    print(f"[dashboard] Downloading Plotly {_PLOTLY_VERSION} bundle...")
    try:
        resp = requests.get(_PLOTLY_URL, timeout=120)
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download Plotly bundle from {_PLOTLY_URL}. "
            f"Ensure build-time network access is available, or pre-stage the bundle at {_PLOTLY_CACHE}. "
            f"Error: {exc}"
        ) from exc

    _PLOTLY_CACHE.write_text(resp.text, encoding="utf-8")
    print(f"[dashboard] Plotly bundle cached → {_PLOTLY_CACHE}")
    return resp.text


def wgs84_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    """Spherical Mercator projection (EPSG:3857) using standard formula."""
    R = 6378137.0
    x = R * math.radians(lon)
    lat_rad = math.radians(lat)
    y = R * math.log(math.tan(math.pi / 4.0 + lat_rad / 2.0))
    return (x, y)


def mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Inverse spherical Mercator projection."""
    R = 6378137.0
    lon = math.degrees(x / R)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R)) - math.pi / 2.0)
    return (lon, lat)


def _tile_xy(zoom: int, lon: float, lat: float) -> tuple[int, int]:
    """Convert WGS84 lat/lon to tile X/Y indices at given zoom."""
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
    return (x, y)


def _tile_bounds(zoom: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Return WGS84 bounds (west, south, east, north) for a tile."""
    n = 2.0 ** zoom
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    lat_n = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_s = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return (west, lat_s, east, lat_n)


def _tile_size_px(zoom: int, lat: float) -> float:
    """Approximate ground resolution in meters per pixel at latitude (standard 256px tiles)."""
    return 156543.03 * math.cos(math.radians(lat)) / (2.0 ** zoom)


def compute_mercator_extent(
    geometries_wgs84: list,
    buffer_pct: float = 0.15,
) -> tuple[float, float, float, float]:
    """Compute buffered Mercator extent from a list of shapely geometries.

    Returns (xmin, ymin, xmax, ymax) in meters.
    """
    import shapely.geometry as geom

    all_coords: list[tuple[float, float]] = []
    for g in geometries_wgs84:
        if g is None:
            continue
        if g.geom_type == "Polygon":
            coords = list(g.exterior.coords)
        elif g.geom_type == "MultiPolygon":
            coords = []
            for poly in g.geoms:
                coords.extend(poly.exterior.coords)
        else:
            coords = []
        for lon, lat in coords:
            all_coords.append(wgs84_to_mercator(lon, lat))

    if not all_coords:
        return (-20037508, -20037508, 20037508, 20037508)

    xs = [c[0] for c in all_coords]
    ys = [c[1] for c in all_coords]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    buf_x = (xmax - xmin) * buffer_pct
    buf_y = (ymax - ymin) * buffer_pct
    return (xmin - buf_x, ymin - buf_y, xmax + buf_x, ymax + buf_y)


def choose_tile_zoom(
    extent_mercator: tuple[float, float, float, float],
    target_width_px: int = 1500,
    max_tiles: int = _MAX_TILES,
) -> int | None:
    """Choose a tile zoom so the stitched result is approximately target_width_px wide.

    Returns None if reasonable zoom cannot be found within tile limits.
    """
    xmin, ymin, xmax, ymax = extent_mercator
    mid_y = (ymin + ymax) / 2.0
    extent_width_m = xmax - xmin

    for zoom in range(20, 0, -1):
        # approximate meters per pixel at mid latitude
        m_per_px = _tile_size_px(zoom, mercator_to_wgs84(0.0, mid_y)[1])
        width_px = extent_width_m / m_per_px
        # number of tiles needed
        n = 2.0 ** zoom
        tile_m = 2.0 * math.pi * 6378137.0 / n
        tiles_x = max(1, int(math.ceil(extent_width_m / tile_m)))
        # estimate tiles_y from aspect ratio
        extent_height_m = ymax - ymin
        tiles_y = max(1, int(math.ceil(extent_height_m / tile_m)))
        total = tiles_x * tiles_y
        if total <= max_tiles and width_px >= target_width_px * 0.7:
            return zoom
        if total <= max_tiles and zoom <= 10:
            return zoom
    return None


def _fetch_tile(url: str, timeout: int = _TILE_TIMEOUT, retries: int = _TILE_RETRIES) -> Image.Image | None:
    """Download a single tile image with retries."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            return Image.open(io.BytesIO(resp.content)).convert("RGB")
        except Exception:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
            continue
    return None


def fetch_basemap_image(
    extent_mercator: tuple[float, float, float, float],
    zoom: int | None = None,
    tile_url_template: str = _DEFAULT_TILE_URL,
    no_basemap: bool = False,
) -> tuple[Image.Image | None, str]:
    """Download tiles, stitch, crop, and return the basemap image + a status message.

    Returns (image, status_message).  image is None if skipped or failed.
    """
    if no_basemap:
        return (None, "basemap skipped (--no-basemap)")

    if zoom is None:
        zoom = choose_tile_zoom(extent_mercator)
        if zoom is None:
            return (None, "basemap skipped (no suitable zoom within tile limits)")

    xmin, ymin, xmax, ymax = extent_mercator
    # Determine tile range
    west, south = mercator_to_wgs84(xmin, ymin)
    east, north = mercator_to_wgs84(xmax, ymax)
    tx_min, ty_max = _tile_xy(zoom, west, north)
    tx_max, ty_min = _tile_xy(zoom, east, south)

    # Clamp and count
    n = 2 ** zoom
    tx_min = max(0, tx_min)
    tx_max = min(n - 1, tx_max)
    ty_min = max(0, ty_min)
    ty_max = min(n - 1, ty_max)

    tile_count = (tx_max - tx_min + 1) * (ty_max - ty_min + 1)
    if tile_count > _MAX_TILES:
        return (None, f"basemap skipped ({tile_count} tiles exceeds limit {_MAX_TILES})")

    tile_size = 256
    canvas_width = (tx_max - tx_min + 1) * tile_size
    canvas_height = (ty_max - ty_min + 1) * tile_size
    canvas = Image.new("RGB", (canvas_width, canvas_height), (220, 220, 220))

    failed = 0
    for tx in range(tx_min, tx_max + 1):
        for ty in range(ty_min, ty_max + 1):
            url = tile_url_template.format(z=zoom, x=tx, y=ty)
            tile = _fetch_tile(url)
            if tile is None:
                failed += 1
                continue
            paste_x = (tx - tx_min) * tile_size
            paste_y = (ty - ty_min) * tile_size
            canvas.paste(tile, (paste_x, paste_y))

    if failed == tile_count:
        return (None, "basemap failed (all tiles unavailable)")

    # Crop to exact mercator bounds
    # Compute pixel offsets within the canvas for the requested extent
    twest, tsouth, teast, tnorth = _tile_bounds(zoom, tx_min, ty_min)
    twest_m, _ = wgs84_to_mercator(twest, 0)
    _, tnorth_m = wgs84_to_mercator(0, tnorth)
    teast_m, _ = wgs84_to_mercator(teast, 0)
    _, tsouth_m = wgs84_to_mercator(0, tsouth)

    tile_width_m = teast_m - twest_m
    tile_height_m = tsouth_m - tnorth_m

    if tile_width_m <= 0 or tile_height_m <= 0:
        return (None, "basemap failed (invalid tile math)")

    px_per_m_x = tile_size / tile_width_m
    px_per_m_y = tile_size / tile_height_m

    left = int((xmin - twest_m) * px_per_m_x)
    top = int((tnorth_m - ymax) * px_per_m_y)
    right = int((xmax - twest_m) * px_per_m_x)
    bottom = int((tnorth_m - ymin) * px_per_m_y)

    left = max(0, min(left, canvas_width))
    top = max(0, min(top, canvas_height))
    right = max(left, min(right, canvas_width))
    bottom = max(top, min(bottom, canvas_height))

    if right - left < 2 or bottom - top < 2:
        return (None, "basemap failed (cropped to nothing)")

    cropped = canvas.crop((left, top, right, bottom))
    status = "basemap ok" if failed == 0 else f"basemap ok ({failed} tiles missing)"
    return (cropped, status)


def image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Serialize a PIL Image to a base64-encoded data URI string."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def build_neutral_basemap_image(
    extent_mercator: tuple[float, float, float, float],
    width_px: int = 1500,
) -> Image.Image:
    """Create a simple neutral background image for offline dashboards."""
    import shapely.geometry as geom

    xmin, ymin, xmax, ymax = extent_mercator
    aspect = max(0.1, (ymax - ymin) / max(0.1, (xmax - xmin)))
    height_px = int(width_px * aspect)
    img = Image.new("RGB", (width_px, height_px), (240, 240, 240))
    return img
