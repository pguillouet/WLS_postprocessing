import pandas as pd
import numpy as np


def interpolate_at(
    x_target,
    data: pd.DataFrame,
    y_key: str,
    x_key: str = None,
    circular: bool = False,
):
    """
    Interpolates a value from a DataFrame at x_target.

    DataFrame is expected to be sorted by x.
    If x is the index, leave x_key as None.
    Circular values such as heading are expected in degrees.

    No extrapolation is performed.
    """

    # Select x values from column or index
    x = data[x_key] if x_key is not None else data.index

    # Find insertion position
    idx = x.searchsorted(x_target)

    # Exact match
    if idx < len(data) and x[idx] == x_target:
        return data[y_key].iloc[idx]

    # Outside data range -> no extrapolation
    if idx == 0 or idx >= len(data):
        return np.nan

    # Nearest values before and after x_target
    x0 = x[idx - 1]
    x1 = x[idx]

    v0 = data[y_key].iloc[idx - 1]
    v1 = data[y_key].iloc[idx]

    # Linear interpolation factor
    alpha = (x_target - x0) / (x1 - x0)

    if not circular:
        return v0 + alpha * (v1 - v0)

    # Circular interpolation
    z0 = np.exp(1j * np.deg2rad(v0))
    z1 = np.exp(1j * np.deg2rad(v1))

    z_interp = (1 - alpha) * z0 + alpha * z1

    return np.rad2deg(np.angle(z_interp)) % 360


def circular_mean_degree(angles_deg):
    """
    Function for calculating circular mean of a pd.Series. 
    Values expected in degrees!
    """
    x = np.cos(np.radians(angles_deg))
    y = np.sin(np.radians(angles_deg))
    x_mean = np.nanmean(x)
    y_mean = np.nanmean(y)
    mean = np.degrees(np.arctan2(y_mean, x_mean)) % 360
    return mean
