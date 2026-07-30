"""Soil depth interpolation package.

Provides functions to fetch full SSURGO data and compute depth-interpolated
soil properties at standard depth slices.
"""

from soil_depth_interpolation import (
    fetch_full_ssurgo_for_field,
    interpolate_soil_depths,
    process_field,
    write_ssurgo_depth_interpolated,
    write_ssurgo_full_with_components,
)

__all__ = [
    "fetch_full_ssurgo_for_field",
    "interpolate_soil_depths",
    "process_field",
    "write_ssurgo_depth_interpolated",
    "write_ssurgo_full_with_components",
]
