"""
ctp2edit.py — CTP2 block-file editor  (CTPEdit53 + Dwarf Therapist model)

Grid view of every block in a CTP2 gamedata file.  Flags as checkboxes,
numerics as editable cells.  Apply formulas en masse to scale or translate
values across mods.  All edits go through the lossless round-trip parser —
same invariant as ctp2_parser.py: never hand-edit data files.

Modes
-----
  Desktop UI (interactive — native PyQt5 window):
    python  ctp2edit.py
    python  ctp2edit.py Units.txt          ← opens with file pre-loaded

  CLI (scriptable):
    python  ctp2edit.py Units.txt --cli --show
    python  ctp2edit.py Units.txt --cli --formula "Attack=Attack*2"
    python  ctp2edit.py Units.txt --cli --set "EnableAdvance=ADVANCE_WARRIOR_CODE" \\
                                        --filter "EnableAdvance.isna()"
    python  ctp2edit.py Units.txt --cli --enable-flag LossMoveToDmgNone
    python  ctp2edit.py Units.txt --cli --disable-flag NoZoc \\
                                        --filter "Category=='UNIT_CATEGORY_NAVAL'" \\
                                        --output Units_patched.txt

CLI flags
---------
  --formula  "COL=EXPR"     Vectorized pandas expression applied to KV column
  --set      "COL=VALUE"    Set KV column to a constant string/number
  --enable-flag  NAME       Add boolean flag to matching blocks
  --disable-flag NAME       Remove boolean flag from matching blocks
  --filter   "EXPR"         Pandas query restricting which blocks are affected
  --filter-block "ID,..."   Restrict to specific block IDs (comma-separated)
  --output   PATH           Write result here (default: overwrite input)
  --show                    Print column/flag summary; no save

Formula examples
----------------
  "Attack=Attack*2"                            scale attack
  "MaxMovePoints=MaxMovePoints.clip(upper=600)" cap movement
  "ShieldCost=int(cost_raw)*100"               recalculate from raw
  with --filter "Category=='UNIT_CATEGORY_AERIAL'"
"""
import argparse
import io
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

pd.set_option('future.no_silent_downcasting', True)

sys.path.insert(0, str(Path(__file__).parent))
from ctp2_roundtrip import Flag, KV, Nested, SubList, parse_file, render_file


# ── constants ─────────────────────────────────────────────────────────────────

# Fields known to always hold numeric values; controls column_config in UI
_NUMERIC_FIELDS: Set[str] = {
    'Attack', 'Defense', 'Armor', 'MaxHP', 'MaxMovePoints', 'VisionRange',
    'ActiveDefenseRange', 'ZBRangeAttack', 'Firepower', 'MaxFuel',
    'PowerPoints', 'ShieldCost', 'ShieldHunger', 'GoldHunger', 'FoodHunger',
    'BombRounds', 'BombardRange', 'SpaceLaunch',
    'Cost', 'Branch',                        # advance fields
    'ProductionCost',                        # building fields
    'MountedBonus', 'DefendAgainstSpies', 'WoodenShipBonus',
    'CityGrowthCoefficient', 'SettleSize',
}

_SL_SEP = '|'   # separator for multi-value sublist columns in DataFrame

# ── dimension / file registry ────────────────────────────────────────────────

_SCENARIO_ROOT = Path(os.environ.get(
    "CTP2_GENERATOR_SCENARIO_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000",
))

# Ordered map: display label → scenario-relative path
QUICK_FILES: "OrderedDict[str, str]" = OrderedDict([
    ("Units",              "default/gamedata/Units.txt"),
    ("Advances",           "default/gamedata/Advance.txt"),
    ("Improvements",       "default/gamedata/Improve.txt"),
    ("Wonders",            "default/gamedata/Wonder.txt"),
    ("Tile Improvements",  "default/gamedata/tileimp.txt"),
    ("Orders",             "default/gamedata/Orders.txt"),
    ("Governments",        "default/gamedata/govern.txt"),
    ("Terrain",            "default/gamedata/terrain.txt"),
    ("Goods",              "default/gamedata/goods.txt"),
    ("Buildings",          "default/gamedata/buildings.txt"),
    ("Concepts",           "default/gamedata/concept.txt"),
    ("Feats",              "default/gamedata/feat.txt"),
])


# ── editor core ───────────────────────────────────────────────────────────────

class CTP2Editor:
    """
    Load a CTP2 block file into three wide-format DataFrames for bulk editing.

    Precondition:  file parseable by ctp2_roundtrip.parse_file.
    Guarantee:     save() produces a file whose parse-tree equals edited state.
    Invariant:     original item order within each block is preserved on save.
    Invariant:     nested blocks (SlaveUprising etc.) are preserved unchanged.

    DataFrames
    ----------
    kv_df   : index=block_id, columns=kv_field_names, values=str|float
    flag_df : index=block_id, columns=flag_names,     values=bool
    sl_df   : index=block_id, columns=sublist_keys,   values=pipe-sep string
    """

    def __init__(self, filepath: Path):
        self.filepath = Path(filepath)
        self.blocks: OrderedDict = OrderedDict()
        self.kv_df:   pd.DataFrame = pd.DataFrame()
        self.flag_df: pd.DataFrame = pd.DataFrame()
        self.sl_df:   pd.DataFrame = pd.DataFrame()
        self._load()

    def _load(self):
        text = self.filepath.read_text(encoding='utf-8', errors='replace')
        self.blocks = parse_file(text)
        self._build_dfs()

    def reload(self):
        """Re-parse the file and reset all DataFrames (discard unsaved edits)."""
        self._load()

    # ── build DataFrames from blocks ─────────────────────────────────────────

    def _build_dfs(self):
        """Convert parsed blocks to three wide-format DataFrames."""
        kv_rows:   Dict[str, dict] = {}
        flag_rows: Dict[str, dict] = {}
        sl_rows:   Dict[str, dict] = {}

        for block_id, items in self.blocks.items():
            kv_rows[block_id]   = {}
            flag_rows[block_id] = {}
            sl_rows[block_id]   = {}
            sl_tmp: Dict[str, List[str]] = {}

            for item in items:
                if isinstance(item, KV):
                    kv_rows[block_id][item.key] = item.val
                elif isinstance(item, Flag):
                    flag_rows[block_id][item.name] = True
                elif isinstance(item, SubList):
                    sl_tmp.setdefault(item.key, []).append(item.val)
                # Nested: intentionally omitted — complex structure, preserved as-is

            for key, vals in sl_tmp.items():
                sl_rows[block_id][key] = _SL_SEP.join(vals)

        self.kv_df   = pd.DataFrame.from_dict(kv_rows,   orient='index')
        self.flag_df = (pd.DataFrame.from_dict(flag_rows, orient='index')
                          .infer_objects(copy=False).fillna(False).astype(bool))
        self.sl_df   = pd.DataFrame.from_dict(sl_rows,   orient='index')

        # Auto-coerce known numeric columns (and any that are purely numeric)
        for col in self.kv_df.columns:
            if col in _NUMERIC_FIELDS:
                self.kv_df[col] = pd.to_numeric(self.kv_df[col], errors='coerce')
            else:
                coerced = pd.to_numeric(self.kv_df[col], errors='coerce')
                if coerced.notna().sum() == self.kv_df[col].notna().sum():
                    self.kv_df[col] = coerced   # all non-null values are numeric

    # ── bulk operations ───────────────────────────────────────────────────────

    def apply_formula(self, col: str, expr: str, query: Optional[str] = None):
        """
        Apply a pandas/numpy expression to a KV column.

        Precondition: expr is a valid Python expression using column names.
        Column names are bound as Series variables in the expression namespace.

        Examples:
            apply_formula('Attack', 'Attack * 2')
            apply_formula('Attack', 'Attack * 1.5',
                          query="Category == 'UNIT_CATEGORY_NAVAL'")
        """
        df   = self.kv_df
        mask = self._parse_filter(query)

        local_vars = {c: df[c] for c in df.columns if df[c].notna().any()}
        local_vars['np']  = np
        local_vars['pd']  = pd

        result = eval(expr, {"__builtins__": {}}, local_vars)    # vectorized eval

        if hasattr(result, '__getitem__'):
            self.kv_df.loc[mask, col] = result.loc[mask]
        else:
            self.kv_df.loc[mask, col] = result

    def set_column(self, col: str, value: str, query: Optional[str] = None):
        """Set a KV column to a constant, optionally filtered by query."""
        mask = self._parse_filter(query)
        coerced = pd.to_numeric(value, errors='ignore')
        self.kv_df.loc[mask, col] = coerced

    def enable_flag(self, flag_name: str, query: Optional[str] = None):
        """Add a boolean flag to all (or filtered) blocks."""
        if flag_name not in self.flag_df.columns:
            self.flag_df[flag_name] = False
        mask = self._parse_filter(query)
        self.flag_df.loc[mask, flag_name] = True

    def disable_flag(self, flag_name: str, query: Optional[str] = None):
        """Remove a boolean flag from all (or filtered) blocks."""
        if flag_name not in self.flag_df.columns:
            return
        mask = self._parse_filter(query)
        self.flag_df.loc[mask, flag_name] = False

    def filter_blocks(self, ids: List[str]):
        """Restrict editor to a subset of block IDs (in place)."""
        keep = [i for i in ids if i in self.kv_df.index]
        self.kv_df   = self.kv_df.loc[keep]
        self.flag_df = self.flag_df.loc[keep]
        self.sl_df   = self.sl_df.loc[keep]

    # ── DataFrame → block reconstruction ─────────────────────────────────────

    def _rebuild_blocks(self) -> OrderedDict:
        """
        Reconstruct block dict from current DataFrames.

        Original item order within each block is preserved.  Items updated
        in the DataFrame are reflected; flags set to False are dropped; new
        fields added via formula are appended after existing items.
        """
        result: OrderedDict = OrderedDict()

        for block_id, orig_items in self.blocks.items():
            if block_id not in self.kv_df.index:
                result[block_id] = orig_items   # unchanged block
                continue

            new_items: List = []
            seen_kv:   Set[str] = set()
            seen_flag: Set[str] = set()
            seen_sl:   Set[str] = set()

            kv_row   = self.kv_df.loc[block_id]
            flag_row = self.flag_df.loc[block_id] if block_id in self.flag_df.index else pd.Series(dtype=bool)
            sl_row   = self.sl_df.loc[block_id]   if block_id in self.sl_df.index   else pd.Series(dtype=str)

            for item in orig_items:
                if isinstance(item, KV):
                    seen_kv.add(item.key)
                    val = kv_row.get(item.key) if item.key in kv_row.index else None
                    if val is None or (isinstance(val, float) and pd.isna(val)):
                        continue                     # field removed (set to NaN)
                    new_items.append(KV(item.key, _fmt_val(val)))

                elif isinstance(item, Flag):
                    seen_flag.add(item.name)
                    if flag_row.get(item.name, False):
                        new_items.append(item)       # False → flag disabled

                elif isinstance(item, SubList):
                    if item.key in seen_sl:
                        continue                     # multi-value: emit once below
                    seen_sl.add(item.key)
                    raw = sl_row.get(item.key) if item.key in sl_row.index else None
                    if raw and isinstance(raw, str):
                        for v in raw.split(_SL_SEP):
                            v = v.strip()
                            if v:
                                new_items.append(SubList(item.key, v))

                elif isinstance(item, Nested):
                    new_items.append(item)           # nested blocks are read-only

            # Append new KV fields added via formula (not in original block)
            for col in self.kv_df.columns:
                if col in seen_kv:
                    continue
                val = kv_row.get(col) if col in kv_row.index else None
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                new_items.append(KV(col, _fmt_val(val)))

            # Append new flags enabled via enable_flag (not in original block)
            for fname in self.flag_df.columns:
                if fname in seen_flag:
                    continue
                if flag_row.get(fname, False):
                    new_items.append(Flag(fname))

            result[block_id] = tuple(new_items)

        return result

    # ── save ──────────────────────────────────────────────────────────────────

    def save(self, output: Optional[Path] = None) -> Path:
        """Render edited blocks to file via the lossless round-trip renderer."""
        out_path = Path(output) if output else self.filepath
        blocks   = self._rebuild_blocks()
        text     = render_file(blocks)
        out_path.write_text(text, encoding='utf-8')
        return out_path

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_filter(self, query: Optional[str]) -> pd.Series:
        """
        Convert a filter string to a boolean mask over kv_df.index.

        Supports pandas query syntax on KV columns.  Returns all-True mask
        when query is None or empty.
        """
        if not query:
            return pd.Series(True, index=self.kv_df.index)
        return self.kv_df.eval(query, engine='python').astype(bool)

    def summary(self) -> str:
        kv_cols    = len(self.kv_df.columns)
        numeric_n  = sum(pd.api.types.is_numeric_dtype(self.kv_df[c])
                         for c in self.kv_df.columns)
        return (
            f"File:      {self.filepath}\n"
            f"Blocks:    {len(self.blocks)}\n"
            f"KV cols:   {kv_cols}  ({numeric_n} numeric, {kv_cols - numeric_n} string)\n"
            f"Flag cols: {len(self.flag_df.columns)}\n"
            f"SL cols:   {len(self.sl_df.columns)}\n"
        )

    def kv_column_report(self) -> str:
        lines = [f"{'column':<32} {'dtype':<12} {'present':>8}  sample"]
        lines.append('-' * 70)
        for col in self.kv_df.columns:
            nn     = self.kv_df[col].notna().sum()
            total  = len(self.kv_df)
            sample = str(self.kv_df[col].dropna().iloc[0]) if nn else ''
            dtype  = str(self.kv_df[col].dtype)
            lines.append(f"{col:<32} {dtype:<12} {nn:>4}/{total:<4}  {sample[:30]}")
        return '\n'.join(lines)

    def flag_column_report(self) -> str:
        lines = [f"{'flag':<32} {'blocks':>8}"]
        lines.append('-' * 42)
        for col in self.flag_df.columns:
            n = self.flag_df[col].sum()
            lines.append(f"{col:<32} {n:>4}/{len(self.flag_df)}")
        return '\n'.join(lines)


# ── formatting helper ─────────────────────────────────────────────────────────

def _fmt_val(val) -> str:
    """Format a DataFrame value back to a CTP2 token string."""
    if isinstance(val, float):
        if pd.isna(val):
            return ''
        if val == int(val):
            return str(int(val))
        return str(val)
    return str(val)


# ── CLI ───────────────────────────────────────────────────────────────────────

def run_cli(args: argparse.Namespace):
    """
    Execute CLI operations on a CTP2 file.

    Precondition: args.filepath exists and is a valid CTP2 block file.
    """
    filepath = Path(args.filepath)
    assert filepath.exists(), f"File not found: {filepath}"

    editor = CTP2Editor(filepath)

    if args.show:
        print(editor.summary())
        print("\nKV COLUMNS")
        print(editor.kv_column_report())
        print("\nFLAG COLUMNS")
        print(editor.flag_column_report())
        return

    query = args.filter or None

    if args.filter_block:
        ids = [x.strip() for x in args.filter_block.split(',')]
        editor.filter_blocks(ids)

    mutated = False

    for formula_str in (args.formula or []):
        assert '=' in formula_str, f"--formula needs COL=EXPR, got: {formula_str!r}"
        col, expr = formula_str.split('=', 1)
        editor.apply_formula(col.strip(), expr.strip(), query=query)
        print(f"  formula : {col.strip()} = {expr.strip()}")
        mutated = True

    for set_str in (args.set or []):
        assert '=' in set_str, f"--set needs COL=VALUE, got: {set_str!r}"
        col, value = set_str.split('=', 1)
        editor.set_column(col.strip(), value.strip(), query=query)
        print(f"  set     : {col.strip()} = {value.strip()}")
        mutated = True

    for flag in (args.enable_flag or []):
        editor.enable_flag(flag, query=query)
        print(f"  +flag   : {flag}")
        mutated = True

    for flag in (args.disable_flag or []):
        editor.disable_flag(flag, query=query)
        print(f"  -flag   : {flag}")
        mutated = True

    if mutated or args.output:
        out = editor.save(args.output)
        print(f"  saved   : {out}")
    else:
        print("No operations specified. Use --show to inspect or --formula / --set / "
              "--enable-flag / --disable-flag to make changes.")


# ── PyQt5 UI ─────────────────────────────────────────────────────────────────

def _run_ui(filepath_str: Optional[str] = None):
    """Native PyQt5 desktop editor (ctpeditv53-style). No web server."""
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QSplitter,
        QVBoxLayout, QHBoxLayout, QGridLayout,
        QLabel, QLineEdit, QPushButton, QComboBox, QTabWidget,
        QTableWidget, QTableWidgetItem, QCheckBox, QScrollArea,
        QTextEdit, QDoubleSpinBox, QSpinBox, QGroupBox,
        QFileDialog, QMessageBox, QHeaderView, QAbstractItemView,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont
    import io as _io

    app = QApplication.instance() or QApplication(sys.argv)

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.editor: Optional[CTP2Editor] = None
            self._kv_edit:  Optional[pd.DataFrame] = None
            self._flg_edit: Optional[pd.DataFrame] = None
            self._sl_edit:  Optional[pd.DataFrame] = None
            self._rec_fields: dict = {}
            self._rec_flags:  dict = {}
            self._rec_sls:    dict = {}
            self._setup_ui()
            if filepath_str:
                self._fp_input.setText(filepath_str)
                self._load_file(filepath_str)

        # ── UI construction ───────────────────────────────────────────────────

        def _setup_ui(self):
            self.setWindowTitle("CTP2 Block File Editor")
            self.resize(1400, 860)

            splitter = QSplitter(Qt.Horizontal)

            # ── left panel ────────────────────────────────────────────────────
            left = QWidget()
            left.setFixedWidth(260)
            lv = QVBoxLayout(left)
            lv.setContentsMargins(8, 8, 8, 8)

            lv.addWidget(QLabel("<b>Dimension</b>"))
            self._dim_combo = QComboBox()
            self._dim_combo.addItem("— pick —")
            for name in QUICK_FILES:
                self._dim_combo.addItem(name)
            self._dim_combo.currentTextChanged.connect(self._on_dim_changed)
            lv.addWidget(self._dim_combo)

            lv.addSpacing(8)
            lv.addWidget(QLabel("<b>File path</b>"))
            self._fp_input = QLineEdit()
            self._fp_input.setPlaceholderText("…gamedata/Units.txt")
            lv.addWidget(self._fp_input)
            load_btn = QPushButton("Load / Reload")
            load_btn.clicked.connect(lambda: self._load_file(self._fp_input.text()))
            lv.addWidget(load_btn)

            lv.addSpacing(8)
            lv.addWidget(QLabel("<b>Block prefix filter</b>"))
            self._pfx_input = QLineEdit()
            self._pfx_input.setPlaceholderText("UNIT_")
            self._pfx_input.textChanged.connect(self._on_filter_changed)
            lv.addWidget(self._pfx_input)

            lv.addSpacing(8)
            self._stats_label = QLabel("")
            self._stats_label.setWordWrap(True)
            lv.addWidget(self._stats_label)
            lv.addStretch()

            # ── tabs ──────────────────────────────────────────────────────────
            self._tabs = QTabWidget()

            # Tab 0: Values (KV)
            self._kv_table = self._make_table()
            self._kv_table.itemChanged.connect(self._on_kv_changed)
            self._tabs.addTab(self._kv_table, "Values (KV)")

            # Tab 1: Record
            self._tabs.addTab(self._make_record_tab(), "Record")

            # Tab 2: Flags
            self._flg_table = self._make_table()
            self._flg_table.itemChanged.connect(self._on_flg_changed)
            self._tabs.addTab(self._flg_table, "Flags")

            # Tab 3: SubLists
            self._sl_table = self._make_table()
            self._sl_table.itemChanged.connect(self._on_sl_changed)
            self._tabs.addTab(self._sl_table, "SubLists")

            # Tab 4: Formulas
            self._tabs.addTab(self._make_formula_tab(), "Formulas")

            # Tab 5: CSV
            self._tabs.addTab(self._make_csv_tab(), "CSV")

            # Tab 6: Save
            self._tabs.addTab(self._make_save_tab(), "Save")

            splitter.addWidget(left)
            splitter.addWidget(self._tabs)
            splitter.setStretchFactor(1, 1)
            self.setCentralWidget(splitter)
            self.statusBar().showMessage("Ready — pick a dimension or load a file.")

        @staticmethod
        def _make_table() -> QTableWidget:
            t = QTableWidget()
            t.setAlternatingRowColors(True)
            t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            t.horizontalHeader().setStretchLastSection(False)
            t.setEditTriggers(QAbstractItemView.DoubleClicked |
                              QAbstractItemView.SelectedClicked)
            return t

        def _make_record_tab(self) -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)
            h = QHBoxLayout()
            h.addWidget(QLabel("Record:"))
            self._rec_combo = QComboBox()
            self._rec_combo.setMinimumWidth(340)
            self._rec_combo.currentTextChanged.connect(self._populate_record)
            h.addWidget(self._rec_combo)
            h.addStretch()
            v.addLayout(h)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            self._rec_form_widget = QWidget()
            self._rec_form_layout = QVBoxLayout(self._rec_form_widget)
            scroll.setWidget(self._rec_form_widget)
            v.addWidget(scroll)
            self._rec_update_btn = QPushButton("Update Record")
            self._rec_update_btn.setEnabled(False)
            self._rec_update_btn.clicked.connect(self._update_record)
            v.addWidget(self._rec_update_btn)
            return w

        def _make_formula_tab(self) -> QScrollArea:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            v = QVBoxLayout(container)

            # Relate two columns
            grp1 = QGroupBox("Relate two columns  (target = source × factor + offset)")
            g = QGridLayout(grp1)
            g.addWidget(QLabel("Target:"), 0, 0)
            self._r_target = QComboBox(); g.addWidget(self._r_target, 0, 1)
            g.addWidget(QLabel("Source:"), 0, 2)
            self._r_source = QComboBox(); g.addWidget(self._r_source, 0, 3)
            g.addWidget(QLabel("Factor:"), 1, 0)
            self._r_factor = QDoubleSpinBox()
            self._r_factor.setValue(1.0); self._r_factor.setSingleStep(0.1)
            self._r_factor.setDecimals(3); self._r_factor.setRange(-1e9, 1e9)
            g.addWidget(self._r_factor, 1, 1)
            g.addWidget(QLabel("Offset:"), 1, 2)
            self._r_offset = QDoubleSpinBox()
            self._r_offset.setValue(0.0); self._r_offset.setRange(-1e9, 1e9)
            g.addWidget(self._r_offset, 1, 3)
            g.addWidget(QLabel("Filter:"), 2, 0)
            self._r_qry = QLineEdit()
            self._r_qry.setPlaceholderText("Category == 'UNIT_CATEGORY_NAVAL'")
            g.addWidget(self._r_qry, 2, 1, 1, 3)
            b = QPushButton("Apply relation")
            b.clicked.connect(self._apply_relation)
            g.addWidget(b, 3, 0, 1, 4)
            v.addWidget(grp1)

            # Scale by percentage
            grp2 = QGroupBox("Scale column by percentage")
            g = QGridLayout(grp2)
            g.addWidget(QLabel("Column:"), 0, 0)
            self._sp_col = QComboBox(); g.addWidget(self._sp_col, 0, 1)
            g.addWidget(QLabel("Scale %:"), 0, 2)
            self._sp_pct = QSpinBox()
            self._sp_pct.setValue(100); self._sp_pct.setRange(1, 10000)
            self._sp_pct.setSingleStep(5); g.addWidget(self._sp_pct, 0, 3)
            g.addWidget(QLabel("Filter:"), 1, 0)
            self._sp_qry = QLineEdit(); g.addWidget(self._sp_qry, 1, 1, 1, 3)
            b = QPushButton("Apply scale")
            b.clicked.connect(self._apply_scale)
            g.addWidget(b, 2, 0, 1, 4)
            v.addWidget(grp2)

            # Free-form expression
            grp3 = QGroupBox("Free-form expression  (col = expr)")
            g = QGridLayout(grp3)
            g.addWidget(QLabel("Target:"), 0, 0)
            self._f_col = QComboBox(); g.addWidget(self._f_col, 0, 1)
            g.addWidget(QLabel("Expression:"), 1, 0)
            self._f_expr = QLineEdit()
            self._f_expr.setPlaceholderText("Attack * 2  or  np.clip(Attack, 5, 200)")
            g.addWidget(self._f_expr, 1, 1)
            g.addWidget(QLabel("Filter:"), 2, 0)
            self._f_qry = QLineEdit(); g.addWidget(self._f_qry, 2, 1)
            b = QPushButton("Apply expression")
            b.clicked.connect(self._apply_expression)
            g.addWidget(b, 3, 0, 1, 2)
            v.addWidget(grp3)

            # Set constant
            grp4 = QGroupBox("Set column to a constant")
            g = QGridLayout(grp4)
            g.addWidget(QLabel("Column:"), 0, 0)
            self._s_col = QComboBox(); g.addWidget(self._s_col, 0, 1)
            g.addWidget(QLabel("Value:"), 0, 2)
            self._s_val = QLineEdit()
            self._s_val.setPlaceholderText("ADVANCE_WARRIOR_CODE")
            g.addWidget(self._s_val, 0, 3)
            g.addWidget(QLabel("Filter:"), 1, 0)
            self._s_qry = QLineEdit()
            self._s_qry.setPlaceholderText("EnableAdvance.isna()")
            g.addWidget(self._s_qry, 1, 1, 1, 3)
            b = QPushButton("Set constant")
            b.clicked.connect(self._apply_set_constant)
            g.addWidget(b, 2, 0, 1, 4)
            v.addWidget(grp4)

            # Flag toggle
            grp5 = QGroupBox("Toggle boolean flag")
            g = QGridLayout(grp5)
            g.addWidget(QLabel("Flag name:"), 0, 0)
            self._g_flag = QLineEdit()
            self._g_flag.setPlaceholderText("LossMoveToDmgNone")
            g.addWidget(self._g_flag, 0, 1)
            g.addWidget(QLabel("Action:"), 0, 2)
            self._g_action = QComboBox()
            self._g_action.addItems(["Enable", "Disable"])
            g.addWidget(self._g_action, 0, 3)
            g.addWidget(QLabel("Filter:"), 1, 0)
            self._g_qry = QLineEdit()
            self._g_qry.setPlaceholderText("Category == 'UNIT_CATEGORY_ATTACK'")
            g.addWidget(self._g_qry, 1, 1, 1, 3)
            b = QPushButton("Apply flag toggle")
            b.clicked.connect(self._apply_flag_toggle)
            g.addWidget(b, 2, 0, 1, 4)
            v.addWidget(grp5)

            v.addStretch()
            scroll.setWidget(container)
            return scroll

        def _make_csv_tab(self) -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)

            grp1 = QGroupBox("Export")
            h = QHBoxLayout(grp1)
            b1 = QPushButton("⬇  Save KV as CSV…")
            b1.clicked.connect(self._export_kv_csv)
            h.addWidget(b1)
            b2 = QPushButton("⬇  Save Flags as CSV…")
            b2.clicked.connect(self._export_flg_csv)
            h.addWidget(b2)
            v.addWidget(grp1)

            grp2 = QGroupBox("Import KV from CSV")
            gv = QVBoxLayout(grp2)
            hi = QHBoxLayout()
            self._csv_path = QLineEdit()
            self._csv_path.setPlaceholderText("Path to CSV file…")
            hi.addWidget(self._csv_path)
            bb = QPushButton("Browse…")
            bb.clicked.connect(self._browse_csv)
            hi.addWidget(bb)
            gv.addLayout(hi)
            bi = QPushButton("Import & Apply")
            bi.clicked.connect(self._import_csv)
            gv.addWidget(bi)
            self._csv_preview = QTextEdit()
            self._csv_preview.setReadOnly(True)
            self._csv_preview.setMaximumHeight(180)
            self._csv_preview.setFont(QFont("Courier New", 9))
            gv.addWidget(self._csv_preview)
            v.addWidget(grp2)
            v.addStretch()
            return w

        def _make_save_tab(self) -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)

            grp1 = QGroupBox("Save edited blocks to file")
            gv = QVBoxLayout(grp1)
            h = QHBoxLayout()
            self._save_path = QLineEdit()
            h.addWidget(self._save_path)
            bb = QPushButton("Browse…")
            bb.clicked.connect(lambda: (
                self._save_path.setText(
                    QFileDialog.getSaveFileName(self, "Save as", "", "Text (*.txt)")[0]
                    or self._save_path.text()
                )
            ))
            h.addWidget(bb)
            gv.addLayout(h)
            btn_save = QPushButton("Save")
            btn_save.setFixedHeight(38)
            btn_save.clicked.connect(self._save_file)
            gv.addWidget(btn_save)
            self._save_info = QLabel("")
            gv.addWidget(self._save_info)
            v.addWidget(grp1)

            grp2 = QGroupBox("Column / flag reference")
            gv2 = QVBoxLayout(grp2)
            self._col_ref = QTextEdit()
            self._col_ref.setReadOnly(True)
            self._col_ref.setFont(QFont("Courier New", 9))
            gv2.addWidget(self._col_ref)
            v.addWidget(grp2)
            return w

        # ── loading ───────────────────────────────────────────────────────────

        def _on_dim_changed(self, name: str):
            if name == "— pick —":
                return
            path = str(_SCENARIO_ROOT / QUICK_FILES[name])
            self._fp_input.setText(path)
            self._load_file(path)

        def _load_file(self, path: str):
            if not path:
                return
            p = Path(path)
            if not p.exists():
                self.statusBar().showMessage(f"Not found: {p}")
                return
            try:
                self.editor   = CTP2Editor(p)
                self._kv_edit  = self.editor.kv_df.copy()
                self._flg_edit = self.editor.flag_df.copy()
                self._sl_edit  = self.editor.sl_df.copy()
                self._save_path.setText(str(p))
                self._update_stats()
                self._populate_all_tables()
                self._populate_formula_combos()
                self._populate_rec_combo()
                self._update_col_ref()
                self.statusBar().showMessage(
                    f"Loaded {len(self.editor.blocks)} blocks from {p.name}"
                )
            except Exception as exc:
                QMessageBox.critical(self, "Load error", str(exc))

        def _update_stats(self):
            if not self.editor:
                return
            self._stats_label.setText(
                f"<b>{len(self.editor.blocks)}</b> blocks<br>"
                f"<b>{len(self._kv_edit.columns)}</b> KV cols<br>"
                f"<b>{len(self._flg_edit.columns)}</b> flags<br>"
                f"<b>{len(self._sl_edit.columns)}</b> SL cols"
            )

        def _filtered_rows(self) -> list:
            if self._kv_edit is None:
                return []
            pfx = self._pfx_input.text().upper()
            if not pfx:
                return list(self._kv_edit.index)
            return [i for i in self._kv_edit.index if pfx in i.upper()]

        def _on_filter_changed(self, _: str):
            self._populate_all_tables()

        # ── table population ──────────────────────────────────────────────────

        def _populate_all_tables(self):
            self._populate_kv_table()
            self._populate_flg_table()
            self._populate_sl_table()

        def _populate_kv_table(self):
            df   = self._kv_edit
            rows = self._filtered_rows()
            if df is None:
                return
            self._kv_table.blockSignals(True)
            self._kv_table.setRowCount(len(rows))
            self._kv_table.setColumnCount(len(df.columns))
            self._kv_table.setHorizontalHeaderLabels(list(df.columns))
            self._kv_table.setVerticalHeaderLabels(rows)
            for r, rid in enumerate(rows):
                for c, col in enumerate(df.columns):
                    val = df.loc[rid, col]
                    text = "" if (isinstance(val, float) and pd.isna(val)) else _fmt_val(val)
                    self._kv_table.setItem(r, c, QTableWidgetItem(text))
            self._kv_table.blockSignals(False)

        def _populate_flg_table(self):
            df   = self._flg_edit
            rows = self._filtered_rows()
            if df is None or df.empty:
                self._flg_table.setRowCount(0)
                self._flg_table.setColumnCount(0)
                return
            self._flg_table.blockSignals(True)
            self._flg_table.setRowCount(len(rows))
            self._flg_table.setColumnCount(len(df.columns))
            self._flg_table.setHorizontalHeaderLabels(list(df.columns))
            self._flg_table.setVerticalHeaderLabels(rows)
            for r, rid in enumerate(rows):
                for c, col in enumerate(df.columns):
                    val = bool(df.loc[rid, col]) if rid in df.index else False
                    item = QTableWidgetItem()
                    item.setCheckState(Qt.Checked if val else Qt.Unchecked)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    self._flg_table.setItem(r, c, item)
            self._flg_table.blockSignals(False)

        def _populate_sl_table(self):
            df   = self._sl_edit
            rows = self._filtered_rows()
            if df is None or df.empty:
                self._sl_table.setRowCount(0)
                self._sl_table.setColumnCount(0)
                return
            self._sl_table.blockSignals(True)
            self._sl_table.setRowCount(len(rows))
            self._sl_table.setColumnCount(len(df.columns))
            self._sl_table.setHorizontalHeaderLabels(list(df.columns))
            self._sl_table.setVerticalHeaderLabels(rows)
            for r, rid in enumerate(rows):
                for c, col in enumerate(df.columns):
                    val = df.loc[rid, col] if rid in df.index else ""
                    text = "" if (not isinstance(val, str) and pd.isna(val)) else str(val)
                    self._sl_table.setItem(r, c, QTableWidgetItem(text))
            self._sl_table.blockSignals(False)

        # ── table change handlers ─────────────────────────────────────────────

        def _on_kv_changed(self, item: QTableWidgetItem):
            if self._kv_edit is None:
                return
            rows = self._filtered_rows()
            r, c = item.row(), item.column()
            if r >= len(rows):
                return
            rid = rows[r]
            col = self._kv_edit.columns[c]
            val = item.text()
            num = pd.to_numeric(val, errors='coerce')
            self._kv_edit.loc[rid, col] = num if pd.notna(num) else val

        def _on_flg_changed(self, item: QTableWidgetItem):
            if self._flg_edit is None or self._flg_edit.empty:
                return
            rows = self._filtered_rows()
            r, c = item.row(), item.column()
            if r >= len(rows):
                return
            rid = rows[r]
            col = self._flg_edit.columns[c]
            self._flg_edit.loc[rid, col] = (item.checkState() == Qt.Checked)

        def _on_sl_changed(self, item: QTableWidgetItem):
            if self._sl_edit is None or self._sl_edit.empty:
                return
            rows = self._filtered_rows()
            r, c = item.row(), item.column()
            if r >= len(rows):
                return
            rid = rows[r]
            col = self._sl_edit.columns[c]
            self._sl_edit.loc[rid, col] = item.text()

        # ── record tab ────────────────────────────────────────────────────────

        def _populate_rec_combo(self):
            self._rec_combo.blockSignals(True)
            self._rec_combo.clear()
            if self._kv_edit is not None:
                for bid in sorted(self._kv_edit.index):
                    self._rec_combo.addItem(bid)
            self._rec_combo.blockSignals(False)
            if self._rec_combo.count():
                self._populate_record(self._rec_combo.currentText())

        def _populate_record(self, bid: str):
            if not bid or self._kv_edit is None:
                return
            self._rec_update_btn.setEnabled(True)
            # Clear old widgets
            while self._rec_form_layout.count():
                child = self._rec_form_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self._rec_fields = {}
            self._rec_flags  = {}
            self._rec_sls    = {}

            # KV fields in 2-column grid
            kv_row    = self._kv_edit.loc[bid]
            kv_fields = [(k, v) for k, v in kv_row.items()
                         if not (isinstance(v, float) and pd.isna(v))]
            if kv_fields:
                self._rec_form_layout.addWidget(
                    QLabel(f"<b>Key-Value fields</b> ({len(kv_fields)})")
                )
                grid = QWidget()
                gl = QGridLayout(grid)
                gl.setContentsMargins(0, 0, 0, 0)
                for i, (k, v) in enumerate(kv_fields):
                    row_i, col_i = divmod(i, 2)
                    gl.addWidget(QLabel(k + ":"), row_i, col_i * 2)
                    w = QLineEdit(str(v) if not isinstance(v, float)
                                  else str(int(v)) if v == int(v) else str(v))
                    gl.addWidget(w, row_i, col_i * 2 + 1)
                    self._rec_fields[k] = w
                self._rec_form_layout.addWidget(grid)

            # Flags in 4-column grid
            if not self._flg_edit.empty and bid in self._flg_edit.index:
                flg_row = self._flg_edit.loc[bid]
                active  = list(flg_row.items())
                if active:
                    self._rec_form_layout.addWidget(QLabel("<b>Flags</b>"))
                    fg = QWidget()
                    fgl = QGridLayout(fg)
                    fgl.setContentsMargins(0, 0, 0, 0)
                    for i, (fname, fval) in enumerate(active):
                        row_i, col_i = divmod(i, 4)
                        cb = QCheckBox(fname)
                        cb.setChecked(bool(fval))
                        fgl.addWidget(cb, row_i, col_i)
                        self._rec_flags[fname] = cb
                    self._rec_form_layout.addWidget(fg)

            # SubList fields
            if not self._sl_edit.empty and bid in self._sl_edit.index:
                sl_row    = self._sl_edit.loc[bid]
                sl_fields = [(k, v) for k, v in sl_row.items()
                             if isinstance(v, str) and v]
                if sl_fields:
                    self._rec_form_layout.addWidget(
                        QLabel("<b>SubList fields</b> (pipe-separated)")
                    )
                    for k, v in sl_fields:
                        row_w = QWidget()
                        rh = QHBoxLayout(row_w)
                        rh.setContentsMargins(0, 0, 0, 0)
                        rh.addWidget(QLabel(k + ":"))
                        w = QLineEdit(v)
                        rh.addWidget(w)
                        self._rec_sls[k] = w
                        self._rec_form_layout.addWidget(row_w)

            self._rec_form_layout.addStretch()

        def _update_record(self):
            bid = self._rec_combo.currentText()
            if not bid:
                return
            for k, w in self._rec_fields.items():
                val = w.text()
                num = pd.to_numeric(val, errors='coerce')
                self._kv_edit.loc[bid, k] = num if pd.notna(num) else val
            for fname, cb in self._rec_flags.items():
                self._flg_edit.loc[bid, fname] = cb.isChecked()
            for k, w in self._rec_sls.items():
                self._sl_edit.loc[bid, k] = w.text()
            self.statusBar().showMessage(
                f"Record {bid} updated — go to Save tab to write to disk."
            )
            self._populate_kv_table()

        # ── formula combo population ──────────────────────────────────────────

        def _populate_formula_combos(self):
            if self._kv_edit is None:
                return
            cols     = list(self._kv_edit.columns)
            num_cols = [c for c in cols
                        if pd.api.types.is_numeric_dtype(self._kv_edit[c])]
            for cb in (self._r_target, self._f_col, self._s_col):
                cb.clear(); cb.addItems(cols)
            for cb in (self._r_source, self._sp_col):
                cb.clear(); cb.addItems(num_cols or cols)

        # ── formula actions ───────────────────────────────────────────────────

        def _sync_to_editor(self):
            self.editor.kv_df   = self._kv_edit.copy()
            self.editor.flag_df = self._flg_edit.copy()
            self.editor.sl_df   = self._sl_edit.copy()

        def _apply_relation(self):
            try:
                target = self._r_target.currentText()
                source = self._r_source.currentText()
                factor = self._r_factor.value()
                offset = self._r_offset.value()
                qry    = self._r_qry.text() or None
                expr   = f"{source} * {factor}"
                if offset != 0.0:
                    expr += f" + {offset}"
                self._sync_to_editor()
                self.editor.apply_formula(target, expr, query=qry)
                self._kv_edit = self.editor.kv_df.copy()
                self._populate_kv_table()
                self.statusBar().showMessage(f"Applied: {target} = {expr}")
            except Exception as exc:
                QMessageBox.warning(self, "Formula error", str(exc))

        def _apply_scale(self):
            try:
                col    = self._sp_col.currentText()
                factor = self._sp_pct.value() / 100.0
                qry    = self._sp_qry.text() or None
                self._sync_to_editor()
                self.editor.apply_formula(col, f"{col} * {factor}", query=qry)
                self._kv_edit = self.editor.kv_df.copy()
                self._populate_kv_table()
                self.statusBar().showMessage(
                    f"Scaled {col} by {self._sp_pct.value()}%"
                )
            except Exception as exc:
                QMessageBox.warning(self, "Scale error", str(exc))

        def _apply_expression(self):
            try:
                col  = self._f_col.currentText()
                expr = self._f_expr.text()
                qry  = self._f_qry.text() or None
                self._sync_to_editor()
                self.editor.apply_formula(col, expr, query=qry)
                self._kv_edit = self.editor.kv_df.copy()
                self._populate_kv_table()
                self.statusBar().showMessage(f"Applied: {col} = {expr}")
            except Exception as exc:
                QMessageBox.warning(self, "Expression error", str(exc))

        def _apply_set_constant(self):
            try:
                col = self._s_col.currentText()
                val = self._s_val.text()
                qry = self._s_qry.text() or None
                self._sync_to_editor()
                self.editor.set_column(col, val, query=qry)
                self._kv_edit = self.editor.kv_df.copy()
                self._populate_kv_table()
                self.statusBar().showMessage(f"Set {col} = {val}")
            except Exception as exc:
                QMessageBox.warning(self, "Set error", str(exc))

        def _apply_flag_toggle(self):
            try:
                flag   = self._g_flag.text()
                action = self._g_action.currentText()
                qry    = self._g_qry.text() or None
                self._sync_to_editor()
                if action == "Enable":
                    self.editor.enable_flag(flag, query=qry)
                else:
                    self.editor.disable_flag(flag, query=qry)
                self._flg_edit = self.editor.flag_df.copy()
                self._populate_flg_table()
                self.statusBar().showMessage(f"{action}d flag: {flag}")
            except Exception as exc:
                QMessageBox.warning(self, "Flag error", str(exc))

        # ── CSV ───────────────────────────────────────────────────────────────

        def _export_kv_csv(self):
            if self._kv_edit is None:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Save KV CSV",
                str(self.editor.filepath.with_suffix("")) + "_kv.csv",
                "CSV (*.csv)"
            )
            if path:
                self._kv_edit.to_csv(path)
                self.statusBar().showMessage(f"KV saved → {path}")

        def _export_flg_csv(self):
            if self._flg_edit is None or self._flg_edit.empty:
                return
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Flags CSV",
                str(self.editor.filepath.with_suffix("")) + "_flags.csv",
                "CSV (*.csv)"
            )
            if path:
                self._flg_edit.to_csv(path)
                self.statusBar().showMessage(f"Flags saved → {path}")

        def _browse_csv(self):
            path, _ = QFileDialog.getOpenFileName(
                self, "Open CSV", "", "CSV (*.csv)"
            )
            if path:
                self._csv_path.setText(path)

        def _import_csv(self):
            path = self._csv_path.text()
            if not path or not Path(path).exists():
                QMessageBox.warning(self, "Import", "Select a valid CSV file first.")
                return
            try:
                imported = pd.read_csv(path, index_col=0)
                self._csv_preview.setPlainText(
                    f"{len(imported)} rows, {len(imported.columns)} columns\n\n"
                    + imported.head(10).to_string()
                )
                if self._kv_edit is None:
                    return
                applied = 0
                for idx in imported.index:
                    if idx in self._kv_edit.index:
                        for col in imported.columns:
                            self._kv_edit.loc[idx, col] = imported.loc[idx, col]
                        applied += 1
                self._populate_kv_table()
                self.statusBar().showMessage(
                    f"Applied {applied} rows from CSV — go to Save tab to write to disk."
                )
            except Exception as exc:
                QMessageBox.critical(self, "Import error", str(exc))

        # ── save ──────────────────────────────────────────────────────────────

        def _update_col_ref(self):
            if self.editor is None:
                return
            self._col_ref.setPlainText(
                self.editor.kv_column_report() + "\n\n"
                + self.editor.flag_column_report()
            )

        def _save_file(self):
            if self.editor is None:
                QMessageBox.warning(self, "Save", "No file loaded.")
                return
            self._sync_to_editor()
            out = self._save_path.text() or None
            try:
                saved = self.editor.save(out)
                self._save_info.setText(
                    f"✓ Saved {len(self.editor.blocks)} blocks → {saved}"
                )
                self.statusBar().showMessage(f"Saved → {saved}")
            except Exception as exc:
                QMessageBox.critical(self, "Save error", str(exc))

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="CTP2 block-file editor — interactive UI or scriptable CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('filepath', nargs='?', help="CTP2 block file (e.g. Units.txt)")
    p.add_argument('--cli',          action='store_true',
                   help="CLI mode (no UI)")
    p.add_argument('--show',         action='store_true',
                   help="Print column/flag summary; no save")
    p.add_argument('--formula',      action='append', metavar='COL=EXPR',
                   help="Apply formula to KV column (repeatable)")
    p.add_argument('--set',          action='append', metavar='COL=VALUE',
                   help="Set KV column to constant (repeatable)")
    p.add_argument('--enable-flag',  action='append', metavar='FLAG',
                   dest='enable_flag',
                   help="Enable boolean flag (repeatable)")
    p.add_argument('--disable-flag', action='append', metavar='FLAG',
                   dest='disable_flag',
                   help="Disable boolean flag (repeatable)")
    p.add_argument('--filter',       metavar='EXPR',
                   help="Pandas query restricting which blocks are modified")
    p.add_argument('--filter-block', metavar='IDs', dest='filter_block',
                   help="Comma-separated block IDs to restrict operations to")
    p.add_argument('--output',       metavar='PATH',
                   help="Output file path (default: overwrite input)")
    return p


if __name__ == '__main__':
    _parser = _build_arg_parser()
    _args   = _parser.parse_args()
    if _args.cli or _args.show:
        if not _args.filepath:
            _parser.error("filepath is required in CLI mode")
        run_cli(_args)
    else:
        _run_ui(_args.filepath)
