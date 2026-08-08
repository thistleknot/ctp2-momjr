"""
ctpedit_gui.py — Streamlit-based form GUI for ctpedit dimension CSV editing.

Loads dimension CSVs as DataFrames, applies aggregate transforms, runs
interactive scripts, previews diffs, and regenerates the mod via ctpedit.py.

Launch: streamlit run ctpedit_gui.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import streamlit as st

# ── Path setup (mirrors ctpedit.py constants) ──────────────────────────────────
TOOLS_DIR = Path(__file__).resolve().parent
MOMJR_CSV = TOOLS_DIR / "momjr_csv"
PIPELINES_DIR = MOMJR_CSV / "pipelines"

# Import ctpedit for DIMENSIONS dict
sys.path.insert(0, str(TOOLS_DIR))
from ctpedit import DIMENSIONS  # noqa: E402

# Import GUI modules
from gui.transforms import TRANSFORM_CATALOG, apply_transform  # noqa: E402
from gui.script_runner import (  # noqa: E402
    ScriptSandboxError,
    ScriptTimeout,
    run_script,
)
from gui.diff_view import compute_diff, format_stats_table  # noqa: E402

# ── Streamlit config ───────────────────────────────────────────────────────────
st.set_page_config(page_title="ctpedit GUI", layout="wide", page_icon="⚔️")

MAX_UNDO = 50


# ── Helper functions ───────────────────────────────────────────────────────────


def _get_csv_files() -> Dict[str, List[Path]]:
    """Group CSV files by dimension based on DIMENSIONS[dim]['sources']."""
    grouped: Dict[str, List[Path]] = {}
    assigned: set = set()

    for dim_key, dim_info in DIMENSIONS.items():
        label = dim_info["label"]
        sources = dim_info.get("sources", [])
        paths = []
        for src in sources:
            p = MOMJR_CSV / src
            if p.exists():
                paths.append(p)
                assigned.add(p.name)
        if paths:
            grouped[label] = paths

    # Ungrouped CSVs
    ungrouped = []
    for f in sorted(MOMJR_CSV.glob("*.csv")):
        if f.name not in assigned:
            ungrouped.append(f)
    if ungrouped:
        grouped["Other"] = ungrouped

    return grouped


def _load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV preserving all columns as-is."""
    return pd.read_csv(path, encoding="utf-8", keep_default_na=False)


def _save_csv(df: pd.DataFrame, path: Path) -> None:
    """Save DataFrame to CSV with LF line endings, UTF-8 no BOM, backup first."""
    # Create backup
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"{path.name}.bak_gui_{timestamp}")
    if path.exists():
        backup.write_bytes(path.read_bytes())

    # Write with LF endings (open in binary mode with newline='')
    csv_text = df.to_csv(index=False, lineterminator="\n")
    path.write_text(csv_text, encoding="utf-8", newline="")


def _push_history(key_prefix: str) -> None:
    """Push current WorkingDF to undo history."""
    history = st.session_state.get(f"{key_prefix}_history", [])
    current = st.session_state.get(f"{key_prefix}_working")
    if current is not None:
        history.append(current.copy())
        if len(history) > MAX_UNDO:
            history = history[-MAX_UNDO:]
        st.session_state[f"{key_prefix}_history"] = history
        # Clear redo stack on new action
        st.session_state[f"{key_prefix}_redo"] = []


def _dimension_for_csv(csv_name: str) -> Optional[str]:
    """Find which dimension key owns a given CSV filename."""
    for dim_key, dim_info in DIMENSIONS.items():
        if csv_name in dim_info.get("sources", []):
            return dim_key
    return None


# ── Session state initialization ───────────────────────────────────────────────


def _init_state(key_prefix: str, df: pd.DataFrame) -> None:
    """Initialize session state for a CSV if not already set."""
    if f"{key_prefix}_original" not in st.session_state:
        st.session_state[f"{key_prefix}_original"] = df.copy()
        st.session_state[f"{key_prefix}_working"] = df.copy()
        st.session_state[f"{key_prefix}_history"] = []
        st.session_state[f"{key_prefix}_redo"] = []
        st.session_state[f"{key_prefix}_pipeline"] = []


# ── Sidebar ────────────────────────────────────────────────────────────────────

st.sidebar.title("⚔️ ctpedit GUI")
st.sidebar.markdown("Dimension CSV Editor")

csv_groups = _get_csv_files()

# Build flat list for selectbox with group labels
csv_options: List[str] = []
csv_paths: Dict[str, Path] = {}
for group_label, paths in csv_groups.items():
    for p in paths:
        display = f"[{group_label}] {p.name} ({len(_load_csv(p))} rows)"
        csv_options.append(display)
        csv_paths[display] = p

selected_display = st.sidebar.selectbox("Select CSV", csv_options)
if not selected_display:
    st.info("Select a CSV file from the sidebar to begin editing.")
    st.stop()

selected_path = csv_paths[selected_display]
key_prefix = f"csv_{selected_path.stem}"

# Load and init
raw_df = _load_csv(selected_path)
_init_state(key_prefix, raw_df)

original_df: pd.DataFrame = st.session_state[f"{key_prefix}_original"]
working_df: pd.DataFrame = st.session_state[f"{key_prefix}_working"]

# ── Main area tabs ─────────────────────────────────────────────────────────────

tab_editor, tab_transforms, tab_repl, tab_diff, tab_pipeline, tab_actions = st.tabs(
    ["DataFrame Editor", "Transforms", "Script REPL", "Diff", "Pipeline", "Actions"]
)

# ── Tab 1: DataFrame Editor ────────────────────────────────────────────────────

with tab_editor:
    st.subheader(f"Editing: {selected_path.name}")

    # Summary stats for numeric columns
    numeric_cols = working_df.select_dtypes(include=[np.number]).columns.tolist()
    if numeric_cols:
        with st.expander("Column Statistics", expanded=False):
            stats_df = working_df[numeric_cols].describe().T
            stats_df = stats_df[["min", "max", "mean", "50%", "std"]].rename(
                columns={"50%": "median"}
            )
            st.dataframe(stats_df, use_container_width=True)

    # Editable data editor
    edited_df = st.data_editor(
        working_df,
        use_container_width=True,
        num_rows="dynamic",
        key=f"{key_prefix}_editor",
    )

    # Detect if user edited inline
    if not edited_df.equals(working_df):
        _push_history(key_prefix)
        st.session_state[f"{key_prefix}_working"] = edited_df
        working_df = edited_df

    # Row management
    col_add, col_del = st.columns(2)
    with col_add:
        if st.button("Add Row", key=f"{key_prefix}_add_row"):
            _push_history(key_prefix)
            # Create new row with dimension-appropriate defaults
            new_row = {}
            for col in working_df.columns:
                if pd.api.types.is_numeric_dtype(working_df[col]):
                    if "index" in col.lower() or "id" in col.lower():
                        # Auto-increment
                        new_row[col] = (
                            int(working_df[col].max()) + 1
                            if not working_df[col].empty
                            else 0
                        )
                    else:
                        new_row[col] = 0
                else:
                    new_row[col] = ""
            new_df = pd.concat(
                [working_df, pd.DataFrame([new_row])], ignore_index=True
            )
            st.session_state[f"{key_prefix}_working"] = new_df
            st.rerun()

    with col_del:
        rows_to_delete = st.multiselect(
            "Select rows to delete (by index)",
            options=list(working_df.index),
            key=f"{key_prefix}_del_rows",
        )
        if st.button("Delete Selected Rows", key=f"{key_prefix}_del_btn"):
            if rows_to_delete:
                _push_history(key_prefix)
                new_df = working_df.drop(index=rows_to_delete).reset_index(drop=True)
                st.session_state[f"{key_prefix}_working"] = new_df
                st.rerun()

# ── Tab 2: Transforms ─────────────────────────────────────────────────────────

with tab_transforms:
    st.subheader("Aggregate Transforms")

    # Select transform
    transform_ids = list(TRANSFORM_CATALOG.keys())
    transform_names = [TRANSFORM_CATALOG[t]["name"] for t in transform_ids]
    selected_idx = st.selectbox(
        "Transform",
        range(len(transform_ids)),
        format_func=lambda i: transform_names[i],
        key=f"{key_prefix}_transform_select",
    )
    selected_transform_id = transform_ids[selected_idx]
    transform_info = TRANSFORM_CATALOG[selected_transform_id]

    # Select columns
    available_cols = (
        working_df.select_dtypes(include=[np.number]).columns.tolist()
        if transform_info["mode"] == "series"
        else working_df.columns.tolist()
    )
    selected_cols = st.multiselect(
        "Target Columns",
        available_cols,
        key=f"{key_prefix}_transform_cols",
    )

    # Parameter inputs
    params: Dict[str, Any] = {}
    for param_name, param_type in transform_info["params"].items():
        if param_type == float:
            params[param_name] = st.number_input(
                param_name,
                value=1.0,
                step=0.1,
                key=f"{key_prefix}_param_{param_name}",
            )
        elif param_type == int:
            params[param_name] = int(
                st.number_input(
                    param_name,
                    value=0,
                    step=1,
                    key=f"{key_prefix}_param_{param_name}",
                )
            )
        elif param_type == "ndarray":
            st.text_area(
                f"{param_name} (JSON 2D array)",
                value="[[1, 0], [0, 1]]",
                key=f"{key_prefix}_param_{param_name}",
            )
            try:
                params[param_name] = np.array(
                    json.loads(
                        st.session_state.get(
                            f"{key_prefix}_param_{param_name}", "[[1,0],[0,1]]"
                        )
                    )
                )
            except (json.JSONDecodeError, ValueError):
                st.error("Invalid JSON array for weights")
                params[param_name] = np.eye(2)

    # Optional row filter
    row_filter = st.text_input(
        "Row Filter (optional, e.g. sphere == 'chaos')",
        key=f"{key_prefix}_row_filter",
    )

    # Preview / Apply
    col_preview, col_apply = st.columns(2)

    with col_preview:
        if st.button("Preview", key=f"{key_prefix}_preview_btn"):
            if not selected_cols:
                st.warning("Select at least one column.")
            else:
                try:
                    preview_df = apply_transform(
                        working_df,
                        selected_transform_id,
                        selected_cols,
                        params,
                        row_filter=row_filter or None,
                    )
                    # Show before/after comparison
                    compare = pd.DataFrame()
                    for col in selected_cols:
                        compare[f"{col} (before)"] = working_df[col]
                        compare[f"{col} (after)"] = preview_df[col]
                    st.dataframe(compare, use_container_width=True)
                except Exception as e:
                    st.error(f"Transform error: {e}")

    with col_apply:
        if st.button("Apply", key=f"{key_prefix}_apply_btn"):
            if not selected_cols:
                st.warning("Select at least one column.")
            else:
                try:
                    _push_history(key_prefix)
                    new_df = apply_transform(
                        working_df,
                        selected_transform_id,
                        selected_cols,
                        params,
                        row_filter=row_filter or None,
                    )
                    st.session_state[f"{key_prefix}_working"] = new_df
                    # Record in pipeline
                    pipeline = st.session_state.get(f"{key_prefix}_pipeline", [])
                    pipeline.append(
                        {
                            "transform_id": selected_transform_id,
                            "params": {
                                k: v.tolist() if isinstance(v, np.ndarray) else v
                                for k, v in params.items()
                            },
                            "columns": selected_cols,
                            "row_filter": row_filter or None,
                        }
                    )
                    st.session_state[f"{key_prefix}_pipeline"] = pipeline
                    st.success("Transform applied.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Transform error: {e}")

# ── Tab 3: Script REPL ────────────────────────────────────────────────────────

with tab_repl:
    st.subheader("Script REPL")
    st.caption(
        "Available: `df` (WorkingDF, mutable), `original` (read-only), `np`, `pd`. "
        "No file I/O, no imports beyond np/pd."
    )

    code = st.text_area(
        "Python code",
        height=200,
        placeholder="# Example: scale a column\ndf['cost'] = df['cost'] * 1.5",
        key=f"{key_prefix}_repl_code",
    )

    if st.button("Run", key=f"{key_prefix}_repl_run"):
        if code.strip():
            try:
                _push_history(key_prefix)
                new_df, output = run_script(code, working_df, original_df)
                st.session_state[f"{key_prefix}_working"] = new_df
                if output:
                    st.code(output, language="text")
                st.success("Script executed successfully.")
                st.rerun()
            except ScriptTimeout as e:
                st.error(f"⏱️ {e}")
            except ScriptSandboxError as e:
                st.error(f"🚫 {e}")
            except Exception as e:
                st.error(f"Script error: {type(e).__name__}: {e}")

# ── Tab 4: Diff ───────────────────────────────────────────────────────────────

with tab_diff:
    st.subheader("Diff: Original vs Working")

    # Refresh working_df reference
    working_df = st.session_state[f"{key_prefix}_working"]
    diff_result = compute_diff(original_df, working_df)

    if (
        diff_result.row_count_delta == 0
        and diff_result.changed_rows.empty
        and diff_result.added_rows.empty
        and diff_result.removed_rows.empty
    ):
        st.info("No changes detected.")
    else:
        # Record count delta
        if diff_result.row_count_delta != 0:
            delta_sign = "+" if diff_result.row_count_delta > 0 else ""
            st.metric(
                "Row Count Delta",
                f"{len(working_df)} rows",
                f"{delta_sign}{diff_result.row_count_delta}",
            )

        # Changed columns
        if diff_result.changed_columns:
            st.markdown(
                f"**Changed columns:** {', '.join(diff_result.changed_columns)}"
            )

        # Column stats
        stats_table = format_stats_table(diff_result.column_stats)
        if "info" not in stats_table.columns:
            with st.expander("Column Distribution Changes", expanded=True):
                st.dataframe(stats_table, use_container_width=True)

        # Added rows
        if not diff_result.added_rows.empty:
            with st.expander(
                f"Added Rows ({len(diff_result.added_rows)})", expanded=False
            ):
                st.dataframe(diff_result.added_rows, use_container_width=True)

        # Removed rows
        if not diff_result.removed_rows.empty:
            with st.expander(
                f"Removed Rows ({len(diff_result.removed_rows)})", expanded=False
            ):
                st.dataframe(diff_result.removed_rows, use_container_width=True)

        # Changed rows
        if not diff_result.changed_rows.empty:
            with st.expander(
                f"Changed Rows ({len(diff_result.changed_rows)})", expanded=True
            ):
                st.dataframe(diff_result.changed_rows, use_container_width=True)

# ── Tab 5: Pipeline ───────────────────────────────────────────────────────────

with tab_pipeline:
    st.subheader("Transform Pipeline")
    pipeline = st.session_state.get(f"{key_prefix}_pipeline", [])

    if not pipeline:
        st.info("No transforms recorded yet. Apply transforms in the Transforms tab.")
    else:
        for i, step in enumerate(pipeline):
            t_name = TRANSFORM_CATALOG.get(step["transform_id"], {}).get(
                "name", step["transform_id"]
            )
            cols = ", ".join(step["columns"])
            filt = f" WHERE {step['row_filter']}" if step.get("row_filter") else ""
            st.text(f"{i+1}. {t_name}({step['params']}) → [{cols}]{filt}")

    st.divider()

    # Apply All (replay from original)
    if st.button("Apply All (replay from original)", key=f"{key_prefix}_replay"):
        if pipeline:
            _push_history(key_prefix)
            result = original_df.copy()
            for step in pipeline:
                p = step["params"].copy()
                # Reconvert weights if present
                if "weights" in p and isinstance(p["weights"], list):
                    p["weights"] = np.array(p["weights"])
                result = apply_transform(
                    result,
                    step["transform_id"],
                    step["columns"],
                    p,
                    row_filter=step.get("row_filter"),
                )
            st.session_state[f"{key_prefix}_working"] = result
            st.success("Pipeline replayed from original.")
            st.rerun()

    st.divider()

    # Export Pipeline
    col_export, col_import = st.columns(2)

    with col_export:
        pipeline_name = st.text_input(
            "Pipeline name", key=f"{key_prefix}_pipeline_name"
        )
        if st.button("Export Pipeline", key=f"{key_prefix}_export_pipeline"):
            if not pipeline:
                st.warning("No pipeline to export.")
            elif not pipeline_name:
                st.warning("Enter a pipeline name.")
            else:
                PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
                export_data = {
                    "name": pipeline_name,
                    "target_csv": selected_path.name,
                    "steps": pipeline,
                }
                out_path = PIPELINES_DIR / f"{pipeline_name}.json"
                out_path.write_text(
                    json.dumps(export_data, indent=2), encoding="utf-8"
                )
                st.success(f"Exported to {out_path.relative_to(TOOLS_DIR)}")

    with col_import:
        # List available pipeline files
        if PIPELINES_DIR.exists():
            pipeline_files = sorted(PIPELINES_DIR.glob("*.json"))
        else:
            pipeline_files = []

        if pipeline_files:
            selected_pipeline = st.selectbox(
                "Import pipeline",
                pipeline_files,
                format_func=lambda p: p.stem,
                key=f"{key_prefix}_import_select",
            )
            if st.button("Import Pipeline", key=f"{key_prefix}_import_pipeline"):
                data = json.loads(selected_pipeline.read_text(encoding="utf-8"))
                st.session_state[f"{key_prefix}_pipeline"] = data.get("steps", [])
                st.success(f"Imported pipeline: {data.get('name', selected_pipeline.stem)}")
                st.rerun()
        else:
            st.info("No saved pipelines found.")

# ── Tab 6: Actions ─────────────────────────────────────────────────────────────

with tab_actions:
    st.subheader("Actions")

    # Undo / Redo / Reset
    col_undo, col_redo, col_reset = st.columns(3)

    with col_undo:
        history = st.session_state.get(f"{key_prefix}_history", [])
        if st.button(
            f"Undo ({len(history)})", key=f"{key_prefix}_undo", disabled=not history
        ):
            redo_stack = st.session_state.get(f"{key_prefix}_redo", [])
            redo_stack.append(st.session_state[f"{key_prefix}_working"].copy())
            st.session_state[f"{key_prefix}_redo"] = redo_stack
            st.session_state[f"{key_prefix}_working"] = history.pop()
            st.session_state[f"{key_prefix}_history"] = history
            st.rerun()

    with col_redo:
        redo_stack = st.session_state.get(f"{key_prefix}_redo", [])
        if st.button(
            f"Redo ({len(redo_stack)})",
            key=f"{key_prefix}_redo_btn",
            disabled=not redo_stack,
        ):
            history = st.session_state.get(f"{key_prefix}_history", [])
            history.append(st.session_state[f"{key_prefix}_working"].copy())
            st.session_state[f"{key_prefix}_history"] = history
            st.session_state[f"{key_prefix}_working"] = redo_stack.pop()
            st.session_state[f"{key_prefix}_redo"] = redo_stack
            st.rerun()

    with col_reset:
        if st.button("Reset to Disk", key=f"{key_prefix}_reset"):
            fresh = _load_csv(selected_path)
            st.session_state[f"{key_prefix}_original"] = fresh.copy()
            st.session_state[f"{key_prefix}_working"] = fresh.copy()
            st.session_state[f"{key_prefix}_history"] = []
            st.session_state[f"{key_prefix}_redo"] = []
            st.session_state[f"{key_prefix}_pipeline"] = []
            st.success("Reset to on-disk state.")
            st.rerun()

    st.divider()

    # Save CSV
    if st.button("💾 Save CSV", key=f"{key_prefix}_save", type="primary"):
        working_df = st.session_state[f"{key_prefix}_working"]
        _save_csv(working_df, selected_path)
        st.session_state[f"{key_prefix}_original"] = working_df.copy()
        st.session_state[f"{key_prefix}_history"] = []
        st.session_state[f"{key_prefix}_redo"] = []
        st.success(f"Saved {selected_path.name} (backup created).")

    st.divider()

    # Patching
    st.markdown("### Patch (Regenerate)")

    col_patch_all, col_patch_dim = st.columns(2)

    with col_patch_all:
        if st.button("Patch All", key=f"{key_prefix}_patch_all"):
            with st.spinner("Running ctpedit.py patch all..."):
                result = subprocess.run(
                    [sys.executable, "ctpedit.py", "patch", "all"],
                    cwd=str(TOOLS_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            if result.returncode == 0:
                st.success("Regeneration complete.")
            else:
                st.error("Patch failed.")
            with st.expander("Output", expanded=result.returncode != 0):
                st.code(result.stdout + result.stderr, language="text")

    with col_patch_dim:
        # Only show dimensions that have source CSVs
        patchable_dims = [
            k for k, v in DIMENSIONS.items() if v.get("sources")
        ]
        selected_dim = st.selectbox(
            "Dimension",
            patchable_dims,
            format_func=lambda d: DIMENSIONS[d]["label"],
            key=f"{key_prefix}_patch_dim_select",
        )
        if st.button(f"Patch {DIMENSIONS[selected_dim]['label']}", key=f"{key_prefix}_patch_dim"):
            st.warning(
                "⚠️ Selective patch — cascade-dependent files for other dimensions "
                "may be stale. Run Patch All for full consistency."
            )
            with st.spinner(f"Running ctpedit.py patch {selected_dim}..."):
                result = subprocess.run(
                    [sys.executable, "ctpedit.py", "patch", selected_dim],
                    cwd=str(TOOLS_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            if result.returncode == 0:
                st.success(f"Patch {selected_dim} complete.")
            else:
                st.error(f"Patch {selected_dim} failed.")
            with st.expander("Output", expanded=result.returncode != 0):
                st.code(result.stdout + result.stderr, language="text")

    st.divider()

    # Audit
    if st.button("Run Audit", key=f"{key_prefix}_audit"):
        with st.spinner("Running mom_audit.py..."):
            result = subprocess.run(
                [sys.executable, "mom_audit.py"],
                cwd=str(TOOLS_DIR),
                capture_output=True,
                text=True,
                timeout=60,
            )
        if result.returncode == 0:
            st.success("Audit passed.")
        else:
            st.error("Audit failed.")
        with st.expander("Audit Output", expanded=result.returncode != 0):
            st.code(result.stdout + result.stderr, language="text")
