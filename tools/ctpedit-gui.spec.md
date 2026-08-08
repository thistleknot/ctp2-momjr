---
description: 'Form-based GUI for ctpedit that loads dimension CSVs as dataframes, applies aggregate transforms, runs interactive scripts, previews diffs, and regenerates the mod via ctpedit.py patch all'
import:
  - ctp2-modding-rules
---

***definitions***

- :SourceCSV: is any `*.csv` file under `Scenarios/mom/tools/momjr_csv/` that serves as input to the generator pipeline.
- :Dimension: is a named group of game records (advances, units, improvements, wonders, terrain, governments, tile_improvements, orders, goods, concepts) as defined in the `DIMENSIONS` dict in `ctpedit.py`.
- :WorkingDF: is the in-memory pandas DataFrame representing the current edit state of a :SourceCSV:, not yet written to disk.
- :OriginalDF: is the DataFrame loaded from the on-disk :SourceCSV: at session start or after a reset; serves as the baseline for diffs.
- :AggregateTransform: is a preset mathematical operation (scaling, normalization, redistribution, clamping, etc.) applied to one or more numeric columns of a :WorkingDF:.
- :TransformPipeline: is an ordered list of :AggregateTransform: definitions that replays deterministically from :OriginalDF:.
- :ScriptREPL: is a code editor panel where the user types Python/NumPy code executed against the :WorkingDF: in a sandboxed namespace.
- :DiffPanel: is the UI region showing row-level and column-level deltas between :OriginalDF: and :WorkingDF:.
- :PatchAll: is the action of invoking `python ctpedit.py patch all` as a subprocess, which runs the full generator + audit pipeline.

***implementation reqs***

- Stack: Streamlit (per coding standards), pandas, numpy. No additional heavy deps.
- Entry point: `Scenarios/mom/tools/ctpedit_gui.py`.
- Supporting modules in `Scenarios/mom/tools/gui/`:
  - `__init__.py`
  - `transforms.py` — pure functions implementing each :AggregateTransform:.
  - `script_runner.py` — sandboxed `exec()` with restricted `__builtins__`, 10s timeout.
  - `diff_view.py` — column-level stats + row-level highlight rendering.
- Paths derived from existing constants in `ctpedit.py`: `TOOLS_DIR`, `MOMJR_CSV`.
- CSV write MUST use LF line endings (no CRLF) and UTF-8 without BOM — CTP2 engine requirement.
- Before overwriting a :SourceCSV:, create a backup at `<name>.csv.bak_gui_<ISO8601_timestamp>`.
- :PatchAll: invoked via `subprocess.run([sys.executable, "ctpedit.py", "patch", "all"], cwd=TOOLS_DIR, timeout=120)`.
- Undo stack capped at 50 DataFrame snapshots in `st.session_state`.
- :ScriptREPL: namespace exposes only: `df` (:WorkingDF:, mutable), `original` (:OriginalDF:, read-only copy), `np`, `pd`. No `os`, `subprocess`, `importlib`, `open`, or network access.
- Launch command: `streamlit run ctpedit_gui.py` from `Scenarios/mom/tools/`.
- Pipeline persistence directory: `momjr_csv/pipelines/`. Each saved pipeline is a JSON file with schema: `{"name": str, "target_csv": str, "steps": [{"transform_id": str, "params": dict, "columns": [str], "row_filter": str|null}]}`.
- Selective patching: invoke `subprocess.run([sys.executable, "ctpedit.py", "patch", dim], cwd=TOOLS_DIR, timeout=120)` where `dim` is chosen from the `DIMENSIONS` keys.
- Row add/remove: new rows get defaults derived from column dtype (0 for numeric, empty string for text, auto-incremented `cell_index` where applicable). Deletions are soft until "Save CSV" commits them to disk.

- Preset :AggregateTransform: catalog:

  | ID | Name | Parameters | Formula |
  |----|------|------------|---------|
  | `linear_scale` | Linear Scale | `factor: float` | `col * factor` |
  | `minmax_norm` | Min-Max Normalize | `new_min, new_max: float` | `(col - col.min()) / (col.max() - col.min()) * (new_max - new_min) + new_min` |
  | `percentile_redist` | Percentile Redistribute | `percentile: int, target: float` | rank-preserving rescale so Pth percentile maps to `target` |
  | `power_curve` | Power Curve | `exponent: float` | normalize [0,1] → `x^exp` → rescale to original range |
  | `clamp` | Clamp | `floor, ceiling: float` | `col.clip(floor, ceiling)` |
  | `round` | Round | `decimals: int` | `col.round(decimals)` |
  | `offset` | Offset | `offset: float` | `col + offset` |
  | `rank_assign` | Rank Assign | `start, step: float` | `rank * step + start` |
  | `matrix_mult` | Matrix Multiply | `weights: ndarray` | `weights @ selected_cols.T` transposed back |

- Architecture diagram:

  ```
  ┌────────────────────────────────────────────────────┐
  │  Streamlit App (ctpedit_gui.py)                    │
  │                                                    │
  │  Sidebar: CSV file selector (grouped by dimension) │
  │                                                    │
  │  Main area:                                        │
  │   ┌─────────────┬──────────────┬────────────────┐  │
  │   │ DataFrame   │ Transform    │ Script REPL    │  │
  │   │ Editor      │ Panel        │ (code cell)    │  │
  │   └──────┬──────┴──────┬───────┴───────┬────────┘  │
  │          │             │               │            │
  │          ▼             ▼               ▼            │
  │   ┌───────────────────────────────────────────┐    │
  │   │  session_state: original_df, working_df,  │    │
  │   │  history[], redo_stack[], pipeline[]       │    │
  │   └─────────────────────┬─────────────────────┘    │
  │                         ▼                           │
  │   ┌───────────────────────────────────────────┐    │
  │   │  Diff Panel (row deltas + column stats)   │    │
  │   └─────────────────────┬─────────────────────┘    │
  │                         ▼                           │
  │   [ Save CSV ] [ Patch All ] [ Audit ] [ Undo/Redo/Reset ] │
  └────────────────────────────────────────────────────┘
             │ subprocess
             ▼
    ctpedit.py patch all → ctp2_generator.py → mom_audit.py
  ```

***test reqs***

- Each :AggregateTransform: in `transforms.py` MUST have a unit test in `tests/test_transforms.py` verifying mathematical correctness on a synthetic 20-row DataFrame.
- :ScriptREPL: sandbox MUST be tested for rejection of: `import os`, `open(...)`, `subprocess.run(...)`, `__import__('os')`. Test confirms `PermissionError` or equivalent raised.
- :ScriptREPL: timeout MUST be tested: a `while True: pass` script must be killed within 11 seconds.
- CSV round-trip test: load a :SourceCSV:, apply a transform, save, reload — verify byte-level LF endings and no BOM.
- :PatchAll: integration test: save a known-good transform to `units.csv`, run Patch All, confirm `mom_audit.py` exits 0.
- Diff correctness: apply a known transform, verify :DiffPanel: reports the exact changed rows/columns.
- Undo/redo: apply 3 transforms, undo 2, redo 1 — verify :WorkingDF: matches expected intermediate state.
- Gate: `python -m pytest tests/test_transforms.py tests/test_script_sandbox.py tests/test_csv_roundtrip.py tests/test_pipeline_persistence.py` MUST exit 0 before any PR merge.
- Pipeline persistence test: export a 3-step pipeline to JSON, import it in a fresh session, replay — verify :WorkingDF: matches expected output.
- Row addition test: add a row, save CSV, reload — verify new row present with correct defaults and file has valid LF encoding.
- Row deletion test: delete a row, save CSV, reload — verify row absent and remaining rows intact.
- Selective patch test: save a change to `units.csv`, run `patch units`, confirm `mom_audit.py` exits 0 for that dimension.

***functional specs***

- Given the GUI is launched, When the sidebar loads, Then every `*.csv` file in `momjr_csv/` MUST appear grouped under its :Dimension: label with a record-count badge.
- Given a :SourceCSV: is selected, When the DataFrame Editor renders, Then all rows and columns MUST be visible and inline-editable; numeric columns MUST show summary stats (min, max, mean, median, std) in a collapsed expander.
- Given a user selects one or more numeric columns and picks an :AggregateTransform:, When they click "Preview", Then a side-by-side before/after comparison table MUST appear showing affected rows with old→new values highlighted.
- Given a user clicks "Apply" on a previewed transform, Then :WorkingDF: MUST be mutated, the previous state MUST be pushed to the undo stack, and the :DiffPanel: MUST update.
- Given a user defines multiple transforms in a :TransformPipeline:, When they click "Apply All", Then transforms MUST execute in order starting from :OriginalDF:, producing a deterministic result regardless of prior manual edits.
- Given a user types valid Python in the :ScriptREPL: and clicks "Run", Then the script MUST execute against :WorkingDF:; if `df` is reassigned the new value MUST become :WorkingDF:; mutations in-place MUST be reflected.
- Given a user types Python that attempts file I/O or imports `os`, When executed, Then the REPL MUST display an error banner and :WorkingDF: MUST remain unchanged.
- Given a user types a script that runs longer than 10 seconds, When the timeout fires, Then execution MUST be killed and an error banner MUST display "Script timed out (10s limit)".
- Given :WorkingDF: differs from :OriginalDF:, When the :DiffPanel: renders, Then it MUST show: (a) row-level diff with green/red cell highlighting, (b) per-column old vs new distribution stats, (c) record-count delta if rows were added/removed.
- Given a user clicks "Save CSV", Then :WorkingDF: MUST be written to the :SourceCSV: path with LF line endings, UTF-8 no-BOM; a `.bak_gui_<timestamp>` backup of the prior file MUST be created; :OriginalDF: MUST be refreshed to match the new on-disk state.
- Given a user clicks "Patch All", Then `ctpedit.py patch all` MUST be invoked as a subprocess; stdout/stderr MUST stream into an expander; exit 0 MUST show a green "Regeneration complete" banner; non-zero MUST show a red banner with the error log.
- Given a user clicks "Undo", Then :WorkingDF: MUST revert to the previous history entry; "Redo" MUST restore the undone state. History depth MUST NOT exceed 50 entries.
- Given a user clicks "Reset", Then :WorkingDF: MUST reload from disk, history and redo stacks MUST clear.
- Given the GUI writes a CSV and the user triggers :PatchAll:, When `mom_audit.py` runs, Then it SHOULD report FAIL: 0 (green audit).
- Transforms MUST support an optional row filter (e.g. `sphere == "chaos"`) so operations can target subsets without affecting unmatched rows.
- The GUI MUST NOT write to any file outside `momjr_csv/` (and `momjr_csv/pipelines/`) — generated files are exclusively owned by the generator pipeline.
- Given a user clicks "Add Row", Then a new row MUST be appended to :WorkingDF: with dimension-appropriate defaults (empty strings for text columns, 0 for numeric columns, next sequential `cell_index` if that column exists). The row MUST be editable inline immediately.
- Given a user selects one or more rows and clicks "Delete Rows", Then those rows MUST be removed from :WorkingDF: and the deletion MUST be visible in the :DiffPanel: as removed rows (red highlight). Deletion is not persisted until "Save CSV".
- Given a user clicks "Export Pipeline", Then the current :TransformPipeline: MUST be serialized to `momjr_csv/pipelines/<user-provided-name>.json` containing an ordered list of transform ID, parameters, target columns, and optional row filter.
- Given a user clicks "Import Pipeline" and selects a JSON file from `momjr_csv/pipelines/`, Then the pipeline MUST be loaded, displayed in the pipeline panel, and "Apply All" MUST replay it from :OriginalDF:.
- Given a user selects a single :Dimension: from the "Patch" dropdown and clicks "Patch <dim>", Then `ctpedit.py patch <dim>` MUST be invoked as a subprocess; the UI MUST display a warning banner: "Selective patch — cascade-dependent files for other dimensions may be stale. Run Patch All for full consistency."
- Given the Actions panel renders, Then both "Patch All" and a dimension-selector + "Patch <dim>" button MUST be visible.

---

## Resolved Questions

1. **Row add/remove:** YES — the GUI supports both numeric rebalancing AND structural edits (adding/removing rows). New rows inherit dimension-appropriate defaults. Removal marks rows for deletion on save.
2. **Persist pipelines:** YES — a "Export Pipeline" button serializes the current :TransformPipeline: to a JSON file in `momjr_csv/pipelines/<name>.json`. An "Import Pipeline" button loads and replays a saved pipeline.
3. **Selective patching:** YES — the Actions panel exposes both "Patch All" and a per-:Dimension: "Patch <dim>" dropdown. UI warns that selective patching may leave cascade-dependent files stale.
