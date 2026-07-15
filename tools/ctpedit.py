"""
ctpedit.py — CTP2 mod dimension patcher

Ports dimensions from a Civ2-compatible mod (via momjr_csv/) to CTP2 scenario
files.  Each dimension knows its source CSVs, target data files, and cascade
effects.  Think of it as an SQL-with-cascade layer: touching 'units' cascades
to Units.txt, uniticon.txt, junk_str.txt, GL strings — all pre-wired.

Commands
--------
  python ctpedit.py patch [units|advances|improvements|wonders|all]
  python ctpedit.py status
  python ctpedit.py show <dimension>

Civ2 → CTP2 dimension mapping
------------------------------
  Civ2 dimension          CTP2 dimension
  ──────────────────────  ─────────────────────────────────────────
  Advances                Advances
  Units                   Units
  City Improvements       City Improvements / Buildings
  Wonders (sub-type)      Wonders
  Terrain                 Terrain
  Caravan Commodities     Goods
                          Tile Improvements
  Governments             Governments
  Orders / command text   Unit Orders
  Civilopedia / labels    Concepts
  Scenario art / sounds   Scenario Art

Cascade map (what gets touched per dimension)
---------------------------------------------
  advances:     Advance.txt  gl_str.txt  Great_Library.txt
  units:        Units.txt  uniticon.txt  junk_str.txt  gl_str.txt
                  Great_Library.txt  (+ unit_mask.csv enforces removals)
  improvements: Improve.txt  uniticon.txt  gl_str.txt  Great_Library.txt
                  (+ building_uniticon.csv provides proxy TGAs for CTP2-only
                     buildings that have no Civ2 art source)
  wonders:      Wonder.txt  uniticon.txt  wondericon.txt  wondermovie.txt
                  Great_Library.txt  WAW_Great_Library.txt
                  (+ migrated wonders removed from Improve.txt)

All cascade logic lives in ctp2_generator.py and ctp2_parser.py — ctpedit.py
is a thin orchestration layer that validates, dispatches, and reports. Every
generator-backed scenario update also refreshes
`Scenarios\\mom\\mom_dimension_inventory.xlsx` from `dimension_inventory.md`
plus the MoM-owned `momjr_csv\\*.csv` control-plane surfaces.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

TOOLS_DIR = Path(__file__).resolve().parent
MOMJR_CSV = TOOLS_DIR / "momjr_csv"
SCENARIO   = Path(
    __import__('os').environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000",
    )
)

# ── Dimension manifest ─────────────────────────────────────────────────────────
# Each entry documents: source CSVs, target gamedata files, and cascade notes.
# This is the "pre-connected lessons learned" — the schema translation layer
# that knows what a Civ2→CTP2 dimension port touches.

DIMENSIONS: Dict[str, dict] = {
    "advances": {
        "label": "Advances",
        "sources": [
            "advances.csv",       # Civ2 advance rows → ADVANCE_* blocks
        ],
        "targets": [
            "default/gamedata/Advance.txt",
            "english/gamedata/gl_str.txt",
            "english/gamedata/Great_Library.txt",
        ],
        "cascade": [
            "EnableAdvance refs in Units.txt auto-resolved from units.csv prereq codes",
            "Base CTP2 advance GL prose restored from stock Great_Library if absent",
            "Missing display names auto-generated from ADVANCE_* identifier",
            "Stub advances created for any base-unit EnableAdvance refs not in advances.csv",
        ],
    },
    "units": {
        "label": "Units",
        "sources": [
            "units.csv",          # Civ2 unit rows → UNIT_* blocks
            "unit_mask.csv",      # Stock CTP2 / test units to remove (nested-brace-safe)
        ],
        "targets": [
            "default/gamedata/Units.txt",
            "default/gamedata/Units_historic.txt",   # Backup — engine loads this in some paths
            "default/gamedata/Units_release.txt",    # Backup — engine loads this in some paths
            "default/gamedata/uniticon.txt",
            "english/gamedata/junk_str.txt",
            "english/gamedata/gl_str.txt",
            "english/gamedata/Great_Library.txt",
        ],
        "cascade": [
            "Sprite assigned automatically by domain + attack stats (civ2_sprite_extractor)",
            "All base CTP2 units NOT in units.csv auto-hidden (NoIndex + GLHidden flags)",
            "Units in unit_mask.csv fully removed via UnitsFile.remove_unit() — handles nested sub-blocks",
            "unit_mask.csv cascades to ALL three unit files (Units.txt, Units_historic.txt, Units_release.txt) — engine can load any of them; missing a file causes 'X not found in Unit database' at startup",
            "ICON_UNIT_* blocks auto-generated in uniticon.txt for every unit",
            "Junk description strings written to junk_str.txt (GL lookup fallback)",
            "GL display name + Great Library section auto-created per unit",
            "Lesson: never use regex for Units.txt block removal — nested sub-blocks require the parser",
        ],
    },
    "improvements": {
        "label": "City Improvements (Buildings)",
        "sources": [
            "improvements.csv",       # Civ2 building rows → IMPROVE_* blocks
            "building_uniticon.csv",  # Proxy TGAs for CTP2-only buildings (no Civ2 art)
        ],
        "targets": [
            "default/gamedata/Improve.txt",
            "default/gamedata/uniticon.txt",
            "english/gamedata/gl_str.txt",
            "english/gamedata/Great_Library.txt",
        ],
        "cascade": [
            "building_uniticon.csv is the canonical proxy path — generator owns uniticon.txt",
            "CTP2-only buildings (no Civ2 art source) get thematic proxy TGAs via building_uniticon.csv",
            "GL surfaces (gameplay, historical, prereq, statistics) auto-generated per improvement",
            "Lesson: dimension_inventory.md is 1st-class source of truth for what belongs in the mod",
        ],
    },
    "wonders": {
        "label": "Wonders of the World",
        "sources": [
            "wonders.csv",        # Civ2 wonder rows → WONDER_* blocks
            "wondericon.csv",
            "wondermovie.csv",
        ],
        "targets": [
            "default/gamedata/Wonder.txt",
            "default/gamedata/uniticon.txt",
            "default/gamedata/wondericon.txt",
            "default/gamedata/wondermovie.txt",
            "english/gamedata/Great_Library.txt",
            "english/gamedata/WAW_Great_Library.txt",
        ],
        "cascade": [
            "Wonders that were migrated from Improve.txt are removed from improvements (cascade delete)",
            "Wonder icon art extracted from Civ2 sprite atlas and written as TGA files",
            "GL surfaces auto-generated: gameplay, historical, prereq, statistics sections",
            "Stale DATABASE_WONDERS links pruned from Great_Library on each run",
            "Wonder build-list files reset to empty on each run (re-populated at runtime)",
        ],
    },
    "terrain": {
        "label": "Terrain",
        "sources": [
            "terrain.csv",           # Civ2 terrain rows → TERRAIN_* blocks
        ],
        "targets": [
            "default/gamedata/Terrain.txt",
            "default/gamedata/terrainicon.txt",
            "english/gamedata/gl_str.txt",
        ],
        "cascade": [
            "Terrain icon TGAs in pictures/ should match TERRAIN_* IDs",
            "CTP2 has 26 terrain types vs Civ2's 33 — some terrain types are consolidated",
            "Good (resource) nodes in terrain.csv map to goods.csv entries",
        ],
    },
    "tile_improvements": {
        "label": "Tile Improvements",
        "sources": [
            "tile_improvements.csv",  # CTP2 tile improvements (81 entries)
        ],
        "targets": [
            "default/gamedata/tileimp.txt",
            "default/gamedata/tileimpicon.txt",
        ],
        "cascade": [
            "Civ2 has 8 tile improvement types (Road/Railroad/Mine/Farmland/Fortress/Airbase/Pollution/Immigration)",
            "CTP2 greatly expands to 81 types; base CTP2 AE entries are used for non-Civ2 types",
            "Tile improvement icons in ICON_TILEIMP_*.tga (36 TGAs in pictures/)",
            "In CTP2, tile building is done via unit CanBuild capability, NOT named orders (unlike Civ2)",
            "Genre-agnostic policy: TERRAFORM_* variants and TRADING_POST are visible (fantasy compatible)",
            "Out-of-genre items (HYDROPONIC_FARMS, OUTLET_MALL, PROCESSING_TOWER, UNDERSEA_TUNNEL) get GLHidden",
            "Surrogate items (13 stock CTP2 tileimps with no MoM CSV equivalent) get GLHidden for engine compat",
            "CRITICAL: hiding requires copy-from-base + GLHidden flag in scenario file — deleting a block is a no-op because CTP2 falls back to base ctp2_data (which has no GLHidden)",
            "TILEIMP_MAGLEV is visible but remapped to Enchanted Road advance in MoM",
        ],
    },
    "governments": {
        "label": "Governments",
        "sources": [
            "governments.csv",       # Civ2 govt rows → GOVERNMENT_* blocks
        ],
        "targets": [
            "default/gamedata/govern.txt",
            "default/gamedata/governicon.txt",
            "english/gamedata/gl_str.txt",
        ],
        "cascade": [
            "Civ2 has 7 governments; CTP2 MoM uses 5 (pruned for MoM theme)",
            "Government icon TGAs in ICON_GOVERN_*.tga (5 TGAs in pictures/)",
            "Each government has support slots (free units) and science/production coefficients",
            "MoM-specific government names (FUNDAMENTALISM, ECOTOPIA, etc.) are NOT in base CTP2 gl_str.txt",
            "Generator injects missing GOVERNMENT_* display strings via humanize_ident() after the prune pass",
        ],
    },
    "orders": {
        "label": "Unit Orders",
        "sources": [
            # orders.csv not yet created — generator pulls from base CTP2 ctp2_data at runtime
        ],
        "targets": [
            "default/gamedata/Orders.txt",
            "english/gamedata/gl_str.txt",
        ],
        "cascade": [
            "Civ2 'Orders / command text' → CTP2 'Unit Orders' (47 entries in base CTP2)",
            "CTP2 orders NEVER have GL article sections (no PREREQ/STATISTICS/GAMEPLAY/HISTORICAL)",
            "Visibility gate: has_display_name alone (NOT has_full_gl which is always False for orders)",
            "34 orders visible (fantasy-compatible); 13 out-of-genre GLHidden",
            "Out-of-genre: corporate (Advertise, Franchise, Injoin, Sue, Sue_Franchise), sci-fi/nuclear (Bio_Infect, Nano_Infect, Plant_Nuke, Refuel, Space_Launch, Target, Clear_Target, Create_Park)",
            "Base ctp2_data gl_str.txt has ORDER_*/UNIT_ORDER_* display strings — generator copies them",
            "3 orders missing from base need manual strings: AIRLIFT, ENSLAVE_SETTLER, INVESTIGATE_READINESS",
            "Civ2 tile-build orders (Build Road/Mine/Irrigation) map to CTP2 unit CanBuild capability, not named orders",
        ],
    },
    "goods": {
        "label": "Goods (Trade Commodities)",
        "sources": [
            "goods.csv",  # not yet created — currently copied raw from base CTP2
        ],
        "targets": [
            "default/gamedata/goods.txt",
            "english/gamedata/gl_str.txt",
        ],
        "cascade": [
            "Civ2 'Caravan commodities / trade lane data' → CTP2 'Goods'",
            "CTP2 goods are resources traded between cities; Civ2 had commodity caravans",
            "Good (resource) nodes in terrain.csv map to goods.csv entries",
            "Generator currently copies goods.txt raw from base CTP2 — not yet CSV-driven",
        ],
    },
    "concepts": {
        "label": "Concepts (Civilopedia)",
        "sources": [
            # No concepts.csv yet — concepts carried over from base CTP2
        ],
        "targets": [
            "default/gamedata/concept.txt",
            "english/gamedata/gl_str.txt",
            "english/gamedata/Great_Library.txt",
        ],
        "cascade": [
            "Civ2 'Civilopedia / labels / game text' → CTP2 'Concepts'",
            "3 out-of-genre concepts hidden: CONCEPT_FUEL, CONCEPT_GENETIC_AGE, CONCEPT_MODERN_AGE",
            "Stale DATABASE_CONCEPTS links pruned from Great_Library and WAW_Great_Library on each run",
            "Generator prunes concept blocks and gl_str entries to match live GL article references",
        ],
    },
    "slic": {
        "label": "SLIC / Events",
        "sources": [
            # No CSV source — SLIC scripts are authored directly
        ],
        "targets": [
            # SLIC .slc files under Scenarios/mom/scen0000/default/
        ],
        "cascade": [
            "Civ2 'Events' → CTP2 'SLIC' scripting layer",
            "SLIC scripts fire on game events (city founding, combat, diplomacy, etc.)",
            "Any BuildingDB(IMPROVE_X) reference to a removed AE building causes a silent crash at load",
            "SLIC must be scanned for removed AE building refs before every commit (Script D in HARNESS.md)",
            "MoM encounter triggers, faction founding events, and magic mechanics live here",
            "Status: not yet started",
        ],
    },
    "scenario_art": {
        "label": "Scenario Art",
        "sources": [
            # Art extracted from Civ2 sprite atlas via civ2_sprite_extractor.py
        ],
        "targets": [
            # Unit TGAs in Scenarios/mom/scen0000/default/graphics/pictures/
            # Ambient sounds and music under Scenarios/mom/scen0000/
        ],
        "cascade": [
            "Civ2 'Scenario art sheets and sounds' → CTP2 unit sprite TGAs + GL background TGAs",
            "GL background TGAs (upfg500/501/502, uptg04e) must have TGA desc byte 0x01 (not 0x20)",
            "Unit icon TGAs (ICON_UNIT_*.tga) extracted from Civ2 sprite atlas by civ2_sprite_extractor.py",
            "Loose TGAs in Scenarios/mom override base — do NOT shadow AE UI files (upbt01*, upsg*, ug026/027)",
            "Status: partial — advance and improvement icons done; unit sprites partially done",
        ],
    },
    "sprites": {
        "label": "Unit Map Sprites (SPR)",
        "sources": [],   # TGAs discovered from pictures/ at runtime — no CSV needed
        "targets": [
            "default/gamedata/newsprite.txt",            # auto-registered sprite numbers
            "ctp2_data/default/graphics/sprites/GU*.SPR",  # compiled output
        ],
        "cascade": [
            "Discovers all SPRITE_*.tga in Scenarios/mom/.../graphics/pictures/",
            "Skips sprites already covered by base-game newsprite.txt (numbers 1-90) unless MoM overrides",
            "Auto-assigns next available number (91+) for TGAs not yet in MoM newsprite.txt",
            "Appends new SPRITE_X ### entries to MoM newsprite.txt",
            "Converts each TGA to 5 facing 96x72 RGBA TIFs via ImageMagick (black keyed to alpha)",
            "Writes minimal single-frame GU###.TXT script and runs makespr.py -u ###",
            "Copies GU###.SPR to ctp2_data/default/graphics/sprites/",
            "Idempotent: skips sprites where GU###.SPR already exists (use --force to rebuild all)",
        ],
    },
    "leaders_civs": {
        "label": "Leaders / Civilizations",
        "sources": [
            # No direct CSV yet — mapping Civ2 @LEADERS to CTP2 civilisation.txt
        ],
        "targets": [
            "default/gamedata/civilisation.txt",
            "english/gamedata/civ_str.txt",
        ],
        "cascade": [
            "Civ2 has 23 leaders in MoMJR (one row per civilization in @LEADERS)",
            "CTP2 stores full civilization records: leader names, personality, city style, emissary photos",
            "5 MoM faction leaders (Ariel/Freya/Jafar/Rjak/Tauron) are the priority",
            "Remaining Civ2 civs can use AE baseline civilisation.txt entries",
            "CTP2 MoM has 70 civilization entries total (including Barbarian)",
            "Female-primary leaders need Female 1 flag in civilisation.txt",
        ],
    },
}

ALL_DIMENSIONS = list(DIMENSIONS.keys())


# ── helpers ────────────────────────────────────────────────────────────────────

def _csv_row_count(csv_name: str) -> Optional[int]:
    path = MOMJR_CSV / csv_name
    if not path.exists():
        return None
    with open(str(path), newline='', encoding='utf-8') as f:
        return sum(1 for r in csv.DictReader(f))


def _target_block_count(rel: str) -> Optional[int]:
    path = SCENARIO / rel
    if not path.exists():
        return None
    text = path.read_text(encoding='latin-1', errors='replace')
    import re
    # gl_str and junk_str use key "value" lines, not { } blocks
    if rel.endswith("_str.txt"):
        return len(re.findall(r'^\w+\s+"', text, re.MULTILINE))
    # Library files use [SECTION] format
    if rel.endswith("Great_Library.txt"):
        return len(re.findall(r'^\[', text, re.MULTILINE))
    # civilisation.txt uses NAME\t#n on one line, { on the next
    if rel.endswith("civilisation.txt"):
        return len(re.findall(r'^\w+\s+#\d+', text, re.MULTILINE))
    return len(re.findall(r'^\w+\s*\{', text, re.MULTILINE))


def _run_generator() -> int:
    """Invoke ctp2_generator.py and return its exit code."""
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "ctp2_generator.py")],
        cwd=str(TOOLS_DIR),
    )
    return result.returncode


def _run_fix_gl_links() -> int:
    """Neutralize dangling Great Library cross-reference links across all 10
    dimensions. The base AE Great Library references base/WAW entities the MoM
    scenario doesn't include; CTP2 hard-errors ('X not found in <DB> database') on
    the first such link at load. Must run AFTER the generator (which re-adds base GL
    prose) and BEFORE the audit."""
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "fix_gl_links.py")],
        cwd=str(TOOLS_DIR),
    )
    return result.returncode


def _run_validate_all_surfaces() -> int:
    """Assert every CTP2 reference surface (gating fields, GL links/sections, AI
    build lists, EndGameObjects, base-fallback files, SLIC symbols) resolves against
    the live DBs. Returns non-zero if any dangling reference remains — the build is
    not launch-clean. Runs AFTER fix_gl_links, BEFORE the audit."""
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "validate_all_surfaces.py")],
        cwd=str(TOOLS_DIR),
    )
    return result.returncode


def _run_build_sprites(force: bool = False) -> int:
    """Invoke build_sprites.py and return its exit code."""
    cmd = [sys.executable, str(TOOLS_DIR / "build_sprites.py")]
    if force:
        cmd.append("--force")
    result = subprocess.run(cmd, cwd=str(TOOLS_DIR))
    return result.returncode


def _run_audit() -> int:
    """Invoke mom_audit.py and return its exit code."""
    result = subprocess.run(
        [sys.executable, str(TOOLS_DIR / "mom_audit.py")],
        cwd=str(TOOLS_DIR),
    )
    return result.returncode


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_status(_args: argparse.Namespace):
    """Show CSV source state and target file block counts for all dimensions."""
    print("\n=== ctpedit status ===\n")
    print(f"  CSV source dir : {MOMJR_CSV}")
    print(f"  Scenario dir   : {SCENARIO}\n")

    for dim_id, dim in DIMENSIONS.items():
        print(f"[{dim_id}] {dim['label']}")
        for src in dim["sources"]:
            count = _csv_row_count(src)
            if count is None:
                print(f"    [N] {src:40s}  (missing)")
            else:
                print(f"    [Y] {src:40s}  {count} row(s)")
        for tgt in dim["targets"]:
            count = _target_block_count(tgt)
            if count is None:
                print(f"    [-] {tgt:40s}  (missing)")
            else:
                print(f"    [-] {tgt:40s}  {count} entry(s)")
        print()


def cmd_show(args: argparse.Namespace):
    """Print cascade documentation for a specific dimension."""
    dim_id = args.dimension
    if dim_id not in DIMENSIONS:
        print(f"Unknown dimension '{dim_id}'. Valid: {', '.join(ALL_DIMENSIONS)}")
        sys.exit(1)
    dim = DIMENSIONS[dim_id]
    print(f"\n=== {dim_id}: {dim['label']} ===\n")
    print("Source CSVs:")
    for src in dim["sources"]:
        path = MOMJR_CSV / src
        print(f"  {'[Y]' if path.exists() else '[N]'} {src}")
    print("\nTarget files:")
    for tgt in dim["targets"]:
        path = SCENARIO / tgt
        print(f"  {'[Y]' if path.exists() else '[N]'} {tgt}")
    print("\nCascade effects:")
    for note in dim["cascade"]:
        print(f"  * {note}")
    print()


def cmd_patch(args: argparse.Namespace):
    """
    Port dimension records from Civ2 CSV source to CTP2 scenario files.

    Runs ctp2_generator.py (which is idempotent), refreshes the workbook via the
    generator, and then runs mom_audit.py. The generator already has all
    cascade effects pre-wired; ctpedit is the orchestration layer that validates
    source CSV presence first.
    """
    dims: List[str] = args.dimensions

    # Validate source CSVs are present
    missing = []
    for dim_id in dims:
        if dim_id == "all":
            continue
        for src in DIMENSIONS[dim_id]["sources"]:
            if not (MOMJR_CSV / src).exists():
                missing.append(f"  {dim_id}: {src}")
    if missing:
        print("ERROR: Missing source CSV(s):")
        for m in missing:
            print(m)
        sys.exit(1)

    if dims == ["all"]:
        print_dims = ALL_DIMENSIONS
    else:
        print_dims = dims

    print("\n=== ctpedit patch ===")
    for dim_id in print_dims:
        dim = DIMENSIONS[dim_id]
        print(f"  [{dim_id}] {dim['label']}")
        for src in dim["sources"]:
            count = _csv_row_count(src)
            status = f"{count} row(s)" if count is not None else "missing"
            print(f"    source: {src} ({status})")
        for tgt in dim["targets"]:
            print(f"    target: {tgt}")
        for note in dim["cascade"]:
            print(f"    cascade: {note}")
    print()

    wants_sprites = ("sprites" in dims or "all" in dims)
    non_sprite_dims = [d for d in (ALL_DIMENSIONS if dims == ["all"] else dims)
                       if d != "sprites"]

    if args.dry_run:
        print("[dry-run] Generator not invoked.")
        if wants_sprites:
            print("[dry-run] Sprite builder not invoked.")
        return

    final_rc = 0

    if non_sprite_dims:
        print("Running generator...")
        rc = _run_generator()
        if rc != 0:
            print(f"\nERROR: Generator exited with code {rc}")
            sys.exit(rc)

        print("\nNeutralizing dangling Great Library links (all 10 dimensions)...")
        _run_fix_gl_links()

        print("\nValidating all reference surfaces (launch-clean gate)...")
        vrc = _run_validate_all_surfaces()
        if vrc != 0:
            print("WARNING: dangling references remain (see above) — NOT launch-clean.")
        final_rc = vrc

        print("\nRunning audit...")
        arc = _run_audit()
        if arc != 0:
            sys.exit(arc)

    if wants_sprites:
        print("\nBuilding unit SPR files from SPRITE_*.tga sources...")
        src = _run_build_sprites(force=getattr(args, "force", False))
        if src != 0:
            print(f"\nERROR: Sprite builder exited with code {src}")
            sys.exit(src)

    sys.exit(final_rc)


# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="ctpedit",
        description="CTP2 mod dimension patcher — ports Civ2 dimensions to CTP2 with cascade effects.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show CSV source state and target file block counts.")

    # show
    p_show = sub.add_parser("show", help="Print cascade docs for a dimension.")
    p_show.add_argument(
        "dimension",
        choices=ALL_DIMENSIONS,
        help="Dimension to describe.",
    )

    # patch
    p_patch = sub.add_parser(
        "patch",
        help="Port dimension(s) from Civ2 CSV source to CTP2 files (with cascade).",
    )
    p_patch.add_argument(
        "dimensions",
        nargs="+",
        choices=ALL_DIMENSIONS + ["all"],
        metavar="DIMENSION",
        help=f"One or more of: {', '.join(ALL_DIMENSIONS)}, all",
    )
    p_patch.add_argument(
        "--dry-run",
        action="store_true",
        help="Print cascade plan without invoking the generator.",
    )
    p_patch.add_argument(
        "--force",
        action="store_true",
        help="Force rebuild of SPR files even if they already exist (sprites dimension only).",
    )

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "patch":
        cmd_patch(args)


if __name__ == "__main__":
    main()
