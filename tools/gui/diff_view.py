"""
gui.diff_view — Column-level stats and row-level diff rendering for Streamlit.

Computes deltas between OriginalDF and WorkingDF, provides:
- Row-level diff with added/removed/changed classification
- Per-column distribution stats (before vs after)
- Styled DataFrames for Streamlit rendering
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class ColumnStats:
    """Distribution stats for a single numeric column."""

    name: str
    old_min: float = 0.0
    old_max: float = 0.0
    old_mean: float = 0.0
    old_median: float = 0.0
    old_std: float = 0.0
    new_min: float = 0.0
    new_max: float = 0.0
    new_mean: float = 0.0
    new_median: float = 0.0
    new_std: float = 0.0

    @property
    def changed(self) -> bool:
        return (
            self.old_min != self.new_min
            or self.old_max != self.new_max
            or self.old_mean != self.new_mean
        )


@dataclass
class DiffResult:
    """Complete diff between original and working DataFrames."""

    added_rows: pd.DataFrame  # Rows in working but not original (by index)
    removed_rows: pd.DataFrame  # Rows in original but not working
    changed_rows: pd.DataFrame  # Rows present in both but with value differences
    changed_columns: List[str] = field(default_factory=list)
    column_stats: List[ColumnStats] = field(default_factory=list)
    row_count_delta: int = 0


def compute_diff(original: pd.DataFrame, working: pd.DataFrame) -> DiffResult:
    """Compute row-level and column-level differences between two DataFrames.

    Parameters
    ----------
    original : The OriginalDF (baseline from disk).
    working : The WorkingDF (current edit state).

    Returns
    -------
    DiffResult with classified rows and column stats.
    """
    # Identify added/removed rows by index
    orig_idx = set(original.index)
    work_idx = set(working.index)

    added_indices = work_idx - orig_idx
    removed_indices = orig_idx - work_idx
    common_indices = sorted(orig_idx & work_idx)

    added_rows = working.loc[sorted(added_indices)] if added_indices else pd.DataFrame()
    removed_rows = (
        original.loc[sorted(removed_indices)] if removed_indices else pd.DataFrame()
    )

    # Find changed rows among common indices
    if common_indices:
        orig_common = original.loc[common_indices]
        work_common = working.loc[common_indices]

        # Compare cell by cell (handle NaN properly)
        diff_mask = (orig_common != work_common) & ~(
            orig_common.isna() & work_common.isna()
        )
        changed_row_mask = diff_mask.any(axis=1)
        changed_rows = work_common[changed_row_mask]
        changed_columns = list(diff_mask.columns[diff_mask.any(axis=0)])
    else:
        changed_rows = pd.DataFrame()
        changed_columns = []

    # Column stats for numeric columns
    column_stats = []
    common_cols = [c for c in original.columns if c in working.columns]
    for col in common_cols:
        if not pd.api.types.is_numeric_dtype(original[col]):
            continue
        old_series = pd.to_numeric(original[col], errors="coerce")
        new_series = pd.to_numeric(working[col], errors="coerce")
        stats = ColumnStats(
            name=col,
            old_min=float(old_series.min()) if not old_series.empty else 0.0,
            old_max=float(old_series.max()) if not old_series.empty else 0.0,
            old_mean=float(old_series.mean()) if not old_series.empty else 0.0,
            old_median=float(old_series.median()) if not old_series.empty else 0.0,
            old_std=float(old_series.std()) if not old_series.empty else 0.0,
            new_min=float(new_series.min()) if not new_series.empty else 0.0,
            new_max=float(new_series.max()) if not new_series.empty else 0.0,
            new_mean=float(new_series.mean()) if not new_series.empty else 0.0,
            new_median=float(new_series.median()) if not new_series.empty else 0.0,
            new_std=float(new_series.std()) if not new_series.empty else 0.0,
        )
        column_stats.append(stats)

    return DiffResult(
        added_rows=added_rows,
        removed_rows=removed_rows,
        changed_rows=changed_rows,
        changed_columns=changed_columns,
        column_stats=column_stats,
        row_count_delta=len(working) - len(original),
    )


def style_diff_dataframe(
    original: pd.DataFrame, working: pd.DataFrame
) -> pd.io.formats.style.Styler:
    """Return a styled DataFrame highlighting changed cells green, removed red.

    Best used on the intersection of common rows for display.
    """
    common_idx = original.index.intersection(working.index)
    common_cols = [c for c in original.columns if c in working.columns]

    if common_idx.empty or not common_cols:
        return working.style

    orig_subset = original.loc[common_idx, common_cols]
    work_subset = working.loc[common_idx, common_cols]

    def _highlight(row: pd.Series) -> List[str]:
        styles = []
        for col in row.index:
            if col not in orig_subset.columns:
                styles.append("")
                continue
            orig_val = orig_subset.at[row.name, col] if row.name in orig_subset.index else None
            if orig_val is None:
                styles.append("")
            elif pd.isna(row[col]) and pd.isna(orig_val):
                styles.append("")
            elif row[col] != orig_val:
                styles.append("background-color: #c6efce")  # green highlight
            else:
                styles.append("")
        return styles

    return work_subset.style.apply(_highlight, axis=1)


def format_stats_table(stats: List[ColumnStats]) -> pd.DataFrame:
    """Format column stats as a comparison table for Streamlit display."""
    changed_stats = [s for s in stats if s.changed]
    if not changed_stats:
        return pd.DataFrame({"info": ["No numeric columns changed"]})

    rows = []
    for s in changed_stats:
        rows.append(
            {
                "Column": s.name,
                "Old Min": f"{s.old_min:.2f}",
                "New Min": f"{s.new_min:.2f}",
                "Old Max": f"{s.old_max:.2f}",
                "New Max": f"{s.new_max:.2f}",
                "Old Mean": f"{s.old_mean:.2f}",
                "New Mean": f"{s.new_mean:.2f}",
                "Old Std": f"{s.old_std:.2f}",
                "New Std": f"{s.new_std:.2f}",
            }
        )
    return pd.DataFrame(rows)
