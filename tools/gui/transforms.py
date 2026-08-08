"""
gui.transforms — Pure aggregate transform functions for the ctpedit GUI.

Each function takes a pandas Series (or DataFrame subset) plus parameters,
and returns the transformed Series. No side effects, no I/O.

Transform catalog (from spec):
    linear_scale, minmax_norm, percentile_redist, power_curve,
    clamp, round, offset, rank_assign, matrix_mult
"""
from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd


# ── Individual transforms ──────────────────────────────────────────────────────


def linear_scale(col: pd.Series, factor: float) -> pd.Series:
    """Multiply column by a constant factor."""
    return col * factor


def minmax_norm(col: pd.Series, new_min: float, new_max: float) -> pd.Series:
    """Rescale column to [new_min, new_max] using min-max normalization."""
    col_min = col.min()
    col_max = col.max()
    if col_max == col_min:
        # Constant column — map to midpoint of target range
        return pd.Series(
            np.full(len(col), (new_min + new_max) / 2),
            index=col.index,
            name=col.name,
        )
    normalized = (col - col_min) / (col_max - col_min)
    return normalized * (new_max - new_min) + new_min


def percentile_redist(col: pd.Series, percentile: int, target: float) -> pd.Series:
    """Rank-preserving rescale so the Pth percentile maps to `target`.

    Values below the percentile are linearly scaled to [0, target].
    Values at or above are linearly scaled to [target, max_rescaled]
    preserving the original rank ordering and relative spacing within each half.
    """
    pval = np.percentile(col.dropna(), percentile)
    if pval == 0:
        # Avoid division by zero — fall back to linear scale
        return col * (target / max(col.max(), 1))

    result = col.copy().astype(float)
    below_mask = col <= pval
    above_mask = ~below_mask

    # Scale below-percentile values to [0, target]
    result[below_mask] = col[below_mask] / pval * target

    # Scale above-percentile values preserving spacing above target
    col_max = col.max()
    if col_max > pval:
        above_range = col_max - pval
        result[above_mask] = target + (col[above_mask] - pval) / above_range * (
            col_max * (target / pval) - target
        )
    return result


def power_curve(col: pd.Series, exponent: float) -> pd.Series:
    """Normalize to [0,1], apply x^exponent, rescale to original range."""
    col_min = col.min()
    col_max = col.max()
    if col_max == col_min:
        return col.copy()
    normalized = (col - col_min) / (col_max - col_min)
    curved = normalized ** exponent
    return curved * (col_max - col_min) + col_min


def clamp(col: pd.Series, floor: float, ceiling: float) -> pd.Series:
    """Clip column values to [floor, ceiling]."""
    return col.clip(lower=floor, upper=ceiling)


def round_values(col: pd.Series, decimals: int) -> pd.Series:
    """Round column to specified decimal places."""
    return col.round(decimals)


def offset(col: pd.Series, offset_val: float) -> pd.Series:
    """Add a constant offset to column values."""
    return col + offset_val


def rank_assign(col: pd.Series, start: float, step: float) -> pd.Series:
    """Replace values with rank-based assignment: rank * step + start."""
    ranks = col.rank(method="min")
    return ranks * step + start


def matrix_mult(df_subset: pd.DataFrame, weights: np.ndarray) -> pd.DataFrame:
    """Apply matrix multiplication: weights @ selected_cols.T, transposed back.

    Parameters
    ----------
    df_subset : DataFrame with the columns to multiply
    weights : 2D ndarray of shape (n_output_cols, n_input_cols)

    Returns
    -------
    DataFrame with n_output_cols columns (named col_0, col_1, ...)
    """
    result = (weights @ df_subset.values.T).T
    out_cols = [f"col_{i}" for i in range(result.shape[1])]
    return pd.DataFrame(result, index=df_subset.index, columns=out_cols)


# ── Registry ───────────────────────────────────────────────────────────────────

TRANSFORM_CATALOG = {
    "linear_scale": {
        "name": "Linear Scale",
        "params": {"factor": float},
        "func": linear_scale,
        "mode": "series",  # operates on a single Series
    },
    "minmax_norm": {
        "name": "Min-Max Normalize",
        "params": {"new_min": float, "new_max": float},
        "func": minmax_norm,
        "mode": "series",
    },
    "percentile_redist": {
        "name": "Percentile Redistribute",
        "params": {"percentile": int, "target": float},
        "func": percentile_redist,
        "mode": "series",
    },
    "power_curve": {
        "name": "Power Curve",
        "params": {"exponent": float},
        "func": power_curve,
        "mode": "series",
    },
    "clamp": {
        "name": "Clamp",
        "params": {"floor": float, "ceiling": float},
        "func": clamp,
        "mode": "series",
    },
    "round": {
        "name": "Round",
        "params": {"decimals": int},
        "func": round_values,
        "mode": "series",
    },
    "offset": {
        "name": "Offset",
        "params": {"offset": float},
        "func": offset,
        "mode": "series",
    },
    "rank_assign": {
        "name": "Rank Assign",
        "params": {"start": float, "step": float},
        "func": rank_assign,
        "mode": "series",
    },
    "matrix_mult": {
        "name": "Matrix Multiply",
        "params": {"weights": "ndarray"},
        "func": matrix_mult,
        "mode": "dataframe",  # operates on a DataFrame subset
    },
}


def apply_transform(
    df: pd.DataFrame,
    transform_id: str,
    columns: List[str],
    params: dict,
    row_filter: Optional[str] = None,
) -> pd.DataFrame:
    """Apply a registered transform to specified columns of a DataFrame.

    Parameters
    ----------
    df : The working DataFrame (will NOT be mutated — a copy is returned).
    transform_id : Key into TRANSFORM_CATALOG.
    columns : Column names to transform.
    params : Parameter dict matching the transform's param spec.
    row_filter : Optional pandas query string to filter rows (e.g. "sphere == 'chaos'").

    Returns
    -------
    New DataFrame with the transform applied.
    """
    entry = TRANSFORM_CATALOG[transform_id]
    func = entry["func"]
    mode = entry["mode"]

    result = df.copy()

    # Determine which rows to affect
    if row_filter:
        mask = result.eval(row_filter)
    else:
        mask = pd.Series(True, index=result.index)

    if mode == "series":
        for col_name in columns:
            series = result.loc[mask, col_name]
            transformed = func(series, **params)
            # Upcast column dtype if transform produces floats from ints
            if transformed.dtype != result[col_name].dtype:
                result[col_name] = result[col_name].astype(transformed.dtype)
            result.loc[mask, col_name] = transformed
    elif mode == "dataframe":
        subset = result.loc[mask, columns]
        transformed = func(subset, **params)
        # matrix_mult may change column count — use output columns
        for i, out_col in enumerate(transformed.columns):
            if i < len(columns):
                result.loc[mask, columns[i]] = transformed.iloc[:, i]

    return result
