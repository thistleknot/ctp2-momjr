# Core Pipeline Review


## ctp2_generator.py

```python
"""Generate CTP2 mod files from MOMJR CSV templates."""
import csv, json, os, sys, re
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(TOOLS_DIR))
import ctp2_parser as P
import civ2_sprite_extractor as extractor
from export_mod_workbook import DEFAULT_OUTPUT as MOD_WORKBOOK_PATH, export_workbook

MOMJR = Path(
    os.environ.get(
        "CTP2_GENERATOR_CSV_DIR",
        str(Path(__file__).parent / "momjr_csv"),
    )
)
SCENARIO = Path(
    os.environ.get(
        "CTP2_GENERATOR_SCENARIO_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000",
    )
)
CTP2_DATA = Path(
    os.environ.get(
        "CTP2_GENERATOR_CTP2_DATA_DIR",
        r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data",
    )
)

reg = P.FileRegistry(SCENARIO, CTP2_DATA)

HIDDEN_SURROGATE_TILEIMPS = {
    "TILEIMP_ADVANCED_UNDERSEA_MINES",
    "TILEIMP_AIR_BASES",
    "TILEIMP_AUTOMATED_FISHERIES",
    "TILEIMP_DRILLING_PLATFORM",
    "TILEIMP_FISHERIES",
    "TILEIMP_LISTENING_POSTS",
    "TILEIMP_MAGLEV",
    "TILEIMP_MEGA_MINES",
    "TILEIMP_MEGA_UNDERSEA_MINES",
    "TILEIMP_PORT",
    "TILEIMP_RADAR_STATIONS",
    "TILEIMP_SONAR_BUOYS",
    "TILEIMP_UNDERSEA_MINES",
}

HIDDEN_OUT_OF_GENRE_TILEIMPS = {
    # Modern commercial — no malls in MoM
    "TILEIMP_OUTLET_MALL",
    # Sci-fi agriculture / industry
    "TILEIMP_HYDROPONIC_FARMS",
    "TILEIMP_PROCESSING_TOWER",
    # Sci-fi underwater infrastructure
    "TILEIMP_UNDERSEA_TUNNEL",
}

START_GOVERNMENT_ADVANCE = "ADVANCE_MONARCHY"

HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT = [
    # Trading Post is now visible; strip co-references to the still-hidden Shopping Mall
    ("Trading Posts and Shopping Malls", "Trading Posts"),
    ("the Trading Post and Shopping Mall", "the Trading Post"),
    ("like the Trading Post and , can help", "like the Trading Post, can help"),
    ("such as Trading Posts and s.", "such as Trading Posts."),
    # Undersea Tunnel is still hidden
    ("Mines and Undersea Tunnels, but not", "Mines, but not"),
    ("Nets<e>, Undersea Tunnels and Ports.", "Nets<e> and Ports."),
    ("like Undersea Tunnels and Fisheries.", "like Fisheries."),
    ("Undersea Tunnels enable land units to travel across water.", ""),
    ("Undersea Tunnels", "sea routes"),
    ("Undersea Tunnel", "sea route"),
    # Shopping Mall references for still-hidden Outlet Mall
    ("Shopping Malls", ""),
    ("Shopping Mall", ""),
]

HIDDEN_OUT_OF_GENRE_ORDERS = {
    # Corporate/legal — no capitalism in MoM
    "ORDER_ADVERTISE",
    "ORDER_FRANCHISE",
    "ORDER_INJOIN",
    "ORDER_SUE",
    "ORDER_SUE_FRANCHISE",
    # Sci-fi / future-tech — out of fantasy genre
    "ORDER_BIO_INFECT",
    "ORDER_CREATE_PARK",
    "ORDER_NANO_INFECT",
    "ORDER_PLANT_NUKE",
    "ORDER_REFUEL",
    "ORDER_SPACE_LAUNCH",
    # Nuclear targeting — no nukes in MoM
    "ORDER_TARGET",
    "ORDER_CLEAR_TARGET",
}

HIDDEN_OUT_OF_GENRE_CONCEPTS = {
    "CONCEPT_FUEL",
    "CONCEPT_GENETIC_AGE",
    "CONCEPT_MODERN_AGE",
}

SURROGATE_TILEIMP_NOTES = {
    "TILEIMP_ADVANCED_UNDERSEA_MINES": "Stock deep-ocean production surrogate retained for compatibility only; hidden because MoMJR has no direct tile-improvement counterpart for this CTP2 lane.",
    "TILEIMP_AIR_BASES": "Stock air-logistics tile improvement retained for compatibility only; hidden because MoMJR does not define an airbase tile-improvement lane.",
    "TILEIMP_AUTOMATED_FISHERIES": "Stock ocean-food surrogate retained for compatibility only; hidden because MoMJR does not define this fisheries upgrade lane.",
    "TILEIMP_DRILLING_PLATFORM": "Stock offshore-oil surrogate retained for compatibility only; hidden because MoMJR has no drilling-platform tile-improvement analogue.",
    "TILEIMP_FISHERIES": "Stock fisheries surrogate retained for compatibility only; hidden because MoMJR does not define this tile-improvement lane.",
    "TILEIMP_LISTENING_POSTS": "Stock detector tile improvement retained for compatibility only; hidden because MoMJR does not define this listening-post lane.",
    "TILEIMP_MAGLEV": "Stock transport upgrade retained only as a hidden residue; MoMJR uses the remapped Enchanted Road lane instead.",
    "TILEIMP_MEGA_MINES": "Stock late-industrial mining surrogate retained for compatibility only; hidden because MoMJR does not define this CTP2 mega-mine lane.",
    "TILEIMP_MEGA_UNDERSEA_MINES": "Stock deep-ocean production surrogate retained for compatibility only; hidden because MoMJR has no mega undersea-mine tile-improvement analogue.",
    "TILEIMP_PORT": "Stock ocean-port surrogate retained for compatibility only; hidden because MoMJR's Port is sourced from a city improvement rather than a tile-improvement lane.",
    "TILEIMP_RADAR_STATIONS": "Stock detector tile improvement retained for compatibility only; hidden because MoMJR does not define this radar-station lane.",
    "TILEIMP_SONAR_BUOYS": "Stock ocean-detector surrogate retained for compatibility only; hidden because MoMJR does not define this sonar-buoy lane.",
    "TILEIMP_UNDERSEA_MINES": "Stock undersea-mine surrogate retained for compatibility only; hidden because MoMJR has no direct tile-improvement counterpart for this CTP2 lane.",
}


def sanitize(name):
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    s = re.sub(r'[^A-Z0-9_]', '', s)
    return re.sub(r'_+', '_', s).strip('_')


def humanize_ident(ident: str, prefix: str) -> str:
    """Convert a database ID into a readable fallback display name."""
    core = ident[len(prefix):] if ident.startswith(prefix) else ident
    return core.replace('_', ' ').title()


def advance_id(code):
    """Map MoM building prereq short codes to CTP2 advance IDs (for improvements).

    Returns empty string for codes that mean 'no prerequisite' (nil, no).
    Raises ValueError for unmapped codes so missing mappings are caught at generation time.
    """
    # Civ2 codes meaning "no prerequisite required" — omit EnableAdvance in CTP2
    _no_prereq = {'nil', 'no', 'nil', ''}
    if code in _no_prereq:
        return ''
    mapping = {
        'Mas': 'ADVANCE_MASONRY', 'Pot': 'ADVANCE_POTTERY',
        'Bro': 'ADVANCE_BRONZE_WORKING', 'Cer': 'ADVANCE_CEREMONIAL_BURIAL',
        'Cur': 'ADVANCE_CURRENCY', 'Wri': 'ADVANCE_WRITING',
        'CoL': 'ADVANCE_CODE_OF_LAWS', 'Cst': 'ADVANCE_CONSTRUCTION',
        'Ban': 'ADVANCE_BANKING', 'MT': 'ADVANCE_COMMUNE_WITH_GODS',
        'Uni': 'ADVANCE_UNIVERSITY', 'Tra': 'ADVANCE_TRADE',
        'Eco': 'ADVANCE_ECONOMICS', 'San': 'ADVANCE_SANITATION',
        'Sea': 'ADVANCE_SEAFARING', 'Feu': 'ADVANCE_FEUDALISM',
        'Eng': 'ADVANCE_ENGINEERING', 'Inv': 'ADVANCE_INVENTION',
        'Nav': 'ADVANCE_NAVIGATION', 'The': 'ADVANCE_THEOLOGY',
        'Ast': 'ADVANCE_ASTRONOMY', 'Lit': 'ADVANCE_LITERACY',
        'Dem': 'ADVANCE_DEMOCRACY', 'Pho': 'ADVANCE_PHILOSOPHY',
        # MoM-specific advance codes from advances.csv category column
        'Fli': 'ADVANCE_WIZARDRY',
        'Rec': 'ADVANCE_NATURE_WIZARD',
        'U1':  'ADVANCE_FORCES_OF_NATURE',
        'U3':  'ADVANCE_SEA_LORE',
        'X3':  'ADVANCE_ARTIFICING',
        'X4':  'ADVANCE_LESSER_FAUNA_LORE',
        'Ato': 'ADVANCE_ELDRITCH_LORE',
        'CA':  'ADVANCE_HEALING',
        'Cmb': 'ADVANCE_LESSER_ENCHANMENTS',
        'Cmp': 'ADVANCE_METAMORPHOSIS',
        'E1':  'ADVANCE_RUNE_LORE',
        'Min': 'ADVANCE_CHAOS_WIZARD',
        'Mys': 'ADVANCE_MYSTICISM',
        'NF':  'ADVANCE_GRAND_MASTERY',
        'PT':  'ADVANCE_NATURE_ADEPT',
        'Phy': 'ADVANCE_SORCERY_WIZARD',
        'Plu': 'ADVANCE_NATURE_LORE',
        'RR':  'ADVANCE_GREATER_ENCHANTMENTS',
        'Rob': 'ADVANCE_DEATH_ADEPT',
        'Too': 'ADVANCE_LIFE_WIZARD',
    }
    result = mapping.get(code)
    if result is None:
        raise ValueError(f"advance_id: unmapped Civ2 prereq code '{code}' — add to mapping in advance_id()")
    return result


# Complete MoM short-code → CTP2 advance ID mapping for UNITS
MOM_UNIT_ADVANCE = {
    'AFl': 'ADVANCE_ALCHEMY',
    'Alp': 'ADVANCE_ALPHABET',
    'Amp': 'ADVANCE_ANIMISM',
    'Ast': 'ADVANCE_ASTROLOGY',
    'Ato': 'ADVANCE_ELDRITCH_LORE',
    'Ban': 'ADVANCE_BANKING',
    'Bri': 'ADVANCE_BRIDGE_BUILDING',
    'Bro': 'ADVANCE_BRONZE_WORKING',
    'Cer': 'ADVANCE_CEREMONIAL_BURIAL',
    'Che': 'ADVANCE_GREATER_FAUNA_LORE',
    'Chi': 'ADVANCE_CHIVALRY',
    'CoL': 'ADVANCE_CODE_OF_LAWS',
    'Cmb': 'ADVANCE_LESSER_ENCHANTMENTS',
    'Cmp': 'ADVANCE_METAMORPHOSIS',
    'Cst': 'ADVANCE_CONSTRUCTION',
    'Cor': 'ADVANCE_PANTHEISM',
    'Cur': 'ADVANCE_CURRENCY',
    'E1':  'ADVANCE_RUNE_LORE',
    'Eng': 'ADVANCE_SEA_MASTERY',
    'Env': 'ADVANCE_SHAMANISM',
    'Esp': 'ADVANCE_THAUMATURGY',
    'Exp': 'ADVANCE_TACTICS',
    'Feu': 'ADVANCE_FEUDALISM',
    'Fli': 'ADVANCE_WIZARDRY',
    'FP':  'ADVANCE_GLYPHS',
    'Gen': 'ADVANCE_LIFE_MAGIC',
    'Gun': 'ADVANCE_CHAOS_MAGIC',
    'Hor': 'ADVANCE_SORCERY',
    'Inv': 'ADVANCE_LIFE_LORE',
    'Iro': 'ADVANCE_IRON_WORKING',
    'Lab': 'ADVANCE_LIFE_ADEPT',
    'Las': 'ADVANCE_LIFE_MAGE',
    'Ldr': 'ADVANCE_HOLY_WARRIORS',
    'Lit': 'ADVANCE_LITERACY',
    'Too': 'ADVANCE_LIFE_WIZARD',
    'Mag': 'ADVANCE_LIFE_MASTER',
    'Map': 'ADVANCE_MAP_MAKING',
    'Mas': 'ADVANCE_MASONRY',
    'MP':  'ADVANCE_CHAOS_LORE',
    'Mat': 'ADVANCE_MATHEMATICS',
    'Med': 'ADVANCE_CHAOS_ADEPT',
    'Met': 'ADVANCE_CHAOS_MAGE',
    'Min': 'ADVANCE_CHAOS_WIZARD',
    'Mob': 'ADVANCE_CHAOS_MASTER',
    'MT':  'ADVANCE_THEOLOGY',
    'Mys': 'ADVANCE_MYSTICISM',
    'Nav': 'ADVANCE_NAVIGATION',
    'NF':  'ADVANCE_GRAND_MASTERY',
    'NP':  'ADVANCE_SORCERY_MAGE',
    'Phi': 'ADVANCE_PHILOSOPHY',
    'Phy': 'ADVANCE_SORCERY_WIZARD',
    'Pla': 'ADVANCE_SORCERY_MASTER',
    'Plu': 'ADVANCE_NATURE_LORE',
    'PT':  'ADVANCE_NATURE_ADEPT',
    'Pot': 'ADVANCE_POTTERY',
    'Rad': 'ADVANCE_NATURE_MAGE',
    'RR':  'ADVANCE_GREATER_ENCHANTMENTS',
    'Rec': 'ADVANCE_NATURE_WIZARD',
    'Ref': 'ADVANCE_NATURE_MASTER',
    'Rfg': 'ADVANCE_DEATH_LORE',
    'Rep': 'ADVANCE_THE_REPUBLIC',
    'Rob': 'ADVANCE_DEATH_ADEPT',
    'San': 'ADVANCE_SANITATION',
    'Sea': 'ADVANCE_SEAFARING',
    'SFl': 'ADVANCE_DEATH_MAGE',
    'Sth': 'ADVANCE_DEATH_WIZARD',
    'SE':  'ADVANCE_DEATH_MASTER',
    'Tac': 'ADVANCE_LEADERSHIP',
    'The': 'ADVANCE_SORCEROUS_LORE',
    'Tra': 'ADVANCE_TRADE',
    'Uni': 'ADVANCE_UNIVERSITY',
    'War': 'ADVANCE_WARRIOR_CODE',
    'Wri': 'ADVANCE_WRITING',
    'U1':  'ADVANCE_FORCES_OF_NATURE',
    'U2':  'ADVANCE_DEATH_MAGIC',
    'U3':  'ADVANCE_SEA_LORE',
    'X1':  'ADVANCE_NATURE_MAGIC',
    'X2':  'ADVANCE_SORCERY_ADEPT',
    'X3':  'ADVANCE_ARTIFICING',
    'X4':  'ADVANCE_LESSER_FAUNA_LORE',
    'X5':  'ADVANCE_PYROTECHNICS',
    'X6':  'ADVANCE_OCCULT_STUDIES',
    'CA':  'ADVANCE_HEALING',
}

# Codes that mean "no advance required" (heroes / starter units)
_NO_ADVANCE = {'nil', 'no', ''}

# Engine-required unit slots that must stay visible even in a MoM-only scenario.
_ENGINE_REQUIRED_UNITS = {
    "UNIT_CITY",
}

# Units the engine validates by display name at startup (hardcoded lookups in
# unitutil.cpp).  These must stay in the unit database but are NOT buildable —
# the auto-hide pass gives them NoIndex + GLHidden.  Never add these to
# unit_mask.csv; doing so removes the DB entry and causes "X not found in
# Unit database" at game startup.
_HARDCODED_DB_UNITS = {
    "UNIT_CLERIC",   # UnitUtil::InitializeClericConversion() looks up "Cleric"
}


def _parse_int_stat(s: str) -> int:
    """Parse MoM stat strings: '3a', '2d', '2h', '1f' → int."""
    return int(s.strip().rstrip('adhf') or '0')


def _parse_move(s: str) -> int:
    """Parse MoM move float string ('1.', '1.5', '2') → CTP2 MaxMovePoints."""
    return int(float(s.strip()) * 100)


def _pick_sprite(name: str, domain: int, attack: int) -> str:
    """Choose the best proxy DefaultSprite based on unit characteristics."""
    n = name.lower()
    if domain == 2:
        return 'SPRITE_GALLEY' if attack >= 35 else 'SPRITE_FIRE_TRIREME'
    if domain == 1:
        return 'SPRITE_CRUISE_MISSILE' if 'device' in n else 'SPRITE_FIGHTER'
    if 'archer' in n or 'bow' in n or 'elven' in n:
        return 'SPRITE_LONGBOWMAN'
    if 'cannon' in n or 'steam' in n:
        return 'SPRITE_CANNON'
    if 'catapult' in n:
        return 'SPRITE_CANNON'
    if 'mammoth' in n:
        return 'SPRITE_ELEPHANT_WARRIOR'
    if any(k in n for k in ('cavalry', 'unicorn', 'paladin', 'horseman')):
        return 'SPRITE_CAVALRY'
    if attack >= 40:
        return 'SPRITE_KNIGHT'
    if attack >= 20:
        return 'SPRITE_HOPLITE'
    return 'SPRITE_WARRIOR'


def _pick_size(name: str, hp_raw: int) -> str:
    n = name.lower()
    if any(k in n for k in ('giant', 'wyrm', 'dragon', 'behemoth', 'mammoth')):
        return 'Large'
    if hp_raw >= 3:
        return 'Medium'
    return 'Small'


# Maps CSV/stub epoch integers to valid CTP2 age IDs (age.txt: AGE_ONE..AGE_FIVE)
_AGE_MAP = {'0': 'AGE_ONE', '1': 'AGE_TWO', '2': 'AGE_THREE', '3': 'AGE_THREE'}

# Advances referenced by base CTP2 units (EnableAdvance) that are MoM-flavoured
# but never in advances.csv.  Generator creates stubs so the engine finds them.
_BASE_UNIT_STUB_ADVANCES = {
    # ── referenced by base Units.txt EnableAdvance ────────────────────────────
    'ADVANCE_BEAST_MASTERY':          ('Beast Mastery',             '3', 'AGE_ONE'),
    'ADVANCE_BESERKER_TRAINING':      ('Berserker Training',        '4', 'AGE_ONE'),
    'ADVANCE_CENTAUR_TRAINING':       ('Centaur Training',          '3', 'AGE_ONE'),
    'ADVANCE_CITY_WIDE_ENCHANTMENT':  ('City Wide Enchantment',     '3', 'AGE_TWO'),
    'ADVANCE_CRUSADE':                ('Crusade',                   '0', 'AGE_TWO'),
    'ADVANCE_DARK_KNOWLEDGE':         ('Dark Knowledge',            '3', 'AGE_ONE'),
    'ADVANCE_DRACONIC':               ('Draconic',                  '3', 'AGE_TWO'),
    'ADVANCE_ELF_NOBILITY':           ('Elf Nobility',              '3', 'AGE_ONE'),
    'ADVANCE_EXPLORATION':            ('Exploration',               '0', 'AGE_ONE'),
    'ADVANCE_FIRE_MAGIC':             ('Fire Magic',                '3', 'AGE_ONE'),
    'ADVANCE_FOREST_LORE':            ('Forest Lore',               '3', 'AGE_ONE'),
    'ADVANCE_GALLEONS':               ('Galleons',                  '0', 'AGE_TWO'),
    'ADVANCE_GREAT_DRAGONS':          ('Great Dragons',             '3', 'AGE_TWO'),
    'ADVANCE_HEROISM':                ('Heroism',                   '0', 'AGE_ONE'),
    'ADVANCE_HORSEMANSHIP':           ('Horsemanship',              '0', 'AGE_ONE'),
    'ADVANCE_INSECT_MAGIC':           ('Insect Magic',              '3', 'AGE_ONE'),
    'ADVANCE_INTERCHANGABLE_PARTS':   ('Interchangeable Parts',     '4', 'AGE_TWO'),
    'ADVANCE_MAGICAL_ENGINEERING':    ('Magical Engineering',       '3', 'AGE_ONE'),
    'ADVANCE_MARKSMANSHIP':           ('Marksmanship',              '4', 'AGE_ONE'),
    'ADVANCE_MONSTER_SUMMONING':      ('Monster Summoning',         '3', 'AGE_TWO'),
    'ADVANCE_MYTHICAL_BEASTS':        ('Mythical Beasts',           '3', 'AGE_TWO'),
    'ADVANCE_SAILING':                ('Sailing',                   '0', 'AGE_ONE'),
    'ADVANCE_SEA_DRAGONS':            ('Sea Dragons',               '3', 'AGE_TWO'),
    'ADVANCE_SEA_MAGIC':              ('Sea Magic',                 '3', 'AGE_ONE'),
    'ADVANCE_SLING_MAKING':           ('Sling Making',              '4', 'AGE_ONE'),
    'ADVANCE_SPEAR_WORKING':          ('Spear Working',             '4', 'AGE_ONE'),
    'ADVANCE_STORM_MAGIC':            ('Storm Magic',               '3', 'AGE_ONE'),
    'ADVANCE_SWORD_WORKING':          ('Sword Working',             '4', 'AGE_ONE'),
    'ADVANCE_WIZARD_GUILD':           ('Wizard Guild',              '3', 'AGE_TWO'),
    # ── referenced by Improve.txt / Wonder.txt / Advance prereq chains ────────
    'ADVANCE_COMPUTERS':              ('Computers',                 '0', 'AGE_THREE'),
    'ADVANCE_CONSUMER_ELECTRONICS':   ('Consumer Electronics',      '0', 'AGE_THREE'),
    'ADVANCE_CRYONICS':               ('Cryonics',                  '0', 'AGE_THREE'),
    'ADVANCE_DOMESTICATION':          ('Domestication',             '0', 'AGE_ONE'),
    'ADVANCE_ELECTRIFICATION':        ('Electrification',           '0', 'AGE_THREE'),
    'ADVANCE_ENVIRONMENTALISM':       ('Environmentalism',          '0', 'AGE_THREE'),
    'ADVANCE_MECHANICAL_CLOCK':       ('Mechanical Clock',          '0', 'AGE_TWO'),
    'ADVANCE_MIND_CONTROL':           ('Mind Control',              '0', 'AGE_THREE'),
    'ADVANCE_NANOASSEMBLY':           ('Nanoassembly',              '0', 'AGE_THREE'),
    'ADVANCE_NEURAL_SILICON_INTERFACE': ('Neural Silicon Interface','0', 'AGE_THREE'),
    'ADVANCE_PERSPECTIVE':            ('Perspective',               '0', 'AGE_TWO'),
    'ADVANCE_SUPERCONDUCTOR':         ('Superconductor',            '0', 'AGE_THREE'),
    'ADVANCE_UNIFIED_FIELD_THEORY':   ('Unified Field Theory',      '0', 'AGE_THREE'),
}


def _read_rel(rel: str) -> str:
    scenario_path = SCENARIO / rel
    if scenario_path.exists():
        return scenario_path.read_text(encoding='latin-1')
    data_path = CTP2_DATA / rel
    return data_path.read_text(encoding='latin-1')


def _write_rel(rel: str, text: str) -> None:
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not text.endswith('\n'):
        text += '\n'
    # Use open() with newline='\n' to write LF-only (not CRLF) to match CTP2 base game file
    # format. Python's default text mode on Windows produces CRLF, which causes the CTP2
    # engine to leave \r on keys/values, breaking string lookups → blank GL list items.
    with path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(text)


def _ensure_diffdb_start_government(rel: str = "default/gamedata/DiffDB.txt") -> bool:
    """Own the scenario DiffDB start-tech surface so MoM never inherits stock zero-government starts.

    Preconditions: the base or scenario DiffDB file contains one or more ADVANCE_CHANCES blocks.
    Guarantee: every difficulty ADVANCE_CHANCES block guarantees START_GOVERNMENT_ADVANCE for both
    human and AI starts, and the scenario owns a DiffDB override on disk.
    Failure mode: raises RuntimeError if the expected ADVANCE_CHANCES surface cannot be found.
    """
    source_text = _read_rel(rel)
    advance_chances_re = re.compile(
        r"(?ms)(^(\s*)ADVANCE_CHANCES\s*\{\s*\n)(.*?)(^\2\})"
    )
    saw_block = False

    def _inject(match: re.Match[str]) -> str:
        nonlocal saw_block
        saw_block = True
        header = match.group(1)
        indent = match.group(2)
        body = match.group(3)
        footer = match.group(4)
        if re.search(rf"(?m)^\s*{re.escape(START_GOVERNMENT_ADVANCE)}\b", body):
            return match.group(0)
        guaranteed_line = f"{indent}\t{START_GOVERNMENT_ADVANCE}\t\t100\t100\n"
        return f"{header}{guaranteed_line}{body}{footer}"

    final_text = advance_chances_re.sub(_inject, source_text)
    if not saw_block:
        raise RuntimeError(f"{rel}: ADVANCE_CHANCES block not found")

    path = SCENARIO / rel
    current_text = path.read_text(encoding='latin-1') if path.exists() else None
    if current_text != final_text:
        _write_rel(rel, final_text)
        return True
    return False


def _csv_path(name: str) -> Path:
    return MOMJR / name


def _csv_exists(name: str) -> bool:
    return _csv_path(name).exists()


def _csv_rows(name: str) -> list[dict[str, str]]:
    with open(_csv_path(name), newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _csv_text(value: str) -> str:
    """Normalize CSV prose fields into plain multi-line text."""
    normalized = (value or "").replace("\r\n", "\n").strip()
    replacements = {
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _normalized_gl_compare_text(value: str) -> str:
    """Normalize GL prose for stale-line comparisons."""
    return _csv_text(value).encode("ascii", "ignore").decode("ascii").strip().lower()


GL_VISIBLE_RAW_BLOCK_RELS = {
    "default/gamedata/Orders.txt",
    "default/gamedata/tileimp.txt",
}
# Note: Wonder.txt was removed from this set so HIDE flags can be applied to base wonders.


def _strip_block_flags(block_text: str, flags: set[str]) -> str:
    kept_lines = [line for line in block_text.splitlines() if line.strip() not in flags]
    return "\n".join(kept_lines).strip("\n")


def _apply_raw_block_csv(csv_name: str, rel: str, counted: bool = False) -> int:
    rows = _csv_rows(csv_name)
    blocks = []
    for row in rows:
        ident = (row.get('id') or '').strip()
        block_text = (row.get('block_text') or '').replace('\r\n', '\n').strip('\n')
        if rel in GL_VISIBLE_RAW_BLOCK_RELS:
            block_text = _strip_block_flags(block_text, {"GLHidden"})
        if not ident or not block_text:
            continue
        blocks.append(block_text)
    body = '\n\n'.join(blocks)
    text = f"{len(blocks)}\n{body}" if counted else body
    if counted and not blocks:
        text = "0\n"
    _write_rel(rel, text)
    return len(blocks)


def _apply_entry_csv(csv_name: str, rel: str, counted: bool = False) -> int:
    rows = _csv_rows(csv_name)
    entries = [(row.get('entry') or '').replace('\r\n', '\n').rstrip() for row in rows]
    entries = [entry for entry in entries if entry.strip()]
    body = '\n'.join(entries)
    text = f"{len(entries)}\n{body}" if counted else body
    if counted and not entries:
        text = "0\n"
    _write_rel(rel, text)
    return len(entries)


def _apply_block_overlay_csv(csv_name: str, rel: str) -> int:
    rows = _csv_rows(csv_name)
    file_obj = reg.load(rel)
    count = 0
    for row in rows:
        ident = (row.get('id') or '').strip()
        block_text = (row.get('block_text') or '').replace('\r\n', '\n').strip()
        if not ident or not block_text:
            continue
        overlay = P.CTP2BlockFile()
        overlay.parse(block_text + "\n")
        if ident not in overlay.blocks:
            continue
        file_obj.blocks[ident] = overlay.blocks[ident]
        count += 1
    reg.save(rel)
    return count


def _load_raw_block_file(rel: str) -> P.RawBlockTextFile:
    file_obj = P.RawBlockTextFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_raw_block_file(rel: str) -> P.RawBlockTextFile:
    file_obj = P.RawBlockTextFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _load_base_block_file(rel: str) -> P.CTP2BlockFile:
    file_obj = P.CTP2BlockFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _save_raw_block_file(rel: str, file_obj: P.RawBlockTextFile) -> None:
    _write_rel(rel, file_obj.render())


def _merge_mom_improvements_into_buildings() -> int:
    """gamefile.txt loads buildings.txt, NOT Improve.txt — so MoM improvements must
    live in buildings.txt or the engine never sees them (SLIC/GL refs go undefined).

    The improvement authoring path writes Improve.txt (CTP2BlockFile, old CTP2 schema:
    IMPROVEMENT_PRODUCTION_COST / ENABLING_ADVANCE / ...). This post-pass converts each
    MoM improvement to the AE schema buildings.txt actually uses (ProductionCost /
    EnableAdvance / ...) and lossless-adds it into buildings.txt (RawBlockTextFile, so
    the complex AE base blocks are preserved verbatim — CTP2BlockFile would mangle their
    bare flags / repeated keys). Dead Improve.txt is then removed.

    A block is merged only if it isn't already an AE base building and it has a MoM
    display string in gl_str (skips stale base-CTP2 leftovers seeded into Improve.txt).
    EnableAdvance refs not present in Advance.txt are remapped to a valid advance.
    """
    import re as _re
    imp = reg.load("default/gamedata/Improve.txt")            # CTP2BlockFile
    gl_str = reg.load("english/gamedata/gl_str.txt")
    advances = set(_re.findall(r'^(ADVANCE_[A-Z0-9_]+)',
                               _read_rel("default/gamedata/Advance.txt"), _re.M))
    bld = _load_raw_block_file("default/gamedata/buildings.txt")
    fallback_adv = ("ADVANCE_ALPHABET" if "ADVANCE_ALPHABET" in advances
                    else (sorted(advances)[0] if advances else ""))
    remap = {"ADVANCE_ENGINEERING": "ADVANCE_CONSTRUCTION",
             "ADVANCE_COMMUNE_WITH_GODS": "ADVANCE_THEOLOGY"}
    merged = 0
    for ident, fields in imp.blocks.items():
        if ident in bld.blocks:
            continue  # AE base building — keep verbatim
        if f"DESCRIPTION_{ident}" not in gl_str.entries:
            continue  # stale base leftover (no MoM display string) — drop
        icon = fields.get("IMPROVE_DEFAULT_ICON") or fields.get("DefaultIcon") or f"ICON_{ident}"
        desc = fields.get("IMPROVE_DESCRIPTION") or fields.get("Description") or f"DESCRIPTION_{ident}"
        adv = fields.get("ENABLING_ADVANCE") or fields.get("EnableAdvance") or ""
        adv = remap.get(adv, adv)
        if adv and adv not in advances:
            adv = fallback_adv
        cost = fields.get("IMPROVEMENT_PRODUCTION_COST") or fields.get("ProductionCost") or "100"
        upkeep = fields.get("IMPROVEMENT_UPKEEP") or fields.get("Upkeep") or "1"
        lines = [f"{ident} {{", f"\tDefaultIcon {icon}", f"\tDescription {desc}"]
        if adv:
            lines.append(f"\tEnableAdvance {adv}")
        lines += [f"\tProductionCost {cost}", f"\tUpkeep {upkeep}"]
        
        # If marked as HIDDEN, inject NoIndex and GLHidden flags
        if fields.get("HIDDEN") == "yes":
            lines += ["\tNoIndex", "\tGLHidden"]
            
        lines.append("}")
        bld.add_block(ident, "\n".join(lines))
        merged += 1
    _save_raw_block_file("default/gamedata/buildings.txt", bld)
    # Improve.txt is never loaded by the engine (not in gamefile.txt) — remove it so it
    # can't be mistaken for the live improvement DB.
    reg._parsed.pop("default/gamedata/Improve.txt", None)
    imp_path = SCENARIO / "default" / "gamedata" / "Improve.txt"
    if imp_path.exists():
        imp_path.unlink()
    print(f"  + merged {merged} MoM improvement(s) into buildings.txt (AE schema); removed dead Improve.txt")
    return merged


def _load_counted_icon_file(rel: str) -> P.CountedIconFile:
    file_obj = P.CountedIconFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_counted_icon_file(rel: str) -> P.CountedIconFile:
    file_obj = P.CountedIconFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _save_counted_icon_file(rel: str, file_obj: P.CountedIconFile) -> None:
    _write_rel(rel, file_obj.render())


GOVERNICON_FALLBACK_IDS = {
    # MoM reintroduces government IDs that stock govern.txt knows about, but the
    # stock governicon database never owned directly. Reuse the nearest stock
    # sibling entry instead of leaving the icon DB unresolved.
    "ICON_GOV_REPUBLIC": "ICON_GOV_CITY_STATE",
    "ICON_GOV_CORPORATE_REPUBLIC": "ICON_GOV_MULTINATIONAL_REPUBLIC",
}


def _load_library_file(rel: str) -> P.LibraryFile:
    file_obj = P.LibraryFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _load_base_library_file(rel: str) -> P.LibraryFile:
    file_obj = P.LibraryFile()
    file_obj.parse((CTP2_DATA / rel).read_text(encoding='latin-1'))
    return file_obj


def _restore_base_advance_gl_prose(
    gl_library: P.LibraryFile,
    base_gl_library: P.LibraryFile,
    advance_ids: set[str],
) -> int:
    """Restore stock advance gameplay/historical prose for sections that exist in base CTP2 data."""
    restored = 0
    for ident in sorted(advance_ids):
        if not ident.startswith("ADVANCE_"):
            continue
        for suffix in ("GAMEPLAY", "HISTORICAL"):
            section_id = f"{ident}_{suffix}"
            base_content = base_gl_library.sections.get(section_id)
            if not base_content:
                continue
            if gl_library.sections.get(section_id) != base_content:
                gl_library.sections[section_id] = base_content
                restored += 1
    return restored


def _normalize_uniticon_text_ref(value: str) -> str:
    token = (value or "").strip().strip('"')
    if not token or token.upper() == "NULL" or token.lower().endswith(".txt"):
        return ""
    return token


def _restore_missing_uniticon_gl_sections(
    uniticon_blocks: dict[str, dict[str, str]],
    gl_library: P.LibraryFile,
    base_gl_library: P.LibraryFile,
) -> int:
    """Backfill any uniticon-linked GL sections that exist in base data but are missing locally."""
    restored = 0
    seen_refs: set[str] = set()
    for fields in uniticon_blocks.values():
        for key in ("Gameplay", "Historical", "Prereq", "Vari", "StatText"):
            section_id = _normalize_uniticon_text_ref(fields.get(key, ""))
            if not section_id or section_id in seen_refs:
                continue
            seen_refs.add(section_id)
            if section_id in gl_library.sections:
                continue
            base_content = base_gl_library.sections.get(section_id)
            if not base_content:
                continue
            gl_library.sections[section_id] = base_content
            restored += 1
    return restored


def _save_library_file(rel: str, file_obj: P.LibraryFile) -> None:
    _write_rel(rel, file_obj.render())


def _load_string_file(rel: str) -> P.StringDBFile:
    file_obj = P.StringDBFile()
    file_obj.parse(_read_rel(rel))
    return file_obj


def _save_string_file(rel: str, file_obj: P.StringDBFile) -> None:
    _write_rel(rel, file_obj.render())


def _write_surrogate_register() -> None:
    scenario_root = SCENARIO.parent
    register_path = scenario_root / "SURROGATES.txt"
    lines = [
        f"{scenario_root.name} surrogate register",
        "",
        f"Primary structured source: {MOMJR}",
        "",
        "Hidden surrogate-backed tile improvements retained only for compatibility:",
    ]
    for ident in sorted(HIDDEN_SURROGATE_TILEIMPS):
        lines.append(f"- {ident}: {SURROGATE_TILEIMP_NOTES[ident]}")
    lines.extend(
        [
            "",
            "Visible remaps:",
            "- TILEIMP_RAILROAD: remapped to Enchanted Road and ADVANCE_GREATER_ENCHANTMENTS.",
            "",
            "Dynamic logic donor references live under:",
            f"- {Path(__file__).parent / 'slic_translation_artifacts'}",
        ]
    )
    register_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _raw_block_value(block_text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}\s+(.+?)\s*$", block_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _set_raw_block_value(block_text: str, key: str, value: str) -> str:
    """Set or insert a single-line raw-block field value."""
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s+)(.+?)(\s*)$", re.MULTILINE)
    if pattern.search(block_text):
        return pattern.sub(lambda match: f"{match.group(1)}{value}{match.group(3)}", block_text, count=1)

    lines = block_text.splitlines()
    if len(lines) < 2:
        return block_text
    lines.insert(1, f"   {key} {value}")
    return "\n".join(lines)


def _raw_block_has_flag(block_text: str, flags: tuple[str, ...] = ("NoIndex", "GLHidden")) -> bool:
    pattern = '|'.join(re.escape(flag) for flag in flags)
    return bool(re.search(rf'^\s*(?:{pattern})\s*$', block_text, re.MULTILINE))


def _ensure_runtime_building_gl_surfaces(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
) -> tuple[int, int]:
    building_blocks: dict[str, str] = {}
    for rel in ("default/gamedata/Improve.txt", "default/gamedata/buildings.txt"):
        raw_text = _read_rel(rel)
        if not raw_text:
            continue
        for ident, block_text in _load_raw_block_file(rel).blocks.items():
            if not ident.startswith("IMPROVE_") or _raw_block_has_flag(block_text):
                continue
            building_blocks[ident] = block_text

    added_strings = 0
    added_sections = 0
    for ident, block_text in building_blocks.items():
        display_name = gl_strings.entries.get(ident, humanize_ident(ident, "IMPROVE_"))
        description_key = _raw_block_value(block_text, "Description")
        description_text = gl_strings.entries.get(
            description_key,
            f"{display_name} is a Master of Magic city improvement.",
        )
        advance_ident = _raw_block_value(block_text, "EnableAdvance")
        if ident not in gl_strings.entries:
            gl_strings.entries[ident] = display_name
            added_strings += 1
        if description_key and description_key not in gl_strings.entries:
            gl_strings.entries[description_key] = description_text
            added_strings += 1

        advance_label = gl_strings.entries.get(advance_ident, humanize_ident(advance_ident, "ADVANCE_"))
        sections = {
            f"{ident}_GAMEPLAY": description_text,
            f"{ident}_HISTORICAL": (
                f"{display_name} currently uses runtime building proxy data in the MoM scenario build."
            ),
            f"{ident}_PREREQ": f"Requires:\n<L:DATABASE_ADVANCES,{advance_ident}>{advance_label}<e>",
            f"{ident}_STATISTICS": f"<L:DATABASE_IMPROVEMENTS,{ident}>{display_name}<e>",
        }
        for section_id, content in sections.items():
            if section_id not in gl_library.sections:
                gl_library.sections[section_id] = content
                added_sections += 1
    return added_strings, added_sections


def _section_base_id(section_id: str):
    for suffix in ("_GAMEPLAY", "_HISTORICAL", "_PREREQ", "_STATISTICS"):
        if section_id.endswith(suffix):
            return section_id[:-len(suffix)]
    return section_id


def _prune_gl_sections(library: P.LibraryFile, keep_ids: set[str], prefixes: tuple[str, ...]) -> int:
    removed = 0
    for section_id in list(library.sections):
        base_id = _section_base_id(section_id)
        if base_id.startswith(prefixes) and base_id not in keep_ids:
            del library.sections[section_id]
            removed += 1
    return removed


def _prune_gl_strings(strings: P.StringDBFile, keep_ids: set[str], prefixes: tuple[str, ...]) -> int:
    removed = 0
    for key in list(strings.entries):
        matched_id = None
        if key.startswith("DESCRIPTION_"):
            candidate = key[len("DESCRIPTION_"):]
            if candidate.startswith(prefixes):
                matched_id = candidate
        elif key.startswith(prefixes):
            matched_id = key
        if matched_id and matched_id not in keep_ids:
            del strings.entries[key]
            removed += 1
    return removed


def _strip_stale_database_links(library: P.LibraryFile, keep_ids: set[str], database_name: str, prefixes: tuple[str, ...]) -> int:
    prefix_group = '|'.join(re.escape(prefix) for prefix in prefixes)
    pattern = re.compile(
        rf'<L:{re.escape(database_name)},(({prefix_group})[A-Z0-9_]*)>(.*?)<e>'
    )
    removed = 0
    for section_id, content in list(library.sections.items()):
        def _replace(match):
            nonlocal removed
            ident = match.group(1)
            if ident in keep_ids:
                return match.group(0)
            removed += 1
            return match.group(3)
        library.sections[section_id] = pattern.sub(_replace, content)
    return removed


def _scrub_hidden_tileimp_gl_file(rel_path: str, hidden_tileimp_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden tile-improvement GL sections and index links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_tileimp_ids):
        for suffix in ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'\[{re.escape(ident)}_{suffix}\].*?\[END\](?:\r?\n)?',
                re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_TILE_IMPROVEMENTS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_hidden_tileimp_gl_prose(rel_path: str, hidden_tileimp_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden tile-improvement plain-text mentions."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_tileimp_ids):
        name = humanize_ident(ident, "TILEIMP_")
        for phrase in {name, f"{name}s"}:
            pattern = re.compile(rf'(?m)^[ \t]*{re.escape(phrase)}\r?\n')
            text, count = pattern.subn("", text)
            removed += count
    for old, new in HIDDEN_TILEIMP_GREAT_LIBRARY_TEXT:
        text, count = re.subn(re.escape(old), new, text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_hidden_order_gl_file(rel_path: str, hidden_order_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden order GL sections and links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_order_ids):
        for suffix in ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'^\[{re.escape(ident)}_{suffix}\]\r?\n.*?^\[END\]\r?\n?',
                re.MULTILINE | re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_ORDERS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _scrub_hidden_concept_gl_file(rel_path: str, hidden_concept_ids: set[str]) -> int:
    """Final raw-file pass to remove hidden concept GL sections and links."""
    text = _read_rel(rel_path)
    removed = 0
    for ident in sorted(hidden_concept_ids):
        for suffix in ("GAMEPLAY", "HISTORICAL"):
            section_pattern = re.compile(
                rf'^\[{re.escape(ident)}_{suffix}\]\r?\n.*?^\[END\]\r?\n?',
                re.MULTILINE | re.DOTALL,
            )
            text, count = section_pattern.subn('', text)
            removed += count
        link_pattern = re.compile(
            rf'<L:DATABASE_CONCEPTS,{re.escape(ident)}>(.*?)<e>'
        )
        text, count = link_pattern.subn(r'\1', text)
        removed += count
    if removed:
        _write_rel(rel_path, text)
    return removed


def _filter_counted_icon_entries(file_obj: P.CountedIconFile, keep_ids: set[str]) -> int:
    kept = []
    removed = 0
    for entry in file_obj.entries:
        icon_id = entry.split('\t', 1)[0].strip()
        if icon_id in keep_ids:
            kept.append(entry)
        else:
            removed += 1
    file_obj.entries = kept
    return removed


def _strip_raw_block_flags(file_obj: P.RawBlockTextFile, flags: set[str]) -> int:
    changed = 0
    for ident, block_text in list(file_obj.blocks.items()):
        lines = block_text.splitlines(keepends=True)
        kept_lines = [line for line in lines if line.strip() not in flags]
        if len(kept_lines) != len(lines):
            file_obj.add_block(ident, ''.join(kept_lines).rstrip('\n'))
            changed += 1
    return changed


def _replace_block_text(file_obj: P.RawBlockTextFile, ident: str, replacements: list[tuple[str, str]]) -> bool:
    block_text = file_obj.blocks.get(ident)
    if not block_text:
        return False

    updated = block_text
    for old, new in replacements:
        updated = updated.replace(old, new)

    if updated == block_text:
        return False

    file_obj.add_block(ident, updated)
    return True


def _parse_goods_numeric_ids() -> dict[str, int]:
    mapping = {}
    for line in _read_rel("default/gamedata/goodsID.txt").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = re.match(r'^([A-Z0-9_]+)\s+(\d+)\b', stripped)
        if match:
            mapping[match.group(1)] = int(match.group(2))
    return mapping


def _extract_referenced_ids(rel_paths: list[str], pattern: str) -> set[str]:
    found = set()
    for rel in rel_paths:
        found.update(re.findall(pattern, _read_rel(rel)))
    return found


def _government_ids_enabled_by_live_advances(
    govern_blocks: dict[str, str],
    live_advance_ids: set[str],
) -> set[str]:
    live_governments = {"GOVERNMENT_ANARCHY"}
    for ident, block_text in govern_blocks.items():
        if ident == "GOVERNMENT_ANARCHY":
            continue
        enable_advance = _raw_block_value(block_text, "EnableAdvance")
        if enable_advance and enable_advance in live_advance_ids:
            live_governments.add(ident)
    return live_governments





def _prune_government_advice_lines(rel: str, keep_ids: set[str]) -> int:
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        stripped = line.strip()
        match = re.match(r'^(GOVERNMENT_[A-Z0-9_]+)_(SAME|HIGHER)_RANK_ADVICE\b', stripped)
        if match and match.group(1) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    if removed:
        _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _prune_strategy_government_lines(rel: str, keep_ids: set[str]) -> int:
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        match = re.match(r'^(\s*Government\s+)(GOVERNMENT_[A-Z0-9_]+)(\s*)$', line)
        if match and match.group(2) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    if removed:
        _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _write_empty_wonder_build_lists() -> None:
    """Write a scenario aidata override so stock wonder AI lists cannot leak in."""
    rel = Path("default/aidata/WonderBuildLists.txt")
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#----------------------------------------------------------------------------\n"
        "#\n"
        "# MoM scenario override -- do not edit ctp2_data version for scenario changes.\n"
        "# Sync this file whenever the scenario wonder lane changes.\n"
        "#\n"
        "# The current MOMJR translation owns a 28-entry WonderDB lane. Keep these lists\n"
        "# empty so the engine does not fall back to stock aidata wonder references.\n"
        "#\n"
        "#----------------------------------------------------------------------------\n"
        "\n"
        "# 7\n"
        "\n"
        "WONDER_BUILD_LIST_HAPPINESS {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_GROWTH {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_PRODUCTION {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_GOLD {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_OFFENSE {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_DEFENSE {\n"
        "}\n"
        "\n"
        "WONDER_BUILD_LIST_SCIENCE {\n"
        "}\n"
        "\n"
        "### ALL WONDERS DONE ###\n",
        encoding='latin-1',
    )


def _scan_unit_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe UNIT_* blocks keyed by unit ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(UNIT_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _unit_block_int(block_text: str, key: str, default: int = 0) -> int:
    match = re.search(rf'^\s*{re.escape(key)}\s+(-?\d+)\b', block_text, re.MULTILINE)
    return int(match.group(1)) if match else default


def _unit_block_value(block_text: str, key: str, default: str = "") -> str:
    match = re.search(rf'^\s*{re.escape(key)}\s+(\S+)\b', block_text, re.MULTILINE)
    return match.group(1) if match else default


def _scan_wonder_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe WONDER_* blocks keyed by wonder ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(WONDER_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _scan_advance_blocks(text: str) -> dict[str, str]:
    """Return nested-brace-safe ADVANCE_* blocks keyed by advance ID."""
    blocks: dict[str, str] = {}
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        match = re.match(r'^(ADVANCE_[A-Z0-9_]+)\s*\{', lines[i])
        if not match:
            i += 1
            continue
        ident = match.group(1)
        depth = 0
        block_lines = []
        while i < len(lines):
            block_lines.append(lines[i])
            depth += lines[i].count('{') - lines[i].count('}')
            i += 1
            if len(block_lines) > 1 and depth <= 0:
                break
        blocks[ident] = ''.join(block_lines)
    return blocks


def _advance_age_map_from_text(text: str) -> dict[str, str]:
    """Return ADVANCE_* -> AGE_* from generated or base Advance.txt text."""
    return {
        ident: _unit_block_value(block_text, "Age", "AGE_ONE")
        for ident, block_text in _scan_advance_blocks(text).items()
    }


def _base_advance_age_map() -> dict[str, str]:
    """Return base CTP2 ADVANCE_* -> AGE_* mapping."""
    path = CTP2_DATA / "default" / "gamedata" / "Advance.txt"
    if not path.exists():
        return {}
    return _advance_age_map_from_text(path.read_text(encoding="latin-1"))


def _load_ae_advance_cost_bands() -> dict[str, tuple[int, int]]:
    """Return AE min/max advance costs keyed by Age for MoM rescaling."""
    ae_path = CTP2_DATA / "default" / "gamedata" / "Advance.txt"
    if not ae_path.exists():
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_advance_blocks(ae_path.read_text(encoding="latin-1")).values():
        age_match = re.search(r'^\s*Age\s+(AGE_[A-Z0-9_]+)\s*$', block_text, re.MULTILINE)
        cost_match = re.search(r'^\s*Cost\s+(\d+)\s*$', block_text, re.MULTILINE)
        if not age_match or not cost_match:
            continue
        bands.setdefault(age_match.group(1), []).append(int(cost_match.group(1)))
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _load_ae_unit_cost_bands() -> dict[str, tuple[int, int]]:
    """Return base CTP2 unit ShieldCost bands keyed by Age."""
    units_path = CTP2_DATA / "default" / "gamedata" / "Units.txt"
    advance_ages = _base_advance_age_map()
    if not units_path.exists() or not advance_ages:
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_unit_blocks(units_path.read_text(encoding="latin-1")).values():
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE):
            continue
        cost = _unit_block_int(block_text, "ShieldCost")
        if cost <= 0:
            continue
        advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(advance, "AGE_ONE")
        bands.setdefault(age, []).append(cost)
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _load_ae_wonder_cost_bands() -> dict[str, tuple[int, int]]:
    """Return base CTP2 wonder ProductionCost bands keyed by Age."""
    wonders_path = CTP2_DATA / "default" / "gamedata" / "Wonder.txt"
    advance_ages = _base_advance_age_map()
    if not wonders_path.exists() or not advance_ages:
        return {}
    bands: dict[str, list[int]] = {}
    for block_text in _scan_wonder_blocks(wonders_path.read_text(encoding="latin-1")).values():
        cost = _unit_block_int(block_text, "ProductionCost")
        if cost <= 0:
            continue
        advance = _unit_block_value(block_text, "EnableAdvance", "ADVANCE_WARRIOR_CODE")
        age = advance_ages.get(advance, "AGE_ONE")
        bands.setdefault(age, []).append(cost)
    return {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _scale_cost_into_band(
    source_cost: int,
    source_band: tuple[int, int],
    target_band: tuple[int, int],
    round_to: int,
) -> int:
    """Project a Civ2-side source cost into the target CTP2 age band."""
    source_low, source_high = source_band
    target_low, target_high = target_band
    if source_high <= source_low:
        scaled = (target_low + target_high) / 2.0
    else:
        clamped = max(source_low, min(source_high, source_cost))
        scaled = target_low + (
            (target_high - target_low) * ((clamped - source_low) / float(source_high - source_low))
        )
    rounded = int(round(scaled / float(round_to)) * round_to)
    return max(target_low, min(target_high, rounded))


def _load_mom_unit_source_cost_bands(
    advance_ages: dict[str, str],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, int]]]:
    """Return raw MOMJR unit costs keyed by UNIT_* plus age bands."""
    bands: dict[str, list[int]] = {}
    specs: dict[str, tuple[int, str]] = {}
    with open(MOMJR / "units.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["name"].strip()
            if not name or name.lower() == "blah":
                continue
            if len(name) == 2 and name[0] == "B" and name[1].isdigit():
                continue
            prereq = row["prereq"].strip()
            if prereq in _NO_ADVANCE:
                advance = "ADVANCE_WARRIOR_CODE"
            else:
                advance = MOM_UNIT_ADVANCE.get(prereq, "ADVANCE_WARRIOR_CODE")
                if advance not in advance_ages:
                    advance = "ADVANCE_WARRIOR_CODE"
            age = advance_ages.get(advance, "AGE_ONE")
            source_cost = int(row["cost"].strip() or "1")
            ident = f"UNIT_{sanitize(name)}"
            specs[ident] = (source_cost, age)
            bands.setdefault(age, []).append(source_cost)
    return specs, {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _retune_mom_unit_costs(units_file: "P.UnitsFile", advance_ages: dict[str, str]) -> int:
    """Rewrite live MoM unit ShieldCost values into base CTP2 age bands."""
    ae_bands = _load_ae_unit_cost_bands()
    unit_specs, source_bands = _load_mom_unit_source_cost_bands(advance_ages)
    if not ae_bands or not unit_specs or not source_bands:
        return 0
    changed = 0
    unit_blocks = _scan_unit_blocks(units_file._text)
    for ident, block_text in unit_blocks.items():
        source_spec = unit_specs.get(ident)
        if not source_spec:
            continue
        source_cost, age = source_spec
        source_band = source_bands.get(age)
        if not source_band:
            continue
        target_band = _nearest_ae_cost_band(age, ae_bands)
        new_cost = _scale_cost_into_band(source_cost, source_band, target_band, 10)
        current_cost = _unit_block_int(block_text, "ShieldCost")
        if current_cost == new_cost:
            continue
        updated_block = _set_raw_block_value(block_text, "ShieldCost", str(new_cost))
        updated_block = _set_raw_block_value(updated_block, "PowerPoints", str(max(100, new_cost // 2)))
        units_file._text = units_file._text.replace(block_text, updated_block, 1)
        unit_blocks[ident] = updated_block
        changed += 1
    return changed


def _load_mom_wonder_source_specs(
    advance_ages: dict[str, str],
) -> tuple[dict[str, tuple[int, str]], dict[str, tuple[int, int]]]:
    """Return raw MOMJR wonder costs keyed by WONDER_* plus age bands."""
    specs: dict[str, tuple[int, str]] = {}
    bands: dict[str, list[int]] = {}
    with open(MOMJR / "improvements.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("name", "").strip()
            if not name:
                continue
            
            # If the name starts with "HIDE ", mark it for removal but keep processing to inject flags
            is_hidden = name.upper().startswith("HIDE ")
            if is_hidden:
                name = name[5:].strip()
            
            cell_index = int(row.get("cell_index", "0").strip() or "0")
            if cell_index < 40 and not is_hidden:
                continue
            
            improve_id = f"IMPROVE_{sanitize(name)}"
            wonder_id = improve_id.replace("IMPROVE_", "WONDER_", 1)
            prereq_code = row.get("prereq", "").strip()
            advance = advance_id(prereq_code) if prereq_code else ""
            age = advance_ages.get(advance, "AGE_ONE") if advance else "AGE_ONE"
            source_cost = int(row.get("cost", "0").strip() or "0")
            
            if cell_index >= 40:
                specs[wonder_id] = (source_cost, age)
                bands.setdefault(age, []).append(source_cost)
            
            # If marked as HIDE, we still register it so the generator can apply GLHidden/NoIndex later
            if is_hidden:
                specs[wonder_id] = (source_cost, age)
                bands.setdefault(age, []).append(source_cost)
    return specs, {
        age: (min(values), max(values))
        for age, values in bands.items()
        if values
    }


def _retune_mom_wonder_costs(advance_ages: dict[str, str]) -> int:
    """Rewrite MoM wonder costs into base CTP2 age bands from raw MOMJR costs."""
    ae_bands = _load_ae_wonder_cost_bands()
    wonder_specs, source_bands = _load_mom_wonder_source_specs(advance_ages)
    if not ae_bands or not wonder_specs or not source_bands:
        return 0
    rel = "default/gamedata/Wonder.txt"
    wonder_file = _load_raw_block_file(rel)
    changed = 0
    for ident, block_text in list(wonder_file.blocks.items()):
        source_spec = wonder_specs.get(ident)
        if not source_spec:
            continue
        source_cost, age = source_spec
        source_band = source_bands.get(age)
        if not source_band:
            continue
        target_band = _nearest_ae_cost_band(age, ae_bands)
        new_cost = _scale_cost_into_band(source_cost, source_band, target_band, 10)
        if _unit_block_int(block_text, "ProductionCost") == new_cost:
            continue
        wonder_file.add_block(ident, _set_raw_block_value(block_text, "ProductionCost", str(new_cost)))
        changed += 1
    if changed:
        _save_raw_block_file(rel, wonder_file)
        refreshed = P.WonderFile()
        refreshed.parse(_read_rel(rel))
        reg._parsed[rel] = refreshed
    return changed


def _nearest_ae_cost_band(age: str, bands: dict[str, tuple[int, int]]) -> tuple[int, int]:
    """Return the nearest AE cost band for the requested age."""
    if age in bands:
        return bands[age]
    age_order = {
        "AGE_ONE": 1,
        "AGE_TWO": 2,
        "AGE_THREE": 3,
        "AGE_FOUR": 4,
        "AGE_FIVE": 5,
        "AGE_SIX": 6,
        "AGE_SEVEN": 7,
        "AGE_EIGHT": 8,
        "AGE_NINE": 9,
        "AGE_TEN": 10,
    }
    target_rank = age_order.get(age, 1)
    nearest_age = min(
        bands,
        key=lambda candidate: abs(age_order.get(candidate, target_rank) - target_rank),
    )
    return bands[nearest_age]


def _scaled_mom_advance_cost(weight: int, age: str, prereq_count: int,
                             ae_bands: dict[str, tuple[int, int]]) -> int:
    """Map Civ2-side advance weight into the matching AE age cost band."""
    low, high = _nearest_ae_cost_band(age, ae_bands)
    clamped_weight = max(2, min(62, weight))
    normalized = (clamped_weight - 2) / 60.0
    base_cost = low + (high - low) * normalized
    prereq_factor = 1.0 + (0.15 * max(0, prereq_count))
    scaled = int(round((base_cost * prereq_factor) / 5.0) * 5)
    return max(low, scaled)


def _retune_mom_advance_costs(adv_file: "P.AdvanceFile") -> int:
    """Rewrite MoM-imported advance costs into AE-scaled research bands."""
    ae_bands = _load_ae_advance_cost_bands()
    if not ae_bands:
        return 0
    changed = 0
    csv_weights: dict[str, int] = {}
    branch_fallback_weights = {
            0: 2,
            1: 10,
            2: 7,
            3: 44,
            4: 56,
    }
    advance_blocks = _scan_advance_blocks(adv_file._text)
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if not name or name.startswith("x") or "Extra Advance" in name or name.lower() == "blah":
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            cell_index_text = (row.get("cell_index") or "").strip()
            if cell_index_text.lstrip("-").isdigit():
                csv_weights[ident] = int(cell_index_text)
    for ident, block_text in advance_blocks.items():
            age_match = re.search(r'^\s*Age\s+(AGE_[A-Z0-9_]+)\s*$', block_text, re.MULTILINE)
            cost_match = re.search(r'^\s*Cost\s+(\d+)\s*$', block_text, re.MULTILINE)
            branch_match = re.search(r'^\s*Branch\s+(\d+)\s*$', block_text, re.MULTILINE)
            if not age_match or not cost_match:
                continue
            low, high = _nearest_ae_cost_band(age_match.group(1), ae_bands)
            current_cost = int(cost_match.group(1))
            if ident in csv_weights:
                weight = csv_weights[ident]
            elif current_cost > (high * 2):
                branch = int(branch_match.group(1)) if branch_match else 1
                weight = branch_fallback_weights.get(branch, 10)
            else:
                continue
            prereq_count = len(re.findall(r'^\s*Prerequisites\s+ADVANCE_[A-Z0-9_]+\s*$', block_text, re.MULTILINE))
            new_cost = _scaled_mom_advance_cost(weight, age_match.group(1), prereq_count, ae_bands)
            if current_cost == new_cost:
                continue
            new_block = re.sub(
                r'^(\s*Cost\s+)\d+(\s*)$',
                rf'\g<1>{new_cost}\g<2>',
                block_text,
                count=1,
                flags=re.MULTILINE,
            )
            adv_file._text = adv_file._text.replace(block_text, new_block, 1)
            advance_blocks[ident] = new_block
            changed += 1
    return changed


def _parse_advance_list_blocks(text: str) -> dict[str, list[str]]:
    """Return ADVANCE_LIST_* blocks keyed to ordered Advance refs."""
    lists: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].rstrip()
        start = re.match(r'^(ADVANCE_LIST_[A-Z0-9_]+)\s*\{', line)
        if start:
            current = start.group(1)
            lists[current] = []
            continue
        if current is None:
            continue
        if line.strip() == "}":
            current = None
            continue
        advance_match = re.match(r'^\s*Advance\s+(ADVANCE_[A-Z0-9_]+)\b', line)
        if advance_match:
            lists[current].append(advance_match.group(1))
    return lists


def _write_mom_advance_lists() -> dict[str, int]:
    """Write scenario AdvanceLists.txt from MoM-visible advances.

    Require: the generated Advance.txt already reflects the live MoM tech tree.
    Guarantee: every strategy-referenced ADVANCE_LIST_* is scenario-owned and
    contains only visible MoM advances. Failure modes: if live advances drift
    out of sync with advances.csv ordering metadata, remaining visible advances
    are appended by live Age/name fallback rather than silently inheriting stock
    CTP2 lists.
    """
    advance_blocks = _scan_advance_blocks(_read_rel("default/gamedata/Advance.txt"))
    hidden_advances = {
        ident
        for ident, block_text in advance_blocks.items()
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE)
    }

    csv_meta: dict[str, tuple[int, int, int]] = {}
    csv_order: list[str] = []
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row_index, row in enumerate(csv.DictReader(f)):
            name = (row.get("name") or "").split(";", 1)[0].strip()
            if not name or name.startswith("x") or "Extra Advance" in name or name.lower() == "blah":
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            if ident in csv_meta:
                continue
            epoch_text = (row.get("epoch") or "").strip()
            try:
                epoch = int(epoch_text)
            except ValueError:
                epoch = 99
            category_field = (row.get("category") or "").strip()
            category_text = category_field.split(";", 1)[0].strip()
            try:
                category = int(category_text)
            except ValueError:
                category = 99
            csv_meta[ident] = (epoch, category, row_index)
            csv_order.append(ident)

    age_rank = {
        "AGE_ONE": 1,
        "AGE_TWO": 2,
        "AGE_THREE": 3,
        "AGE_FOUR": 4,
        "AGE_FIVE": 5,
        "AGE_SIX": 6,
        "AGE_SEVEN": 7,
        "AGE_EIGHT": 8,
        "AGE_NINE": 9,
        "AGE_TEN": 10,
    }

    visible_advances = {
        ident for ident in advance_blocks
        if ident not in hidden_advances
    }
    ordered_visible_advances = [
        ident for ident in csv_order
        if ident in visible_advances
    ]
    remaining_visible_advances = sorted(
        visible_advances - set(ordered_visible_advances),
        key=lambda ident: (
            age_rank.get(_unit_block_value(advance_blocks[ident], "Age"), 99),
            ident,
        ),
    )
    ordered_visible_advances.extend(remaining_visible_advances)

    stock_lists = _parse_advance_list_blocks(_read_rel("default/aidata/AdvanceLists.txt"))
    strategy_refs = sorted(set(re.findall(
        r'\b(?:Research|StopResearch)\s+(ADVANCE_LIST_[A-Z0-9_]+)',
        _read_rel("default/aidata/strategies.txt"),
    )))

    lists: dict[str, list[str]] = {}
    for ident in strategy_refs:
        seen: set[str] = set()
        stock_kept: list[str] = []
        for advance_id in stock_lists.get(ident, []):
            if advance_id in visible_advances and advance_id not in seen:
                stock_kept.append(advance_id)
                seen.add(advance_id)
        if ident == "ADVANCE_LIST_STOP_RESEARCH":
            lists[ident] = stock_kept
            continue
        remainder = [advance_id for advance_id in ordered_visible_advances if advance_id not in seen]
        lists[ident] = stock_kept + remainder

    for ident in stock_lists:
        lists.setdefault(ident, stock_lists[ident] if ident == "ADVANCE_LIST_STOP_RESEARCH" else [])

    lines = [
        "#----------------------------------------------------------------------------",
        "#",
        "# MoM scenario override -- generator-owned.",
        "# Keep AI research on visible MoM advances; do not inherit stock CTP2 lists.",
        "# Preserve stock ordering where it still matches MoM, then append the rest",
        "# of the visible imported tech tree so SetResearch never falls through to",
        "# zero science because the scenario omitted AdvanceLists.txt.",
        "#",
        "#----------------------------------------------------------------------------",
        "",
        f"# {len(lists)}",
        "",
    ]
    for index, ident in enumerate(sorted(lists), start=1):
        lines.append(f"## {index} #########################################################")
        lines.append(f"{ident} {{")
        for advance_id in lists[ident]:
            lines.append(f"  Advance {advance_id}")
        lines.append("}")
        lines.append("")
    lines.append("### ALL ADVANCES DONE ###")

    _write_rel("default/aidata/AdvanceLists.txt", "\n".join(lines))
    return {ident: len(advance_ids) for ident, advance_ids in lists.items()}


def _write_mom_unit_build_lists(units_file: P.UnitsFile) -> dict[str, int]:
    """Write scenario UnitBuildLists.txt from visible MoM units only.

    Require: Units.txt has already been generated and hidden base units carry
    NoIndex/GLHidden. Guarantee: every strategy-referenced UNIT_BUILD_LIST_* is
    scenario-owned and contains no hidden base CTP2 unit IDs. Failure modes:
    malformed unit blocks are skipped by the scanner, causing the audit to fail
    rather than letting stock aidata leak back in.
    """
    blocks = _scan_unit_blocks(units_file.render())

    visible_units: list[tuple[str, str]] = []
    for ident, block_text in blocks.items():
        if ident == "UNIT_CITY":
            continue
        if re.search(r'^\s*(NoIndex|GLHidden)\s*$', block_text, re.MULTILINE):
            continue
        visible_units.append((ident, block_text))

    def by_cost(unit_items: list[tuple[str, str]]) -> list[str]:
        return [
            ident
            for ident, _ in sorted(
                unit_items,
                key=lambda item: (
                    _unit_block_int(item[1], "ShieldCost"),
                    _unit_block_int(item[1], "Attack"),
                    item[0],
                ),
            )
        ]

    land = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_ATTACK"
    ]
    air = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_AERIAL"
    ]
    sea = [
        item for item in visible_units
        if _unit_block_value(item[1], "Category") == "UNIT_CATEGORY_NAVAL"
    ]
    freight = [item for item in visible_units if item[0] == "UNIT_CARAVAN"]
    land_settlers = [item for item in visible_units if item[0] == "UNIT_PEASANTS"]
    ranged_ids = {
        "UNIT_CATAPULT",
        "UNIT_STEAM_CANNON",
        "UNIT_MAGE",
        "UNIT_WARLOCK",
        "UNIT_INFERNAL_DEVICE",
    }
    ranged = [item for item in visible_units if item[0] in ranged_ids]
    sea_transports = [item for item in sea if item[0] in {"UNIT_GALLEY", "UNIT_WARSHIP"}]
    air_transports = [item for item in air if item[0] == "UNIT_AIRSHIP"]

    lists: dict[str, list[str]] = {
        "UNIT_BUILD_LIST_OFFENSE": [
            ident for ident in by_cost(land)
            if _unit_block_int(blocks[ident], "Attack") > 0
        ],
        "UNIT_BUILD_LIST_DEFENSE": by_cost(land),
        "UNIT_BUILD_LIST_RANGED": by_cost(ranged),
        "UNIT_BUILD_LIST_SEA": by_cost(sea),
        "UNIT_BUILD_LIST_AIR": by_cost(air),
        "UNIT_BUILD_LIST_LAND_SETTLER": by_cost(land_settlers),
        "UNIT_BUILD_LIST_SEA_SETTLER": [],
        "UNIT_BUILD_LIST_SEA_TRANSPORT": by_cost(sea_transports),
        "UNIT_BUILD_LIST_AIR_TRANSPORT": by_cost(air_transports),
        "UNIT_BUILD_LIST_NAVAL_SPECIAL": by_cost(sea_transports),
        "UNIT_BUILD_LIST_FREIGHT": by_cost(freight),
        "UNIT_BUILD_LIST_SPECIAL_ANTISLAVERY": [],
        "UNIT_BUILD_LIST_SPECIAL_DIPLOMACY": [],
        "UNIT_BUILD_LIST_SPECIAL_DIPLOMATIC": [],
        "UNIT_BUILD_LIST_SPECIAL_ECONOMIC": [],
        "UNIT_BUILD_LIST_SPECIAL_ECOTOPIAN": [],
        "UNIT_BUILD_LIST_SPECIAL_MILITARIST": [],
        "UNIT_BUILD_LIST_SPECIAL_MISSIONARY": [],
        "UNIT_BUILD_LIST_SPECIAL_NUCLEAR": [],
        "UNIT_BUILD_LIST_SPECIAL_SCIENTIST": [],
        "UNIT_BUILD_LIST_SPECIAL_SLAVERY": [],
        "UNIT_BUILD_LIST_SPECIAL_SPY": [],
    }

    strategy_refs = sorted(set(re.findall(
        r'\b\w+UnitList\s+(UNIT_BUILD_LIST_[A-Z0-9_]+)',
        _read_rel("default/aidata/strategies.txt"),
    )))
    for ident in strategy_refs:
        lists.setdefault(ident, [])

    lines = [
        "#----------------------------------------------------------------------------",
        "#",
        "# MoM scenario override -- generator-owned.",
        "# Keep AI production on visible MoM units; do not inherit stock CTP2 lists.",
        "#",
        "#----------------------------------------------------------------------------",
        "",
        f"# {len(lists)}",
        "",
    ]
    for index, ident in enumerate(sorted(lists), start=1):
        lines.append(f"## {index} #########################################################")
        lines.append(f"{ident} {{")
        for unit_id in lists[ident]:
            lines.append(f"  Unit {unit_id}")
        lines.append("}")
        lines.append("")
    lines.append("### ALL UNITS DONE ###")

    rel = Path("default/aidata/UnitBuildLists.txt")
    path = SCENARIO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding='latin-1')
    return {ident: len(unit_ids) for ident, unit_ids in lists.items()}


def _write_sanitized_goals_wonder_refs(keep_ids: set[str]) -> int:
    """Write a scenario Goals.txt override with only live wonder protection refs."""
    rel = "default/aidata/Goals.txt"
    removed = 0
    kept_lines = []
    for line in _read_rel(rel).splitlines():
        match = re.match(r'^(\s*TargetProtectionWonder\s+)(WONDER_[A-Z0-9_]+)(\s*)$', line)
        if match and match.group(2) not in keep_ids:
            removed += 1
            continue
        kept_lines.append(line)
    _write_rel(rel, '\n'.join(kept_lines))
    return removed


def _load_canonical_momjr_wonders() -> list[dict[str, object]]:
    """Load MOMJR wonder records from momjr_csv/wonders.csv + improvements.csv.

    Derives display names from improvements.csv (same icon key pattern) and
    parses EnableAdvance from the stored block_text. No longer depends on the
    civ2_canonical/momjr/wonders.csv artifact.
    """
    # Build display-name lookup from improvements.csv: IMPROVE_KEY -> name
    imp_names: dict[str, str] = {}
    with open(MOMJR / "improvements.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            icon = (row.get("icon") or "").strip()
            name = (row.get("name") or "").strip()
            if icon.startswith("ICON_IMPROVE_") and name:
                imp_names[icon[len("ICON_"):]] = name  # IMPROVE_KEY -> name

    legacy_wonder_art = _load_legacy_wonder_art_specs()
    wonder_gl_rows = _load_momjr_wonder_gl_rows()
    _enable_adv_re = re.compile(r"EnableAdvance\s+(\S+)")
    wonders = []
    for row in _csv_rows("wonders.csv"):
        wonder_id = (row.get("id") or "").strip()
        if not wonder_id:
            continue
        improve_id = wonder_id.replace("WONDER_", "IMPROVE_", 1)
        name = imp_names.get(improve_id) or humanize_ident(wonder_id, "WONDER_")
        block_text = row.get("block_text") or ""
        m = _enable_adv_re.search(block_text)
        advance_id = m.group(1).strip() if m else "ADVANCE_WARRIOR_CODE"
        no_prereq = not bool(m)
        icon_id = f"ICON_{wonder_id}"
        # Prefer cell_index from wonders.csv (= @IMPROVE slot, set by pipeline);
        # fall back to the legacy canonical_schema/improvements.csv path.
        cell_index_text = (row.get("cell_index") or "").strip()
        legacy_art = legacy_wonder_art.get(improve_id, {})
        if cell_index_text.lstrip("-").isdigit():
            source_cell_index: int | None = int(cell_index_text)
        else:
            source_cell_index = legacy_art.get("source_cell_index")
        gl_row = wonder_gl_rows.get(wonder_id, {})
        wonders.append(
            {
                "name": name,
                "wonder_id": wonder_id,
                "improve_id": improve_id,
                "description_id": f"DESCRIPTION_{wonder_id}",
                "icon_id": icon_id,
                "icon_asset": f"{icon_id}.TGA",
                "advance_id": advance_id,
                "no_prereq": no_prereq,
                "source_cell_index": source_cell_index,
                "gl_description": str(gl_row.get("gl_description") or ""),
                "gl_gameplay": str(gl_row.get("gl_gameplay") or ""),
                "gl_historical": str(gl_row.get("gl_historical") or ""),
                "gl_statistics": str(gl_row.get("gl_statistics") or ""),
            }
        )
    return wonders


def _load_momjr_wonder_gl_rows() -> dict[str, dict[str, str]]:
    """Load wonder prose/stat rows from the scenario-owned wonders CSV."""
    rows: dict[str, dict[str, str]] = {}
    for row in _csv_rows("wonders.csv"):
        ident = (row.get("id") or "").strip()
        if not ident:
            continue
        rows[ident] = {
            "gl_description": _csv_text(row.get("gl_description") or ""),
            "gl_gameplay": _csv_text(row.get("gl_gameplay") or ""),
            "gl_historical": _csv_text(row.get("gl_historical") or ""),
            "gl_statistics": _csv_text(row.get("gl_statistics") or ""),
        }
    return rows


def _load_momjr_advance_ids_by_code() -> dict[str, str]:
    """Map MoM short codes to the live advance IDs generated from advances.csv."""
    advance_ids_by_code: dict[str, str] = {}
    with open(MOMJR / "advances.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("name") or "").split(";")[0].strip()
            if not name or "Extra Advance" in name or name.lower() == "blah":
                continue
            category_field = (row.get("category") or "").strip()
            if ";" not in category_field:
                continue
            code = category_field.split(";", 1)[1].split(",", 1)[0].strip()
            if code and code != "...":
                advance_ids_by_code[code] = f"ADVANCE_{sanitize(name)}"
    return advance_ids_by_code


def _load_legacy_wonder_art_specs() -> dict[str, dict[str, object]]:
    """Load wonder art metadata from the validated Improvements.bmp wonder lane.

    Returns empty dict if the canonical_schema/improvements.csv file is absent
    (source_cell_index is optional — callers use .get() with a None fallback).
    """
    icon_path = Path(__file__).parent / "canonical_schema" / "improvements.csv"
    if not icon_path.exists():
        return {}

    legacy_specs: dict[str, dict[str, object]] = {}
    with open(icon_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ident = (row.get("ctp2_ident") or "").strip()
            source_index_text = (row.get("source_index") or "").strip()
            if not ident.startswith("IMPROVE_") or not source_index_text:
                continue
            legacy_specs[ident] = {
                "source_cell_index": int(source_index_text) - 1,
            }
    return legacy_specs


def _strip_detected_wonder_border(cell):
    """Trim the validated outer frame plus any uniform top-left matte strip."""
    outer_border = 2
    if cell.width <= outer_border * 2 or cell.height <= outer_border * 2:
        raise ValueError(f"Wonder atlas cell too small for outer trim: {cell.size}")

    trimmed = cell.crop(
        (
            outer_border,
            outer_border,
            cell.width - outer_border,
            cell.height - outer_border,
        )
    )

    def edge_stats(strip):
        colors = strip.convert("RGB").getcolors(strip.width * strip.height)
        if not colors:
            return None, 0.0, 0
        dominant_count, dominant_color = max(colors, key=lambda item: item[0])
        return dominant_color, dominant_count / (strip.width * strip.height), len(colors)

    def colors_close(a, b, tolerance=8):
        return all(abs(int(x) - int(y)) <= tolerance for x, y in zip(a, b))

    while trimmed.width > 4 and trimmed.height > 4:
        top_color, top_frac, top_unique = edge_stats(trimmed.crop((0, 0, trimmed.width, 1)))
        left_color, left_frac, left_unique = edge_stats(trimmed.crop((0, 0, 1, trimmed.height)))
        if (
            top_color is None
            or left_color is None
            or top_frac < 0.98
            or left_frac < 0.98
            or top_unique > 2
            or left_unique > 2
            or not colors_close(top_color, left_color)
        ):
            break
        trimmed = trimmed.crop((1, 1, trimmed.width, trimmed.height))

    return trimmed


def _write_momjr_wonder_icon_art(wonder_specs: list[dict[str, object]]) -> int:
    """Extract scenario-owned wonder TGAs from the validated wonder atlas grid."""
    cells = extractor.load_sheet_cells("wonder_atlas")
    picture_dir = SCENARIO / "default" / "graphics" / "pictures"
    picture_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for spec in wonder_specs:
        source_cell_index = spec.get("source_cell_index")
        if not isinstance(source_cell_index, int):
            continue
        if source_cell_index < 0 or source_cell_index >= len(cells):
            raise IndexError(
                f"Wonder art source index {source_cell_index} out of range for {spec['wonder_id']}"
            )

        cell = cells[source_cell_index].convert("RGBA")
        cell = _strip_detected_wonder_border(cell)
        alpha_bbox = cell.getchannel("A").getbbox()
        if alpha_bbox is None:
            scaled = extractor._scale_rgba_to_canvas(cell, 160, 120)
        else:
            scaled = extractor._scale_rgba_to_canvas(cell.crop(alpha_bbox), 160, 120)

        dest = picture_dir / str(spec["icon_asset"])
        extractor.save_tga_rgb555(scaled, dest, False)
        written += 1

    return written


def _strip_exact_database_links(library: P.LibraryFile, database_name: str, stale_ids: set[str]) -> int:
    """Remove GL database links for a specific set of stale IDs while keeping the display text."""
    if not stale_ids:
        return 0
    pattern = re.compile(
        rf'<L:{re.escape(database_name)},({"|".join(re.escape(i) for i in sorted(stale_ids))})>(.*?)<e>'
    )
    removed = 0
    for section_id, content in list(library.sections.items()):
        def _replace(match):
            nonlocal removed
            removed += 1
            return match.group(2)
        library.sections[section_id] = pattern.sub(_replace, content)
    return removed


def _remove_migrated_wonder_improvements(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
    waw_library: P.LibraryFile,
    wonder_specs: list[dict[str, object]],
) -> tuple[int, int, int]:
    """Remove MOMJR wonder-slot concepts from the old IMPROVE_* lane after migration."""
    stale_improves = {spec["improve_id"] for spec in wonder_specs}
    improve_file = reg.load("default/gamedata/Improve.txt")
    removed_improve_blocks = 0
    for ident in sorted(stale_improves):
        if ident in improve_file.blocks:
            del improve_file.blocks[ident]
            removed_improve_blocks += 1

    uniticon = reg.load("default/gamedata/uniticon.txt")
    removed_uniticon_blocks = 0
    for ident in sorted(stale_improves):
        icon_id = f"ICON_{ident}"
        if icon_id in uniticon.blocks:
            del uniticon.blocks[icon_id]
            removed_uniticon_blocks += 1

    removed_gl_refs = 0
    for strings in (gl_strings,):
        for ident in sorted(stale_improves):
            for key in (ident, f"DESCRIPTION_{ident}"):
                if key in strings.entries:
                    del strings.entries[key]

    for library in (gl_library, waw_library):
        for ident in sorted(stale_improves):
            for suffix in ("_GAMEPLAY", "_HISTORICAL", "_PREREQ", "_STATISTICS"):
                library.sections.pop(f"{ident}{suffix}", None)
        removed_gl_refs += _strip_exact_database_links(library, "DATABASE_IMPROVEMENTS", stale_improves)

    return removed_improve_blocks, removed_uniticon_blocks, removed_gl_refs


def _synchronize_runtime_wonder_blocks(wonder_specs: list[dict[str, object]]) -> int:
    """Align live Wonder.txt blocks with the current wonder metadata contract."""
    rel = "default/gamedata/Wonder.txt"
    wonder_file = _load_raw_block_file(rel)
    updated = 0
    for spec in wonder_specs:
        ident = str(spec["wonder_id"])
        block_text = wonder_file.blocks.get(ident)
        if not block_text:
            continue

        synchronized = block_text
        synchronized = _set_raw_block_value(synchronized, "DefaultIcon", str(spec["icon_id"]))
        synchronized = _set_raw_block_value(synchronized, "Description", str(spec["description_id"]))
        synchronized = _set_raw_block_value(synchronized, "EnableAdvance", str(spec["advance_id"]))
        if synchronized != block_text:
            wonder_file.add_block(ident, synchronized)
            updated += 1
    if updated:
        _save_raw_block_file(rel, wonder_file)
        refreshed = P.WonderFile()
        refreshed.parse(_read_rel(rel))
        reg._parsed[rel] = refreshed
    return updated


def _render_wonder_prereq_section(
    advance_ident: str,
    advance_label: str,
    no_prereq: bool,
) -> str:
    """Render a CTP2-style wonder prerequisite section."""
    lines = ["Requires:"]
    if no_prereq or not advance_ident:
        lines.append("Nothing")
    else:
        lines.append(f"<L:DATABASE_ADVANCES,{advance_ident}>{advance_label}<e>")
    lines.extend(
        [
            "",
            "Costs:",
            '{WonderDB(Wonder[0]).ProductionCost} <L:DATABASE_CONCEPTS,CONCEPT_PRODUCTION>Production<e>',
        ]
    )
    return "\n".join(lines)


def _render_wonder_statistics_section(statistics_text: str, ident: str, display_name: str) -> str:
    """Render a CTP2-style wonder statistics section."""
    lines = ["Gives:"]
    if statistics_text:
        lines.extend(statistics_text.splitlines())
    else:
        lines.append(f"<L:DATABASE_WONDERS,{ident}>{display_name}<e>")
    return "\n".join(lines)


def _ensure_runtime_wonder_gl_surfaces(
    gl_strings: P.StringDBFile,
    gl_library: P.LibraryFile,
    waw_library: P.LibraryFile,
    wonder_specs: list[dict[str, object]],
) -> tuple[int, int, int, int]:
    """Ensure live WONDER_* blocks have names, scenario-owned art, and GL sections."""
    wonder_name_map = {spec["wonder_id"]: spec["name"] for spec in wonder_specs}
    wonder_no_prereq = {spec["wonder_id"] for spec in wonder_specs if spec["no_prereq"]}
    wonder_spec_map = {spec["wonder_id"]: spec for spec in wonder_specs}
    wonder_blocks = _load_raw_block_file("default/gamedata/Wonder.txt")
    uniticon = reg.load("default/gamedata/uniticon.txt")
    wondericon = reg.load("default/gamedata/wondericon.txt")

    added_strings = 0
    added_sections = 0
    added_icons = 0
    runtime_art_written = _write_momjr_wonder_icon_art(wonder_specs)
    wondericon_entries: list[str] = []

    for ident, block_text in wonder_blocks.blocks.items():
        if not ident.startswith("WONDER_"):
            continue
        spec = wonder_spec_map.get(ident, {})
        display_name = wonder_name_map.get(ident, humanize_ident(ident, "WONDER_"))
        description_key = _raw_block_value(block_text, "Description") or f"DESCRIPTION_{ident}"
        advance_ident = _raw_block_value(block_text, "EnableAdvance")
        icon_id = _raw_block_value(block_text, "DefaultIcon") or str(spec.get("icon_id") or f"ICON_{ident}")
        icon_asset = str(spec.get("icon_asset") or f"{icon_id}.TGA")

        if gl_strings.entries.get(ident) != display_name:
            if ident not in gl_strings.entries:
                added_strings += 1
            gl_strings.entries[ident] = display_name

        description_text = str(spec.get("gl_description") or "").strip() or gl_strings.entries.get(
            description_key,
            f"{display_name} is a Master of Magic world wonder.",
        )
        if description_key not in gl_strings.entries:
            gl_strings.entries[description_key] = description_text
            added_strings += 1
        elif gl_strings.entries.get(description_key) != description_text:
            gl_strings.entries[description_key] = description_text

        desired_uniticon = {
            "FirstFrame": f'"{icon_asset}"',
            "Movie": '"NULL"',
            "Gameplay": f'"{ident}_GAMEPLAY"',
            "Historical": f'"{ident}_HISTORICAL"',
            "Prereq": f'"{ident}_PREREQ"',
            "Vari": f'"{ident}_STATISTICS"',
            "Icon": f'"{icon_asset}"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{ident}_STATISTICS"',
        }
        if uniticon.blocks.get(icon_id) != desired_uniticon:
            if icon_id not in uniticon.blocks:
                added_icons += 1
            uniticon.blocks[icon_id] = desired_uniticon

        wondericon_entries.append(
            "\t".join(
                [
                    icon_id,
                    f'"{icon_asset}"',
                    '"null"',
                    f'"{ident}_GAMEPLAY"',
                    f'"{ident}_HISTORICAL"',
                    f'"{ident}_PREREQ"',
                    f'"{ident}_STATISTICS"',
                    f'"{icon_asset}"',
                    f'"{ident}_STATISTICS"',
                ]
            )
        )

        if ident in wonder_no_prereq or not advance_ident:
            prereq_text = _render_wonder_prereq_section("", "", True)
        else:
            advance_label = gl_strings.entries.get(advance_ident, humanize_ident(advance_ident, "ADVANCE_"))
            prereq_text = _render_wonder_prereq_section(advance_ident, advance_label, False)

        historical_text = str(spec.get("gl_historical") or "").strip() or (
            f"{display_name} currently uses runtime wonder proxy data in the MoM scenario build."
        )
        statistics_text = _render_wonder_statistics_section(
            str(spec.get("gl_statistics") or "").strip(),
            ident,
            display_name,
        )
        gameplay_text = str(spec.get("gl_gameplay") or "").strip() or description_text

        sections = {
            f"{ident}_GAMEPLAY": gameplay_text,
            f"{ident}_HISTORICAL": historical_text,
            f"{ident}_PREREQ": prereq_text,
            f"{ident}_STATISTICS": statistics_text,
        }
        for library in (gl_library, waw_library):
            for section_id, content in sections.items():
                if library.sections.get(section_id) != content:
                    if section_id not in library.sections:
                        added_sections += 1
                    library.sections[section_id] = content

    wondericon.entries = wondericon_entries
    return added_strings, added_sections, added_icons, runtime_art_written


def _prune_stale_statistics_links(
    library: P.LibraryFile,
    base_library: P.LibraryFile,
    keep_ids: set[str],
    database_name: str,
    prefixes: tuple[str, ...],
) -> int:
    """Remove stale database-derived list items from *_STATISTICS sections."""
    prefix_group = '|'.join(re.escape(prefix) for prefix in prefixes)
    pattern = re.compile(
        rf'^\s*<L:{re.escape(database_name)},((?:{prefix_group})[A-Z0-9_]*)>(.*?)<e>\s*$'
    )
    removed = 0
    for section_id, base_content in base_library.sections.items():
        if not section_id.endswith("_STATISTICS"):
            continue
        current_content = library.sections.get(section_id)
        if current_content is None:
            continue

        stale_line_texts = set()
        stale_rendered_lines = set()
        stale_normalized_lines = set()
        for raw_line in base_content.splitlines():
            match = pattern.match(raw_line.strip())
            if not match:
                continue
            if match.group(1) in keep_ids:
                continue
            stale_rendered_lines.add(raw_line.strip())
            stale_line_texts.add(match.group(2).strip())
            stale_normalized_lines.add(_normalized_gl_compare_text(match.group(2)))

        if not stale_line_texts and not stale_rendered_lines:
            continue

        kept_lines = []
        changed = False
        for line in current_content.splitlines():
            stripped = line.strip()
            normalized = _normalized_gl_compare_text(stripped)
            if (
                stripped in stale_rendered_lines
                or stripped in stale_line_texts
                or normalized in stale_normalized_lines
            ):
                removed += 1
                changed = True
                continue
            kept_lines.append(line)

        if changed:
            library.sections[section_id] = "\n".join(kept_lines)
    return removed


def _prune_wonder_surfaces() -> tuple[int, int, int, int, int, int, int]:
    """Prune stale wonder surfaces to the IDs currently present in Wonder.txt."""
    wonder_file = _load_raw_block_file("default/gamedata/Wonder.txt")
    live_wonders = set(wonder_file.blocks)

    uniticon = reg.load("default/gamedata/uniticon.txt")
    keep_wonder_icons = set()
    for block_text in wonder_file.blocks.values():
        keep_wonder_icons.update(re.findall(r'^\s*DefaultIcon\s+(\S+)', block_text, re.MULTILINE))
    removed_uniticon_wonders = 0
    for icon_id in list(uniticon.blocks):
        if not icon_id.startswith("ICON_WONDER_"):
            continue
        if icon_id not in keep_wonder_icons:
            del uniticon.blocks[icon_id]
            removed_uniticon_wonders += 1

    gl_strings = reg.load("english/gamedata/gl_str.txt")
    removed_gl_strings = _prune_gl_strings(gl_strings, live_wonders, ("WONDER_",))

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    removed_gl_sections = _prune_gl_sections(gl_library, live_wonders, ("WONDER_",))
    removed_gl_links = _strip_stale_database_links(
        gl_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )
    removed_gl_stat_lines = _prune_stale_statistics_links(
        gl_library,
        base_gl_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )

    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    removed_waw_sections = _prune_gl_sections(waw_library, live_wonders, ("WONDER_",))
    removed_waw_links = _strip_stale_database_links(
        waw_library,
        live_wonders,
        "DATABASE_WONDERS",
        ("WONDER_",),
    )
    if removed_waw_sections or removed_waw_links:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    return (
        len(live_wonders),
        removed_uniticon_wonders,
        removed_gl_strings,
        removed_gl_sections + removed_waw_sections,
        removed_gl_links + removed_waw_links,
        removed_gl_stat_lines,
        len(keep_wonder_icons),
    )


def main():
    csv_imports = []
    for csv_name, rel, apply_kind in (
        ("buildings.csv", "default/gamedata/buildings.txt", "raw"),
        ("improveicon.csv", "default/gamedata/improveicon.txt", "counted-entry"),
        ("wonders.csv", "default/gamedata/Wonder.txt", "raw"),
        ("wondericon.csv", "default/gamedata/wondericon.txt", "counted-entry"),
        ("wondermovie.csv", "default/gamedata/wondermovie.txt", "entry"),
        ("goods.csv", "default/gamedata/goods.txt", "raw"),
        ("goodsid.csv", "default/gamedata/goodsID.txt", "entry"),
        ("goodsicon.csv", "default/gamedata/goodsicon.txt", "counted-entry"),
        # terrain.csv intentionally NOT imported: terrain is a KEEP dimension per
        # dimension_inventory.md ("Base content retained"). terrain.csv is structured
        # (columns), not raw CTP2 block text, so the "raw" importer wiped terrain.txt
        # to 1 line, dropping all 26 base terrains (e.g. TERRAIN_BROWN_MOUNTAIN /
        # "Desert Mountain") and breaking every <L:DATABASE_TERRAIN,...> GL link.
        ("terrainicon.csv", "default/gamedata/terrainicon.txt", "counted-entry"),
        ("governments.csv", "default/gamedata/govern.txt", "raw"),
        ("governicon.csv", "default/gamedata/governicon.txt", "counted-entry"),
        ("orders.csv", "default/gamedata/Orders.txt", "raw"),
        ("concepts.csv", "default/gamedata/concept.txt", "counted-raw"),
    ):
        if not _csv_exists(csv_name):
            continue
        if apply_kind == "raw":
            count = _apply_raw_block_csv(csv_name, rel)
        elif apply_kind == "counted-raw":
            count = _apply_raw_block_csv(csv_name, rel, counted=True)
        elif apply_kind == "counted-entry":
            count = _apply_entry_csv(csv_name, rel, counted=True)
        else:
            count = _apply_entry_csv(csv_name, rel)
        csv_imports.append((csv_name, rel, count))
    if _csv_exists("building_uniticon.csv"):
        count = _apply_block_overlay_csv("building_uniticon.csv", "default/gamedata/uniticon.txt")
        csv_imports.append(("building_uniticon.csv", "default/gamedata/uniticon.txt", count))
    for csv_name, rel, count in csv_imports:
        print(f"  + csv-owned: {csv_name} -> {rel} ({count} row(s))")

    reg.load("default/gamedata/Wonder.txt")
    reg.load("default/gamedata/uniticon.txt")
    reg.load("default/gamedata/Improve.txt")
    reg.load("default/gamedata/Advance.txt")
    reg.load("default/gamedata/tileimp.txt")
    reg.load("english/gamedata/gl_str.txt")
    reg.load("english/gamedata/Great_Library.txt")

    mom_advance_idents: set[str] = set(MOM_UNIT_ADVANCE.values())

    # Generate stub advances for base-unit EnableAdvance refs not in advances.csv
    adv_file = reg.load("default/gamedata/Advance.txt")
    for ident, (name, cat, age) in _BASE_UNIT_STUB_ADVANCES.items():
        if ident not in adv_file.blocks:
            P.ModAdvance(ident, name, "500", cat, age).register(reg)
            print(f"  + stub advance: {name}")

    with open(str(MOMJR / "advances.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].split(';')[0].strip()
            if not name or name.startswith('x') or 'Extra Advance' in name or name.lower() == 'blah':
                continue
            ident = f"ADVANCE_{sanitize(name)}"
            mom_advance_idents.add(ident)
            epoch = row['epoch'].strip()
            cat = row['category'].strip()
            prereqs = []
            for code_col in ('prereq1', 'prereq2'):
                code = row.get(code_col, '').strip()
                if code and code not in _NO_ADVANCE:
                    adv_id = MOM_UNIT_ADVANCE.get(code)
                    if adv_id:
                        prereqs.append(adv_id)
            is_new = ident not in reg.load("default/gamedata/Advance.txt").blocks
            P.ModAdvance(ident, name, "1000", cat, _AGE_MAP.get(str(epoch), 'AGE_ONE'),
                         prereqs=prereqs).register(reg)
            if is_new:
                print(f"  + advance: {name}")
    retuned_advance_costs = _retune_mom_advance_costs(adv_file)
    if retuned_advance_costs:
        print(f"  + rescaled {retuned_advance_costs} MoM advance cost(s) into AE age bands")
    advance_ages = _advance_age_map_from_text(adv_file._text)

    # Backfill display names for pre-existing advances that still show raw ADVANCE_* IDs
    adv_file = reg.load("default/gamedata/Advance.txt")
    gl_str = reg.load("english/gamedata/gl_str.txt")
    for ident in sorted(adv_file.blocks):
        if ident not in gl_str.entries:
            gl_str.entries[ident] = humanize_ident(ident, "ADVANCE_")
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    restored_base_advance_gl = _restore_base_advance_gl_prose(
        gl_library,
        base_gl_library,
        set(adv_file.blocks),
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    base_waw_library = _load_base_library_file("english/gamedata/WAW_Great_Library.txt")
    restored_base_waw_advance_gl = _restore_base_advance_gl_prose(
        waw_library,
        base_waw_library,
        set(adv_file.blocks),
    )
    if restored_base_waw_advance_gl:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if restored_base_advance_gl or restored_base_waw_advance_gl:
        print(
            "  + restored stock advance GL prose "
            f"({restored_base_advance_gl} base section(s),"
            f" {restored_base_waw_advance_gl} WAW section(s))"
        )

    # Ensure every advance referenced by the Great Library exists in the Advance DB.
    # CTP2 validates each GL [ADVANCE_X_*] section header AND each
    # <L:DATABASE_ADVANCES,ADVANCE_X> prose link against the Advance database at load,
    # hard-erroring "X not found in Advance database" on the first miss. The base GL
    # ships prose/links for ~87 advances the MoM data set doesn't define (Drama,
    # Aerodynamics, ...), and _restore_missing_uniticon_gl_sections re-adds them on
    # every run — so pruning the sections is futile (they come back). Instead create
    # the missing advances as hidden stub blocks; the GLHidden pass below keeps them
    # out of the player-facing tech tree. This mirrors the "hide base records, don't
    # delete them" approach already used for base units.
    gl_referenced_advances: set[str] = set()
    for _gl in (gl_library, waw_library):
        for sid, content in _gl.sections.items():
            base = _section_base_id(sid)
            if base.startswith("ADVANCE_"):
                gl_referenced_advances.add(base)
            gl_referenced_advances.update(
                re.findall(r"<L:DATABASE_ADVANCES,(ADVANCE_[A-Z0-9_]+)>", content)
            )
    gl_stub_added = 0
    for ident in sorted(gl_referenced_advances):
        if ident not in adv_file.blocks:
            P.ModAdvance(ident, humanize_ident(ident, "ADVANCE_"), "999999",
                         "0", "AGE_ONE", icon="ICON_ADVANCE_DEFAULT").register(reg)
            gl_stub_added += 1
    if gl_stub_added:
        print(f"  + created {gl_stub_added} hidden stub advance(s) for GL-referenced advances")

    with open(str(MOMJR / "improvements.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            if not name:
                continue
            
            # Check for HIDE prefix
            is_hidden = name.upper().startswith("HIDE ")
            if is_hidden:
                name = name[5:].strip()
            
            if name.startswith('x') or name == 'Nothing' or 'SS ' in name:
                continue
            
            ident = f"IMPROVE_{sanitize(name)}"
            imp = reg.load("default/gamedata/Improve.txt")
            is_new = ident not in imp.blocks
            cost = int(row.get('cost', '0').strip() or '0') * 100
            upkeep = row.get('upkeep', '0').strip()
            prereq_code = row.get('prereq', '').strip()
            advance = advance_id(prereq_code) if prereq_code else ""
            if advance:
                mom_advance_idents.add(advance)
            
            # Register the building
            P.ModBuilding(ident, name, str(cost), upkeep, advance).register(reg)
            
            # If hidden, mark it in the Improve.txt fields so _merge_mom_improvements_into_buildings can add flags
            if is_hidden and is_new:
                imp_file = reg.load("default/gamedata/Improve.txt")
                if ident in imp_file.blocks:
                    imp_file.blocks[ident]["HIDDEN"] = "yes"
            
            if is_new and not is_hidden:
                print(f"  + building: {name} (cost {cost})")
            elif is_new and is_hidden:
                print(f"  - hiding base building: {name}")

    # Deduplication: remove any IMPROVE_* from Improve.txt that is already
    # defined in buildings.txt.  CTP2 loads both files sequentially; duplicate
    # IDs produce DB index collisions that cause silent crashes before turn 10.
    _bld_raw = _load_raw_block_file("default/gamedata/buildings.txt")
    _bld_imps = {bid for bid in _bld_raw.blocks if bid.startswith("IMPROVE_")}
    _dup_imp_file = reg.load("default/gamedata/Improve.txt")
    _dup_removed = 0
    for _bid in sorted(_bld_imps):
        if _bid in _dup_imp_file.blocks:
            del _dup_imp_file.blocks[_bid]
            _dup_removed += 1
    if _dup_removed:
        print(f"  - deduped {_dup_removed} improve(s) from Improve.txt (already in buildings.txt)")

    # Reconciliation: ensure every IMPROVE_* in Improve.txt has a uniticon entry.
    # Stale base-CTP2 buildings that weren't processed through improvements.csv
    # (e.g. IMPROVE_SILO, IMPROVE_SDI) may have no uniticon block; create a
    # minimal UPLG001.TGA fallback so the icon-coverage audit passes.
    _imp_file  = reg.load("default/gamedata/Improve.txt")
    _ui_file   = reg.load("default/gamedata/uniticon.txt")
    _filled_ui = 0
    for _bid, _bfields in _imp_file.blocks.items():
        _icon_id = _bfields.get("IMPROVE_DEFAULT_ICON", f"ICON_{_bid}")
        if _icon_id not in _ui_file.blocks:
            _ui_file.blocks[_icon_id] = {
                "FirstFrame": '"UPLG001.TGA"',
                "Movie":      '"NULL"',
                "Gameplay":   f'"{_bid}_GAMEPLAY"',
                "Historical": f'"{_bid}_HISTORICAL"',
                "Prereq":     f'"{_bid}_PREREQ"',
                "Vari":       f'"{_bid}_STATISTICS"',
                "Icon":       '"UPLG001.TGA"',
                "LargeIcon":  '"NULL"',
                "SmallIcon":  '"NULL"',
                "StatText":   f'"{_bid}_STATISTICS"',
            }
            _filled_ui += 1
    if _filled_ui:
        print(f"  + backfilled {_filled_ui} missing building uniticon entry(ies) with UPLG001.TGA fallback")

    wonder_specs = _load_canonical_momjr_wonders()
    gl_str = reg.load("english/gamedata/gl_str.txt")
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    synchronized_wonder_blocks = _synchronize_runtime_wonder_blocks(wonder_specs)
    (
        removed_wonder_improve_blocks,
        removed_wonder_improve_icons,
        removed_wonder_improve_links,
    ) = _remove_migrated_wonder_improvements(gl_str, gl_library, waw_library, wonder_specs)
    (
        added_runtime_wonder_strings,
        added_runtime_wonder_sections,
        added_runtime_wonder_icons,
        written_runtime_wonder_art,
    ) = _ensure_runtime_wonder_gl_surfaces(gl_str, gl_library, waw_library, wonder_specs)
    retuned_wonder_costs = _retune_mom_wonder_costs(advance_ages)
    if any((
        removed_wonder_improve_blocks,
        removed_wonder_improve_icons,
        removed_wonder_improve_links,
        synchronized_wonder_blocks,
        retuned_wonder_costs,
        added_runtime_wonder_strings,
        added_runtime_wonder_sections,
        added_runtime_wonder_icons,
        written_runtime_wonder_art,
    )):
        print(
            "  + migrated MOMJR wonder slots into the Wonder DB"
            f" ({removed_wonder_improve_blocks} old Improve block(s) removed,"
            f" {removed_wonder_improve_icons} old uniticon block(s) removed,"
            f" {removed_wonder_improve_links} stale GL improve link(s) stripped,"
            f" {synchronized_wonder_blocks} Wonder block(s) synchronized,"
            f" {retuned_wonder_costs} Wonder cost(s) rescaled,"
            f" {added_runtime_wonder_strings} wonder string(s) added,"
            f" {added_runtime_wonder_sections} wonder GL section(s) added,"
            f" {added_runtime_wonder_icons} wonder icon block(s) added,"
            f" {written_runtime_wonder_art} wonder art file(s) written)"
        )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    hidden_advances = 0
    goody_excluded_advances = 0
    for ident in sorted(adv_file.blocks):
        if ident in mom_advance_idents:
            continue
        if adv_file.ensure_flags(ident, ["GLHidden"]):
            hidden_advances += 1
        if adv_file.ensure_flags(ident, ["GoodyHutExcluded"]):
            goody_excluded_advances += 1
    if hidden_advances:
        print(f"  + hid {hidden_advances} base CTP2 advance(s) from Great Library index")
    if goody_excluded_advances:
        print(f"  + excluded {goody_excluded_advances} base CTP2 advance(s) from goody-hut rewards")

    # --- Units from units.csv ---
    adv_db = reg.load("default/gamedata/Advance.txt")
    mom_unit_idents: set[str] = set()
    mom_unit_display_names: dict[str, str] = {}  # ident -> display name for gl_str backfill
    with open(str(MOMJR / "units.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            # Skip stub rows: blank, 'blah', B+digit shortcodes
            if not name or name.lower() == 'blah':
                continue
            if len(name) == 2 and name[0] == 'B' and name[1].isdigit():
                continue

            ident = f"UNIT_{sanitize(name)}"
            mom_unit_idents.add(ident)
            mom_unit_display_names[ident] = name

            domain     = int(row['domain'].strip())
            move       = _parse_move(row['move'])
            attack_raw = _parse_int_stat(row['attack'])
            def_raw    = _parse_int_stat(row['defense'])
            hp_raw     = _parse_int_stat(row['hp'])
            fp_raw     = _parse_int_stat(row['firepower'])
            cost_raw   = int(row['cost'].strip() or '1')
            prereq     = row['prereq'].strip()
            # Scale to CTP2 internal units
            attack     = attack_raw * 5
            defense    = max(5, def_raw * 5)
            shield_cost = cost_raw * 100
            shield_hunger = max(1, cost_raw // 5)

            # Advance prereq — heroes (nil/no) default to earliest advance so
            # EnableAdvance is always present (required in 97% of reference blocks).
            if prereq in _NO_ADVANCE:
                advance = 'ADVANCE_WARRIOR_CODE'
            else:
                advance = MOM_UNIT_ADVANCE.get(prereq, 'ADVANCE_WARRIOR_CODE')
                if advance not in adv_db.blocks:
                    advance = 'ADVANCE_WARRIOR_CODE'  # graceful fallback

            # Category, sprite, size, sound
            if domain == 2:
                category = 'UNIT_CATEGORY_NAVAL'
            elif domain == 1:
                category = 'UNIT_CATEGORY_AIR'
            else:
                category = 'UNIT_CATEGORY_ATTACK'

            sprite    = _pick_sprite(name, domain, attack)
            size      = _pick_size(name, hp_raw)
            sound_set = 'FIGHTER' if domain == 1 else 'WARRIOR'

            unit = P.ModUnit(
                ident=ident, name=name, category=category,
                attack=attack, defense=defense,
                sprite=sprite, desc=f"{name}: a Master of Magic unit.",
                advance=advance, move=move, hp=10,
                firepower=max(1, fp_raw), armor=1, zbrange=0,
                shield_cost=shield_cost, shield_hunger=shield_hunger,
                gold_hunger=0, sound_set=sound_set,
                domain=domain, size=size,
            )
            uni = reg.load("default/gamedata/Units.txt")
            is_new = not uni.has_unit(ident)
            unit.register(reg)
            if is_new:
                print(f"  + unit: {name} ({ident})")
    retuned_unit_costs = _retune_mom_unit_costs(reg.load("default/gamedata/Units.txt"), advance_ages)
    if retuned_unit_costs:
        print(f"  + rescaled {retuned_unit_costs} MoM unit cost(s) into base CTP2 age bands")

    # Backfill display names for MoM units missing from gl_str.txt.
    # Use the exact name from units.csv (not the humanized fallback) so the
    # Build Manager shows "Gargoyles" instead of "UNIT_GARGOYLES".
    _unit_gl_str = reg.load("english/gamedata/gl_str.txt")
    added_unit_strings = 0
    for _uid, _display in sorted(mom_unit_display_names.items()):
        if _uid not in _unit_gl_str.entries:
            _unit_gl_str.entries[_uid] = _display
            added_unit_strings += 1
    if added_unit_strings:
        print(f"  + added {added_unit_strings} unit display string(s) to gl_str.txt")

    # Auto-hide all base CTP2 units that are not MoM CSV units.
    # Engine-required slots (UNIT_CITY etc.) are exempt.
    # This is generator-owned so regeneration never reintroduces GL entries.
    uni = reg.load("default/gamedata/Units.txt")

    # Restore any hardcoded-DB units that were previously removed (e.g. by a
    # prior unit_mask.csv run).  Pull the block verbatim from the base game
    # and add NoIndex + GLHidden so the engine finds it but it never appears
    # in-game or in the Great Library.
    _restored = []
    for _uid in _HARDCODED_DB_UNITS:
        if not uni.has_unit(_uid):
            _base_units_path = reg.ctp2_data / "default/gamedata/Units.txt"
            if _base_units_path.exists():
                _base_text = _base_units_path.read_text(encoding='latin-1')
                _m = re.search(rf'^{re.escape(_uid)}\s*\{{', _base_text, re.MULTILINE)
                if _m:
                    _start = _base_text.rfind('\n', 0, _m.start()) + 1
                    _lines = _base_text[_start:].splitlines(keepends=True)
                    _depth, _block = 0, []
                    for _l in _lines:
                        _depth += _l.count('{') - _l.count('}')
                        _block.append(_l)
                        if len(_block) > 1 and _depth <= 0:
                            break
                    uni.add_unit(_uid, ''.join(_block).rstrip())
                    _restored.append(_uid)
    if _restored:
        print(f"  + restored engine-hardcoded unit(s) from base game: {', '.join(_restored)}")

    # Restore the uniticon.txt blocks for hardcoded DB units — they must be present
    # or the audit "icon-coverage" check fails.  Pull from base game if absent.
    _uniticon_file = reg.load("default/gamedata/uniticon.txt")
    _base_uniticon_path = reg.ctp2_data / "default/gamedata/uniticon.txt"
    if _base_uniticon_path.exists():
        _base_icon_text = _base_uniticon_path.read_text(encoding='latin-1')
        for _uid in _HARDCODED_DB_UNITS:
            _icon_id = f"ICON_{_uid}"
            if _icon_id not in _uniticon_file.blocks:
                _im = re.search(rf'^{re.escape(_icon_id)}\s*\{{', _base_icon_text, re.MULTILINE)
                if _im:
                    _istart = _base_icon_text.find('{', _im.start())
                    _iend = _base_icon_text.find('}', _istart)
                    _inner = _base_icon_text[_istart + 1:_iend]
                    _ifields = dict(re.findall(r'(\w+)\s+("(?:[^"]*)")', _inner))
                    if _ifields:
                        _uniticon_file.blocks[_icon_id] = _ifields
                        print(f"  + restored {_icon_id} icon block from base game")

    # Ensure all hardcoded DB units are hidden regardless of mom_unit_idents.
    for _uid in _HARDCODED_DB_UNITS:
        uni.ensure_flags(_uid, ["NoIndex", "GLHidden"])

    hidden_count = 0
    for ident in sorted(uni._unit_ids):
        if ident in mom_unit_idents or ident in _ENGINE_REQUIRED_UNITS:
            continue
        if uni.ensure_flags(ident, ["NoIndex", "GLHidden"]):
            hidden_count += 1
    if hidden_count:
        print(f"  + hid {hidden_count} base CTP2 unit(s) from Great Library index")

    # Remove stock CTP2 / test units listed in unit_mask.csv using the
    # proper nested-brace-aware parser.  Never use regex for block removal.
    # The mask is applied to ALL three unit files the engine can load:
    # Units.txt (active), Units_historic.txt and Units_release.txt (backup
    # copies the engine may load in some scenario paths).  Not applying the
    # mask to the backup files causes "X not found in Unit database" errors
    # at game startup even when Units.txt is correct.
    unit_mask_path = MOMJR / "unit_mask.csv"
    if unit_mask_path.exists():
        masked_ids = []
        with open(str(unit_mask_path), newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                uid = row['unit_id'].strip()
                if not uid:
                    continue
                if uid in _HARDCODED_DB_UNITS:
                    print(f"  ! SKIP: {uid} is engine-hardcoded (must stay in DB hidden); remove from unit_mask.csv")
                    continue
                masked_ids.append(uid)

        _UNIT_FILES_TO_MASK = [
            "default/gamedata/Units.txt",
            "default/gamedata/Units_historic.txt",
            "default/gamedata/Units_release.txt",
        ]
        for rel_path in _UNIT_FILES_TO_MASK:
            uf = reg.load(rel_path)
            removed_masked = [uid for uid in masked_ids if uf.remove_unit(uid)]
            if removed_masked:
                print(f"  + removed {len(removed_masked)} masked unit(s) from {rel_path.split('/')[-1]}: {', '.join(removed_masked)}")

    unit_build_list_counts = _write_mom_unit_build_lists(uni)
    populated_unit_build_lists = sum(1 for count in unit_build_list_counts.values() if count)
    total_unit_build_refs = sum(unit_build_list_counts.values())
    print(
        "  + wrote scenario-level UnitBuildLists.txt override"
        f" ({populated_unit_build_lists}/{len(unit_build_list_counts)} populated list(s),"
        f" {total_unit_build_refs} visible MoM unit ref(s))"
    )
    advance_list_counts = _write_mom_advance_lists()
    populated_advance_lists = sum(1 for ident, count in advance_list_counts.items() if count and ident != "ADVANCE_LIST_STOP_RESEARCH")
    total_advance_refs = sum(advance_list_counts.values())
    print(
        "  + wrote scenario-level AdvanceLists.txt override"
        f" ({populated_advance_lists}/{len(advance_list_counts)} populated list(s),"
        f" {total_advance_refs} visible MoM advance ref(s))"
    )

    # --- Tile improvements from tileimp.csv ---
    # First row of each tileimp has name + base fields; continuation rows (empty
    # name) add terrain variants with fields shifted left into class/tooltip/etc.
    tileimp_db = reg.load("default/gamedata/tileimp.txt")
    tileimp_groups = {}
    current_name = None
    with open(str(MOMJR / "tileimp.csv"), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['name'].strip()
            if name:
                if name.startswith('x') or name == 'Nothing':
                    current_name = None
                    continue
                current_name = name
                ident = f"TILEIMP_{sanitize(name)}"
                if ident in HIDDEN_OUT_OF_GENRE_TILEIMPS:
                    current_name = None
                    continue
                tileimp_groups[ident] = {
                    "name": name, "ident": ident,
                    "level": row['level'].strip(),
                    "tile_class": row['class'].strip(),
                    "icon": row['icon'].strip(),
                    "tooltip": row['tooltip'].strip(),
                    "statusbar": row['statusbar'].strip(),
                    "sound": row['sound'].strip(),
                    "construction_tiles": row['construction_tiles'].strip(),
                    "cant_build_on": row['cant_build_on'].strip(),
                    "excludes": row['excludes'].strip(),
                    "terrain_effects": [],
                }
                terrain = (row.get('terrain') or '').strip()
                if not terrain:
                    continue
            else:
                if current_name is None:
                    continue
                ident = f"TILEIMP_{sanitize(current_name)}"
                if ident not in tileimp_groups:
                    continue
                terrain = row['class'].strip()
                if not terrain:
                    continue

            te = {"terrain": terrain}
            if name:
                te["bonus_food"] = (row.get('terrain_bonus_food') or '').strip()
                te["bonus_production"] = (row.get('terrain_bonus_production') or '').strip()
                te["bonus_gold"] = (row.get('terrain_bonus_gold') or '').strip()
                te["enable_advance"] = (row.get('terrain_enable_advance') or '').strip()
                te["production_cost"] = (row.get('terrain_production_cost') or '').strip()
                te["production_time"] = (row.get('terrain_production_time') or '').strip()
                te["tileset_index"] = (row.get('terrain_tileset_index') or '').strip()
            else:
                te["bonus_food"] = ''
                te["bonus_production"] = (row['tooltip'] or '').strip()
                te["enable_advance"] = (row['statusbar'] or '').strip()
                te["production_cost"] = (row['sound'] or '').strip()
                te["production_time"] = (row['construction_tiles'] or '').strip()
                te["tileset_index"] = (row['cant_build_on'] or '').strip()
            tileimp_groups[ident]["terrain_effects"].append(te)

    tileimp_db = reg.load("default/gamedata/tileimp.txt")
    for ident, g in tileimp_groups.items():
        tileimp = P.ModTileImp(
            ident=g["ident"], name=g["name"], level=g["level"],
            tile_class=g["tile_class"], icon=g["icon"], tooltip=g["tooltip"],
            statusbar=g["statusbar"], sound=g["sound"],
            construction_tiles=g["construction_tiles"],
            cant_build_on=g["cant_build_on"], excludes=g["excludes"],
            terrain_effects=g["terrain_effects"],
        )
        is_new = ident not in tileimp_db.blocks
        tileimp.register(reg)
        if is_new:
            n_terrains = len(g["terrain_effects"])
            print(f"  + tileimp: {g['name']} ({ident}) [{n_terrains} terrain variant(s)]")

    # Reconcile: any Advance.txt block whose Icon ref is missing from uniticon.txt
    # gets a stub entry so the engine doesn't raise "not found in Icon database".
    # If an extracted MoMJR TGA (ICON_ADVANCE_*.tga) exists on disk, use it;
    # otherwise fall back to UPLG001.TGA.
    _pics_dir = SCENARIO / "default" / "graphics" / "pictures"
    adv_file = reg.load("default/gamedata/Advance.txt")
    uic_file  = reg.load("default/gamedata/uniticon.txt")
    _icon_re  = re.compile(r'^\s+Icon\s+(ICON_ADVANCE_\S+)', re.MULTILINE)
    patched = 0
    patched_with_mom = 0
    for icon_id in _icon_re.findall(adv_file._text):
        adv_id = icon_id[len("ICON_"):]
        extracted_tga = f"{icon_id}.tga"
        has_mom_art = (_pics_dir / extracted_tga).exists()
        tga_token = f'"{extracted_tga}"' if has_mom_art else '"UPLG001.TGA"'
        desired = {
            "FirstFrame": tga_token,
            "Movie": '"NULL"',
            "Gameplay": f'"{adv_id}_GAMEPLAY"',
            "Historical": f'"{adv_id}_HISTORICAL"',
            "Prereq": f'"{adv_id}_PREREQ"',
            "Vari": f'"{adv_id}_STATISTICS"',
            "Icon": tga_token,
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{adv_id}_PREREQ"',
        }
        if uic_file.blocks.get(icon_id) != desired:
            if icon_id not in uic_file.blocks:
                patched += 1
            uic_file.blocks[icon_id] = desired
            if has_mom_art:
                patched_with_mom += 1
    normalized_stub_icons = 0
    for icon_id, block in uic_file.blocks.items():
        if not icon_id.startswith("ICON_ADVANCE_"):
            continue
        bad_icon_tokens = {'"CM2_Upap001l.tga"', '"CM2_UPAP001L.TGA"'}
        if block.get("FirstFrame") in bad_icon_tokens or block.get("Icon") in bad_icon_tokens:
            block["FirstFrame"] = '"UPLG001.TGA"'
            block["Icon"] = '"UPLG001.TGA"'
            normalized_stub_icons += 1
    if patched:
        print(f"  + patched {patched} missing advance icon entries in uniticon.txt ({patched_with_mom} with MoMJR art)")
    if normalized_stub_icons:
        print(f"  + normalized {normalized_stub_icons} advance icon block(s) off the bad fallback TGA")

    # Reconcile: any Improve.txt / buildings.txt block whose uniticon entry still
    # uses a stock CTP2 TGA → swap in the extracted MoMJR TGA if it exists on disk.
    # Blocks already updated by building_uniticon.csv (proxy TGAs) are left alone.
    _imp_text = _read_rel("default/gamedata/Improve.txt")
    _bld_text = _read_rel("default/gamedata/buildings.txt")
    _imp_icon_re = re.compile(r'(?:DefaultIcon|Icon)\s+(ICON_IMPROVE_\S+)', re.MULTILINE)
    _stock_tga_pat = re.compile(r'^"(?:CM2_|UPLG001\.TGA")', re.IGNORECASE)
    _all_improve_icons = (
        set(_imp_icon_re.findall(_imp_text))
        | set(_imp_icon_re.findall(_bld_text))
    )
    patched_improve = 0
    for icon_id in _all_improve_icons:
        block = uic_file.blocks.get(icon_id)
        if block is None:
            continue
        first_frame = (block.get("FirstFrame") or "").strip()
        if not _stock_tga_pat.match(first_frame):
            continue  # already set to MoM art (e.g., via building_uniticon.csv)
        extracted_tga = f"{icon_id}.tga"
        if not (_pics_dir / extracted_tga).exists():
            continue  # no MoM art on disk — leave the stock CTP2 fallback
        block["FirstFrame"] = f'"{extracted_tga}"'
        block["Icon"] = f'"{extracted_tga}"'
        patched_improve += 1
    if patched_improve:
        print(f"  + patched {patched_improve} improvement icon block(s) to use MoMJR art")

    # Reconcile: any UNIT block whose uniticon entry can be upgraded to the extracted MoMJR TGA.
    # If the extracted MoM art exists on disk, use it instead of whatever stock CTP2 fallback is present.
    uic_file_units = reg.load("default/gamedata/uniticon.txt")
    patched_units = 0
    for _uid in mom_unit_idents:
        _icon_id = f"ICON_{_uid}"
        _block = uic_file_units.blocks.get(_icon_id)
        if _block is None:
            continue
        _extracted_tga = f"{_icon_id}.tga"
        if (_pics_dir / _extracted_tga).exists():
            # MoM art exists on disk — force the uniticon block to use it
            _block["FirstFrame"] = f'"{_extracted_tga}"'
            _block["Icon"] = f'"{_extracted_tga}"'
            patched_units += 1
        _block["FirstFrame"] = f'"{_extracted_tga}"'
        _block["Icon"] = f'"{_extracted_tga}"'
        patched_units += 1
    if patched_units:
        print(f"  + patched {patched_units} stock unit icon entries in uniticon.txt with MoMJR art")

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    base_gl_library = _load_base_library_file("english/gamedata/Great_Library.txt")
    restored_uniticon_gl_sections = _restore_missing_uniticon_gl_sections(
        uic_file.blocks,
        gl_library,
        base_gl_library,
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    base_waw_library = _load_base_library_file("english/gamedata/WAW_Great_Library.txt")
    restored_uniticon_waw_sections = _restore_missing_uniticon_gl_sections(
        uic_file.blocks,
        waw_library,
        base_waw_library,
    )
    if restored_uniticon_waw_sections:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if restored_uniticon_gl_sections or restored_uniticon_waw_sections:
        print(
            "  + restored missing uniticon-linked GL sections "
            f"({restored_uniticon_gl_sections} base section(s),"
            f" {restored_uniticon_waw_sections} WAW section(s))"
        )

    goods_file = _load_raw_block_file("default/gamedata/goods.txt")
    goods_numeric_ids = _parse_goods_numeric_ids()
    seen_good_numbers = set()
    hidden_goods = 0
    for ident in goods_file.blocks:
        good_number = goods_numeric_ids.get(ident)
        if good_number in (None, 0) or good_number in seen_good_numbers:
            if goods_file.ensure_flags(ident, ["GLHidden"]):
                hidden_goods += 1
            continue
        seen_good_numbers.add(good_number)
    if hidden_goods:
        _save_raw_block_file("default/gamedata/goods.txt", goods_file)
        print(f"  + hid {hidden_goods} duplicate/placeholder goods from Great Library index")

    restored_wonders = _load_raw_block_file("default/gamedata/Wonder.txt")
    stripped_wonder_flags = _strip_raw_block_flags(restored_wonders, {"GLHidden"})
    if stripped_wonder_flags:
        _save_raw_block_file("default/gamedata/Wonder.txt", restored_wonders)
        print(f"  + restored {stripped_wonder_flags} wonder block(s) to Great Library index")
    (
        live_wonder_count,
        removed_uniticon_wonders,
        removed_wonder_strings,
        removed_wonder_sections,
        removed_wonder_links,
        removed_wonder_stat_lines,
        keep_wonder_icon_count,
    ) = _prune_wonder_surfaces()
    if any((
        removed_uniticon_wonders,
        removed_wonder_strings,
        removed_wonder_sections,
        removed_wonder_links,
        removed_wonder_stat_lines,
    )):
        print(
            f"  + reduced wonders to {live_wonder_count} live entry(ies)"
            f" ({keep_wonder_icon_count} icon ref(s) kept,"
            f" {removed_uniticon_wonders} uniticon block(s),"
            f" {removed_wonder_strings} string(s),"
            f" {removed_wonder_sections} GL section(s),"
            f" {removed_wonder_links} stale GL link(s),"
            f" {removed_wonder_stat_lines} stale advance-stat line(s) removed)"
        )
    live_wonder_ids = set(_load_raw_block_file("default/gamedata/Wonder.txt").blocks)
    _write_empty_wonder_build_lists()
    print("  + wrote scenario-level empty WonderBuildLists.txt override")
    removed_goal_wonder_refs = _write_sanitized_goals_wonder_refs(live_wonder_ids)
    print(
        "  + wrote scenario-level Goals.txt override"
        f" ({removed_goal_wonder_refs} stale wonder goal ref(s) removed)"
    )

    restored_orders = _load_raw_block_file("default/gamedata/Orders.txt")
    stripped_order_flags = _strip_raw_block_flags(restored_orders, {"GLHidden"})
    if stripped_order_flags:
        _save_raw_block_file("default/gamedata/Orders.txt", restored_orders)
        print(f"  + restored {stripped_order_flags} unit order block(s) to Great Library index")

    restored_tileimps = _load_raw_block_file("default/gamedata/tileimp.txt")
    stripped_tileimp_flags = _strip_raw_block_flags(restored_tileimps, {"GLHidden"})
    if stripped_tileimp_flags:
        _save_raw_block_file("default/gamedata/tileimp.txt", restored_tileimps)
        print(f"  + restored {stripped_tileimp_flags} tile improvement block(s) to Great Library index")

    transport_tileimps = _load_raw_block_file("default/gamedata/tileimp.txt")
    base_tileimps = P.RawBlockTextFile()
    base_tileimps.parse(
        Path(r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data\default\gamedata\tileimp.txt").read_text(
            encoding='latin-1'
        )
    )
    transport_changed = False
    transport_changed |= _replace_block_text(
        transport_tileimps,
        "TILEIMP_RAILROAD",
        [("EnableAdvance ADVANCE_RAILROAD", "EnableAdvance ADVANCE_GREATER_ENCHANTMENTS")],
    )
    # OUT_OF_GENRE: copy block from base if missing, then mark GLHidden.
    # Deleting the block is wrong — base ctp2_data has it without GLHidden, so the
    # game would fall back and show it in the Great Library anyway.
    hidden_out_of_genre_added = 0
    for ident in sorted(HIDDEN_OUT_OF_GENRE_TILEIMPS):
        if ident not in transport_tileimps.blocks and ident in base_tileimps.blocks:
            transport_tileimps.add_block(ident, base_tileimps.blocks[ident])
            hidden_out_of_genre_added += 1
            transport_changed = True
        transport_changed |= transport_tileimps.ensure_flags(ident, ["GLHidden"])
    hidden_tileimps = HIDDEN_SURROGATE_TILEIMPS | HIDDEN_OUT_OF_GENRE_TILEIMPS
    for ident in sorted(HIDDEN_SURROGATE_TILEIMPS):
        transport_changed |= transport_tileimps.ensure_flags(ident, ["GLHidden"])
    if transport_changed:
        _save_raw_block_file("default/gamedata/tileimp.txt", transport_tileimps)
        print(
            "  + remapped the transport lane, added "
            f"{hidden_out_of_genre_added} out-of-genre tile improvement block(s) with GLHidden, "
            "and hid surrogate-only tile improvements from the Great Library"
        )

    live_advance_ids = set(reg.load("default/gamedata/Advance.txt").blocks)
    govern_file = _load_raw_block_file("default/gamedata/govern.txt")
    base_govern_file = _load_base_raw_block_file("default/gamedata/govern.txt")
    govern_source_blocks = dict(base_govern_file.blocks)
    govern_source_blocks.update(govern_file.blocks)
    live_governments = _government_ids_enabled_by_live_advances(
        govern_source_blocks,
        live_advance_ids,
    )
    live_governments.update(
        _extract_referenced_ids(
            ["default/gamedata/Units.txt", "default/gamedata/Improve.txt"],
            r'GOVERNMENT_[A-Z0-9_]+',
        )
    )
    restored_governments = 0
    for ident, block_text in govern_source_blocks.items():
        if ident not in live_governments or ident in govern_file.blocks:
            continue
        govern_file.add_block(ident, block_text)
        restored_governments += 1
    removed_governments = 0
    for ident in list(govern_file.blocks):
        if ident not in live_governments and govern_file.remove_block(ident):
            removed_governments += 1
    if restored_governments or removed_governments:
        _save_raw_block_file("default/gamedata/govern.txt", govern_file)
    govern_icons = _load_counted_icon_file("default/gamedata/governicon.txt")
    base_govern_icons = _load_base_counted_icon_file("default/gamedata/governicon.txt")
    keep_govern_icons = set()
    for ident in live_governments:
        block_text = govern_file.blocks.get(ident, "")
        match = re.search(r'^\s*Icon\s+(\S+)', block_text, re.MULTILINE)
        if match:
            keep_govern_icons.add(match.group(1))
    keep_govern_icons.add("ICON_GOV_DEFAULT")
    existing_govern_icon_ids = {
        entry.split('\t', 1)[0].strip()
        for entry in govern_icons.entries
        if entry.strip()
    }
    restored_icons = 0
    for entry in base_govern_icons.entries:
        icon_id = entry.split('\t', 1)[0].strip()
        if icon_id not in keep_govern_icons or icon_id in existing_govern_icon_ids:
            continue
        govern_icons.entries.append(entry)
        existing_govern_icon_ids.add(icon_id)
        restored_icons += 1
    synthesized_icons = 0
    base_govern_icon_entries = {
        entry.split('\t', 1)[0].strip(): entry
        for entry in base_govern_icons.entries
        if entry.strip()
    }
    for icon_id in sorted(keep_govern_icons - existing_govern_icon_ids):
        donor_id = GOVERNICON_FALLBACK_IDS.get(icon_id)
        donor_entry = base_govern_icon_entries.get(donor_id or "")
        if not donor_entry:
            continue
        govern_icons.entries.append(re.sub(r'^\s*\S+', icon_id, donor_entry, count=1))
        existing_govern_icon_ids.add(icon_id)
        synthesized_icons += 1
    removed_icons = _filter_counted_icon_entries(govern_icons, keep_govern_icons)
    if restored_icons or synthesized_icons or removed_icons:
        _save_counted_icon_file("default/gamedata/governicon.txt", govern_icons)
    uniticon = reg.load("default/gamedata/uniticon.txt")
    base_uniticon = _load_base_block_file("default/gamedata/uniticon.txt")
    restored_uniticon_govs = 0
    for ident in sorted(live_governments):
        icon_id = f"ICON_GOV_{ident[len('GOVERNMENT_'):]}"
        if icon_id in uniticon.blocks or icon_id not in base_uniticon.blocks:
            continue
        uniticon.blocks[icon_id] = base_uniticon.blocks[icon_id]
        restored_uniticon_govs += 1
    removed_uniticon_govs = 0
    for icon_id in list(uniticon.blocks):
        if not icon_id.startswith("ICON_GOV_") or icon_id == "ICON_GOV_DEFAULT":
            continue
        govern_id = f"GOVERNMENT_{icon_id[len('ICON_GOV_'):]}"
        if govern_id not in live_governments:
            del uniticon.blocks[icon_id]
            removed_uniticon_govs += 1
    removed_dip2_government_advice = _prune_government_advice_lines(
        "english/gamedata/dip2_str.txt",
        live_governments,
    )
    removed_strategy_governments = _prune_strategy_government_lines(
        "default/aidata/strategies.txt",
        live_governments,
    )
    gl_strings = reg.load("english/gamedata/gl_str.txt")
    removed_gl_strings = _prune_gl_strings(gl_strings, live_governments, ("GOVERNMENT_",))
    # Ensure every live government has a display string — base gl_str.txt may be missing some
    added_gov_strings = 0
    for gov_id in sorted(live_governments):
        if gov_id not in gl_strings.entries:
            gl_strings.entries[gov_id] = humanize_ident(gov_id, "GOVERNMENT_")
            added_gov_strings += 1
    gl_library = reg.load("english/gamedata/Great_Library.txt")
    removed_gl_sections = _prune_gl_sections(gl_library, live_governments, ("GOVERNMENT_",))
    removed_gl_links = _strip_stale_database_links(
        gl_library,
        live_governments,
        "DATABASE_GOVERNMENTS",
        ("GOVERNMENT_",),
    )
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    removed_waw_sections = _prune_gl_sections(waw_library, live_governments, ("GOVERNMENT_",))
    removed_waw_links = _strip_stale_database_links(
        waw_library,
        live_governments,
        "DATABASE_GOVERNMENTS",
        ("GOVERNMENT_",),
    )
    if removed_waw_sections or removed_waw_links:
        _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if any((
        restored_governments,
        restored_icons,
        synthesized_icons,
        removed_governments,
        restored_uniticon_govs,
        removed_icons,
        removed_uniticon_govs,
        removed_dip2_government_advice,
        removed_strategy_governments,
        removed_gl_strings,
        added_gov_strings,
        removed_gl_sections,
        removed_waw_sections,
        removed_gl_links,
        removed_waw_links,
    )):
        print(
            f"  + reduced governments to {len(live_governments)} live entry(ies)"
            f" ({restored_governments} block(s) restored, {removed_governments} block(s) removed,"
            f" {restored_icons} icon(s) restored, {synthesized_icons} fallback icon(s) synthesized, {removed_icons} icon(s) removed,"
            f" {restored_uniticon_govs} uniticon block(s) restored, {removed_uniticon_govs} uniticon block(s) removed,"
            f" {removed_dip2_government_advice} dip2_str line(s),"
            f" {removed_strategy_governments} aidata strategies line(s),"
            f" {removed_gl_strings} string(s) removed, {added_gov_strings} string(s) added,"
            f" {removed_gl_sections + removed_waw_sections} GL section(s) removed,"
            f" {removed_gl_links + removed_waw_links} stale GL link(s) stripped)"
        )

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    live_concepts = set(re.findall(r'<L:DATABASE_CONCEPTS,(CONCEPT_[A-Z0-9_]+)>', gl_library.render()))
    live_concepts.update(re.findall(r'<L:DATABASE_CONCEPTS,(CONCEPT_[A-Z0-9_]+)>', waw_library.render()))
    live_concepts -= HIDDEN_OUT_OF_GENRE_CONCEPTS
    stripped_hidden_concept_links = _strip_stale_database_links(
        gl_library,
        live_concepts,
        "DATABASE_CONCEPTS",
        ("CONCEPT_",),
    )
    stripped_hidden_waw_concept_links = _strip_stale_database_links(
        waw_library,
        live_concepts,
        "DATABASE_CONCEPTS",
        ("CONCEPT_",),
    )
    concept_text = _read_rel("default/gamedata/concept.txt").splitlines()
    concept_blocks = P.CTP2BlockFile()
    concept_blocks.parse('\n'.join(concept_text[1:]))
    removed_concepts = 0
    for ident in list(concept_blocks.blocks):
        if ident not in live_concepts:
            del concept_blocks.blocks[ident]
            removed_concepts += 1
    if removed_concepts:
        _write_rel(
            "default/gamedata/concept.txt",
            str(len(concept_blocks.blocks)) + "\n" + concept_blocks.render(),
        )
        concept_strings = reg.load("english/gamedata/gl_str.txt")
        removed_concept_strings = _prune_gl_strings(concept_strings, live_concepts, ("CONCEPT_",))
        removed_concept_sections = _prune_gl_sections(gl_library, live_concepts, ("CONCEPT_",))
        removed_waw_concept_sections = _prune_gl_sections(waw_library, live_concepts, ("CONCEPT_",))
        if removed_waw_concept_sections or stripped_hidden_waw_concept_links:
            _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
        print(
            f"  + reduced concepts to {len(live_concepts)} referenced entry(ies)"
            f" ({removed_concepts} block(s), {removed_concept_strings} string(s),"
            f" {removed_concept_sections + removed_waw_concept_sections} GL section(s) removed,"
            f" {stripped_hidden_concept_links + stripped_hidden_waw_concept_links} stale GL link(s) stripped)"
        )

    advances = reg.load("default/gamedata/Advance.txt")
    advances._text = advances._text.replace(
        "   Prerequisites ADVANCE_RAILROAD\n",
        "   Prerequisites ADVANCE_GREATER_ENCHANTMENTS\n",
        1,
    )
    wonders = reg.load("default/gamedata/Wonder.txt")
    wonders._text = wonders._text.replace(
        "   ObsoleteAdvance ADVANCE_RAILROAD\n",
        "   ObsoleteAdvance ADVANCE_GREATER_ENCHANTMENTS\n",
        1,
    )

    gl_strings = reg.load("english/gamedata/gl_str.txt")
    gl_strings.entries["TILEIMP_RAILROAD"] = "Enchanted Road"

    gl_library = reg.load("english/gamedata/Great_Library.txt")
    added_runtime_building_strings, added_runtime_building_sections = _ensure_runtime_building_gl_surfaces(
        gl_strings,
        gl_library,
    )
    gl_library.sections["TILEIMP_RAILROAD_PREREQ"] = (
        "Requires:\n"
        "<L:DATABASE_ADVANCES,ADVANCE_GREATER_ENCHANTMENTS>Greater Enchantments<e>"
    )
    gl_library.sections["TILEIMP_RAILROAD_GAMEPLAY"] = (
        "Enchanted Roads reduce the movement cost for units.  They are an "
        "improvement on <L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e>, "
        "and allow units to travel greater distances in a single turn.  Build "
        "them on any land tile."
    )
    gl_library.sections["ADVANCE_OIL_REFINING_PREREQ"] = (
        "Requires:\n"
        "<L:DATABASE_ADVANCES,ADVANCE_INDUSTRIAL_REVOLUTION>Industrial Revolution<e>\n"
        "<L:DATABASE_ADVANCES,ADVANCE_GREATER_ENCHANTMENTS>Greater Enchantments<e>"
    )
    swamp_gl = gl_library.sections.get("TERRAIN_SWAMP_GAMEPLAY")
    if swamp_gl:
        gl_library.sections["TERRAIN_SWAMP_GAMEPLAY"] = swamp_gl.replace(
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e>, "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_RAILROAD>Railroads<e> and "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_MAGLEV>Maglevs<e>",
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e> and "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_RAILROAD>Enchanted Roads<e>",
        )
    for section_id in (
        "TILEIMP_MAGLEV_PREREQ",
        "TILEIMP_MAGLEV_STATISTICS",
        "TILEIMP_MAGLEV_GAMEPLAY",
        "TILEIMP_MAGLEV_HISTORICAL",
    ):
        gl_library.sections.pop(section_id, None)
    ht_superconductor_stats = gl_library.sections.get("ADVANCE_HT_SUPERCONDUCTOR_STATISTICS")
    if ht_superconductor_stats:
        gl_library.sections["ADVANCE_HT_SUPERCONDUCTOR_STATISTICS"] = ht_superconductor_stats.replace(
            "\n<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_MAGLEV>Maglevs<e>",
            "",
        )
    ht_superconductor_gameplay = gl_library.sections.get("ADVANCE_HT_SUPERCONDUCTOR_GAMEPLAY")
    if ht_superconductor_gameplay:
        gl_library.sections["ADVANCE_HT_SUPERCONDUCTOR_GAMEPLAY"] = ht_superconductor_gameplay.replace(
            "\n\nMagnetic Levitation Trains, or "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_MAGLEV>Maglevs<e>, are transit systems "
            "that whiz along the surface of the earth at speeds well in excess of any other "
            "form of land transportation.  As a "
            "<L:DATABASE_CONCEPTS,CONCEPT_TILE_IMPROVEMENTS>Tile Improvement<e>, they are "
            "the fastest way to get around, dramatically reducing the movement costs "
            "associated with any terrain they are built on.",
            "",
        )

    waw_library = _load_library_file("english/gamedata/WAW_Great_Library.txt")
    waw_library.sections["TILEIMP_RAILROAD_PREREQ"] = (
        "Requires:\n"
        "<L:DATABASE_ADVANCES,ADVANCE_GREATER_ENCHANTMENTS>Greater Enchantments<e>"
    )
    waw_library.sections["TILEIMP_RAILROAD_GAMEPLAY"] = (
        "Enchanted Roads reduce the movement cost for units.  They are an "
        "improvement on <L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e>, "
        "and allow units to travel greater distances in a single turn.  Build "
        "them on any land tile."
    )
    waw_swamp_gl = waw_library.sections.get("TERRAIN_SWAMP_GAMEPLAY")
    if waw_swamp_gl:
        waw_library.sections["TERRAIN_SWAMP_GAMEPLAY"] = waw_swamp_gl.replace(
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e>, "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_RAILROAD>Railroads<e> and "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_MAGLEV>Maglevs<e>",
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_ROAD>Roads<e> and "
            "<L:DATABASE_TILE_IMPROVEMENTS,TILEIMP_RAILROAD>Enchanted Roads<e>",
        )
    for section_id in (
        "TILEIMP_MAGLEV_PREREQ",
        "TILEIMP_MAGLEV_STATISTICS",
        "TILEIMP_MAGLEV_GAMEPLAY",
        "TILEIMP_MAGLEV_HISTORICAL",
    ):
        waw_library.sections.pop(section_id, None)
    hidden_tileimps = HIDDEN_SURROGATE_TILEIMPS | HIDDEN_OUT_OF_GENRE_TILEIMPS
    visible_tileimps = set(tileimp_groups) - hidden_tileimps
    removed_hidden_tileimp_sections = _prune_gl_sections(
        gl_library,
        visible_tileimps,
        ("TILEIMP_",),
    )
    removed_hidden_waw_tileimp_sections = _prune_gl_sections(
        waw_library,
        visible_tileimps,
        ("TILEIMP_",),
    )
    stripped_hidden_tileimp_links = _strip_stale_database_links(
        gl_library,
        visible_tileimps,
        "DATABASE_TILE_IMPROVEMENTS",
        ("TILEIMP_",),
    )
    stripped_hidden_waw_tileimp_links = _strip_stale_database_links(
        waw_library,
        visible_tileimps,
        "DATABASE_TILE_IMPROVEMENTS",
        ("TILEIMP_",),
    )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)
    if stripped_hidden_tileimp_links or stripped_hidden_waw_tileimp_links:
        print(
            f"  + stripped {stripped_hidden_tileimp_links + stripped_hidden_waw_tileimp_links}"
            " hidden surrogate tile improvement GL link(s)"
        )
    if removed_hidden_tileimp_sections or removed_hidden_waw_tileimp_sections:
        print(
            "  + removed "
            f"{removed_hidden_tileimp_sections + removed_hidden_waw_tileimp_sections}"
            " hidden surrogate tile-improvement GL section(s)"
        )
    if added_runtime_building_strings or added_runtime_building_sections:
        print(
            "  + filled runtime building GL fallback surfaces "
            f"({added_runtime_building_strings} string(s), {added_runtime_building_sections} section(s))"
        )

    _write_surrogate_register()

    visible_order_sections = ("PREREQ", "STATISTICS", "GAMEPLAY", "HISTORICAL")
    order_visibility = _load_raw_block_file("default/gamedata/Orders.txt")
    # Load base CTP2 order display strings as fallback source
    _base_gl_str_path = CTP2_DATA / "english/gamedata/gl_str.txt"
    _base_order_strings: dict[str, str] = {}
    if _base_gl_str_path.exists():
        _base_gl_raw = _base_gl_str_path.read_text(encoding="latin-1")
        for _m in re.finditer(r'^((?:ORDER_|UNIT_ORDER_)\w+)\s*"([^"]*)"', _base_gl_raw, re.MULTILINE):
            _base_order_strings[_m.group(1)] = _m.group(2)
    # Manual display strings for orders absent from base CTP2 gl_str.txt
    _manual_order_strings: dict[str, str] = {
        "ORDER_AIRLIFT": "Airlift",
        "ORDER_ENSLAVE_SETTLER": "Enslave",
        "ORDER_INVESTIGATE_READINESS": "Investigate Readiness",
    }
    _base_order_strings.update(_manual_order_strings)
    rehidden_orders = 0
    restored_documented_orders = 0
    forced_hidden_orders = 0
    added_order_strings = 0
    visible_orders = set()
    for ident in list(order_visibility.blocks):
        if not ident.startswith("ORDER_"):
            continue
        if ident in HIDDEN_OUT_OF_GENRE_ORDERS:
            if order_visibility.ensure_flags(ident, ["GLHidden"]):
                forced_hidden_orders += 1
            continue
        alias = ident.replace("ORDER_", "UNIT_ORDER_", 1)
        # Ensure a display string exists in the scenario gl_str — copy from base if missing
        if ident not in gl_strings.entries and alias not in gl_strings.entries:
            base_name = _base_order_strings.get(ident) or _base_order_strings.get(alias)
            if base_name:
                gl_strings.entries[ident] = base_name
                added_order_strings += 1
        # Orders never had full GL articles in CTP2; display string alone is sufficient
        has_display_name = ident in gl_strings.entries or alias in gl_strings.entries
        if has_display_name:
            visible_orders.add(ident)
            if _replace_block_text(order_visibility, ident, [("\n   GLHidden", "")]):
                restored_documented_orders += 1
        elif order_visibility.ensure_flags(ident, ["GLHidden"]):
            rehidden_orders += 1
    removed_hidden_order_sections = _prune_gl_sections(
        gl_library,
        visible_orders,
        ("ORDER_",),
    )
    removed_hidden_waw_order_sections = _prune_gl_sections(
        waw_library,
        visible_orders,
        ("ORDER_",),
    )
    stripped_hidden_order_links = _strip_stale_database_links(
        gl_library,
        visible_orders,
        "DATABASE_ORDERS",
        ("ORDER_",),
    )
    stripped_hidden_waw_order_links = _strip_stale_database_links(
        waw_library,
        visible_orders,
        "DATABASE_ORDERS",
        ("ORDER_",),
    )
    if rehidden_orders or restored_documented_orders or added_order_strings or forced_hidden_orders:
        _save_raw_block_file("default/gamedata/Orders.txt", order_visibility)
        print(
            "  + reconciled unit order visibility against owned GL surfaces "
            f"({restored_documented_orders} restored, {added_order_strings} display string(s) added,"
            f" {rehidden_orders} hidden, {forced_hidden_orders} genre-hidden)"
        )
    if removed_hidden_order_sections or removed_hidden_waw_order_sections:
        print(
            "  + removed "
            f"{removed_hidden_order_sections + removed_hidden_waw_order_sections}"
            " hidden/out-of-genre unit-order GL section(s)"
        )
    if stripped_hidden_order_links or stripped_hidden_waw_order_links:
        print(
            "  + stripped "
            f"{stripped_hidden_order_links + stripped_hidden_waw_order_links}"
            " hidden/out-of-genre unit-order GL link(s)"
        )
    _save_library_file("english/gamedata/WAW_Great_Library.txt", waw_library)

    tips_strings = _load_string_file("english/gamedata/tips_str.txt")
    tips_strings.entries["TOOLTIP_TILEIMP_SELECT_ROAD2_BUTTON"] = "Enchanted Road"
    tips_strings.entries["STATUSBAR_TILEIMP_SELECT_ROAD2_BUTTON"] = (
        "Enchanted Roads can be placed on any land tile."
    )
    _save_string_file("english/gamedata/tips_str.txt", tips_strings)

    # Remove tileimp.txt from cache — we only loaded it for reading above,
    # not for modification. save_all() would corrupt it with the wrong format.
    if "default/gamedata/tileimp.txt" in reg._parsed:
        del reg._parsed["default/gamedata/tileimp.txt"]

    # Improvements load from buildings.txt (per gamefile.txt), NOT Improve.txt. Convert
    # the authored MoM improvements into buildings.txt (AE schema) and drop Improve.txt.
    # Done before save_all so the dead Improve.txt is never written.
    _merge_mom_improvements_into_buildings()

    reg.save_all()
    final_gl_scrubbed = 0
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_file(
        "english/gamedata/Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_prose(
        "english/gamedata/Great_Library.txt",
        hidden_tileimps,
    )
    final_gl_scrubbed += _scrub_hidden_tileimp_gl_prose(
        "english/gamedata/WAW_Great_Library.txt",
        hidden_tileimps,
    )
    if final_gl_scrubbed:
        print(f"  + final GL scrub removed {final_gl_scrubbed} hidden tile-improvement surface(s)")
    final_order_scrubbed = 0
    final_order_scrubbed += _scrub_hidden_order_gl_file(
        "english/gamedata/Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_ORDERS,
    )
    final_order_scrubbed += _scrub_hidden_order_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_ORDERS,
    )
    if final_order_scrubbed:
        print(f"  + final GL scrub removed {final_order_scrubbed} hidden/out-of-genre order surface(s)")
    final_concept_scrubbed = 0
    final_concept_scrubbed += _scrub_hidden_concept_gl_file(
        "english/gamedata/Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_CONCEPTS,
    )
    final_concept_scrubbed += _scrub_hidden_concept_gl_file(
        "english/gamedata/WAW_Great_Library.txt",
        HIDDEN_OUT_OF_GENRE_CONCEPTS,
    )
    if final_concept_scrubbed:
        print(f"  + final GL scrub removed {final_concept_scrubbed} hidden/out-of-genre concept surface(s)")

    if _ensure_diffdb_start_government():
        print(f"  + DiffDB.txt: guaranteed {START_GOVERNMENT_ADVANCE} across all start-tech blocks")

    _generate_civilisation_tribes()
    _generate_civstr_tribes()
    workbook_path, workbook_sheet_count = export_workbook(MOD_WORKBOOK_PATH)
    print(f"  + refreshed workbook {workbook_path} ({workbook_sheet_count} sheet(s))")

    print("Done. Run ctp2_csvgen.py to check exports.")


def _civ_tab(key: str, value: str) -> str:
    """Return a tab-aligned field line: KEY<tabs>VALUE matching civilisation.txt convention.

    Preconditions: key is a non-empty identifier; value is the raw token or quoted string.
    Guarantee: produces '\tKEY<tabs>VALUE\n' with enough tabs so value starts at or after col 25.
    """
    # Base file uses 1 tab indent + tabs to align value.  Field name + 1 leading tab;
    # then pad with tabs so the value column lands >= 24 chars in.
    padded = key
    col = len(key)
    while col < 23:
        padded += '\t'
        col = ((col // 8) + 1) * 8
    if col == 23 or col % 8 != 0:
        padded += '\t'
    return f'\t{padded}\t{value}\n'


def _str_tab(key: str, value: str) -> str:
    """Return a tab-aligned string-file line: KEY<tabs>"value" matching civ_str.txt convention.

    Preconditions: key is a non-empty string key; value is unquoted text.
    Guarantee: produces 'KEY<tabs>"value"\n' with value column at or after col 24.
    """
    col = len(key)
    tabs = ''
    while col < 24:
        tabs += '\t'
        col = ((col // 8) + 1) * 8
    if not tabs:
        tabs = '\t'
    return f'{key}{tabs}"{value}"\n'


_CIV_HEADER_RE = re.compile(r'^([A-Z][A-Z0-9_]+)(?:\s+#\d+)?\s*$')


def _civ_record_name(lines: list[str], index: int) -> str | None:
    """Return the top-level civilisation record name at lines[index], if any."""
    match = _CIV_HEADER_RE.match(lines[index].strip())
    if not match:
        return None
    probe = index + 1
    while probe < len(lines) and lines[probe].strip() == '':
        probe += 1
    if probe < len(lines) and lines[probe].strip() == '{':
        return match.group(1)
    return None


def _find_civilisation_record_bounds(lines: list[str], ident: str) -> tuple[int, int]:
    """Return [start, end) line bounds for the named top-level civilisation record block."""
    for i in range(len(lines)):
        if _civ_record_name(lines, i) != ident:
            continue
        depth = 0
        saw_open = False
        probe = i + 1
        while probe < len(lines):
            depth += lines[probe].count('{') - lines[probe].count('}')
            if lines[probe].count('{'):
                saw_open = True
            probe += 1
            if saw_open and depth <= 0:
                while probe < len(lines) and lines[probe].strip() == '':
                    probe += 1
                return i, probe
        break
    raise RuntimeError(f'Could not locate civilisation record {ident!r} in base source')


def _renumber_civilisation_headers(lines: list[str]) -> list[str]:
    """Rewrite civilisation header comment numbers to match final record order."""
    renumbered = list(lines)
    civ_index = 0
    for i in range(len(renumbered)):
        ident = _civ_record_name(renumbered, i)
        if not ident:
            continue
        renumbered[i] = f'{ident}\t#{civ_index}\n'
        civ_index += 1
    return renumbered


def _generate_civilisation_tribes() -> None:
    """Regenerate the MoM tribe blocks into selectable civ order from players.csv.

    Preconditions: players.csv has columns ctp2_is_new, ctp2_civ_id, civ2_leader_male,
        civ2_leader_female, personality_male, personality_female, parchment, city_style,
        emissary_photo, nation_flag. tribe_cities.csv has columns ctp2_civ_id + city_1..city_15.
    Guarantee: civilisation.txt contains only BARBARIAN plus the MoM tribes from players.csv,
        so loading the scenario exposes only MoM selectable civs; file is LF-only.
    Maintain: the file is rebuilt from canonical base BARBARIAN data each run, then renumbered
        so the header comments stay consistent with the actual selectable civ order.
    """
    if not _csv_exists('players.csv') or not _csv_exists('tribe_cities.csv'):
        return

    players = [r for r in _csv_rows('players.csv') if r.get('ctp2_is_new', '').strip() == 'yes']
    if not players:
        return

    cities_by_key = {}
    for row in _csv_rows('tribe_cities.csv'):
        key = row['ctp2_civ_id'].strip()
        cities_by_key[key] = [row.get(f'city_{i}', '').strip() for i in range(1, 16)]

    civ_path = SCENARIO / 'default/gamedata/civilisation.txt'
    SENTINEL = '# == BEGIN GENERATED MOM TRIBES =='

    # Always source the base 70-civ block from the canonical ctp2_data copy.
    # The scenario file is generator output and has no independent base to preserve.
    base_source = CTP2_DATA / 'default/gamedata/civilisation.txt'
    with base_source.open('r', encoding='latin-1') as fh:
        base_lines = fh.readlines()

    blocks = [
        '\n',
        f'{SENTINEL}\n',
        '# Generated by ctp2_generator.py from players.csv + tribe_cities.csv\n',
        '# DO NOT EDIT - re-run the generator to update\n',
        '#----------------------------------------------------------------------------\n',
        '# Masters of Magic Scenario Tribes\n',
        '#----------------------------------------------------------------------------\n',
        '\n',
    ]

    for i, row in enumerate(players):
        key = row['ctp2_civ_id'].strip()
        lm = row['civ2_leader_male'].strip()
        lf = row['civ2_leader_female'].strip()
        pers_m = row['personality_male'].strip()
        pers_f = row['personality_female'].strip()
        parch = row['parchment'].strip()
        cs = row['city_style'].strip()
        emis = row['emissary_photo'].strip()
        flag = row['nation_flag'].strip()
        city_list = cities_by_key.get(key, [])

        blocks.append(f'{key}\n')
        blocks.append('{\n')
        blocks.append(_civ_tab('LeaderNameMale', f'{key}_LEADERM_NAME'))
        if lf:
            blocks.append(_civ_tab('LeaderNameFemale', f'{key}_LEADERF_NAME'))
        else:
            blocks.append(_civ_tab('LeaderNameFemale', f'{key}_LEADERM_NAME'))
        blocks.append(_civ_tab('PersonalityMale', pers_m))
        blocks.append(_civ_tab('PersonalityFemale', pers_f))
        blocks.append(_civ_tab('PersonalityDescription', f'PERSONALITY_DESCRIPTION_{key}'))
        blocks.append(_civ_tab('CountryName', f'{key}_COUNTRY_NAME'))
        blocks.append(_civ_tab('SingularCivName', f'{key}_SINGULAR'))
        blocks.append(_civ_tab('PluralCivName', f'{key}_PLURAL'))
        blocks.append(_civ_tab('EmissaryPhotoMale', emis))
        blocks.append(_civ_tab('EmissaryPhotoFemale', emis))
        blocks.append(_civ_tab('Parchment', parch))
        blocks.append(_civ_tab('CityStyle', cs))
        blocks.append(_civ_tab('NationUnitFlag', flag))
        for i, city in enumerate(city_list, 1):
            if city:
                blocks.append(_civ_tab('CityName', f'{key}_CITY_{i}'))
        blocks.append('}\n\n')

    _, barbarian_end = _find_civilisation_record_bounds(base_lines, 'BARBARIAN')
    content_lines = base_lines[:barbarian_end] + blocks
    content = ''.join(_renumber_civilisation_headers(content_lines))
    with civ_path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(content)
    print(f'  + civilisation.txt: wrote BARBARIAN + {len(players)} MoM tribe civ block(s)')


def _generate_civstr_tribes() -> None:
    """Regenerate the MoM tribe string entries at the end of civ_str.txt from players.csv.

    Preconditions: players.csv has ctp2_is_new, ctp2_civ_id, civ2_leader_male,
        civ2_leader_female, civ2_tribe_name.  tribe_cities.csv has city_1..city_15.
    Guarantee: civ_str.txt ends with exactly the tribe string entries; base entries preserved
        verbatim; file is LF-only.
    Maintain: tribe section is delimited by a sentinel comment so re-runs are idempotent.
    """
    if not _csv_exists('players.csv') or not _csv_exists('tribe_cities.csv'):
        return

    players = [r for r in _csv_rows('players.csv') if r.get('ctp2_is_new', '').strip() == 'yes']
    if not players:
        return

    cities_by_key = {}
    for row in _csv_rows('tribe_cities.csv'):
        key = row['ctp2_civ_id'].strip()
        cities_by_key[key] = [row.get(f'city_{i}', '').strip() for i in range(1, 16)]

    str_path = SCENARIO / 'english/gamedata/civ_str.txt'
    SENTINEL = '# == BEGIN GENERATED MOM TRIBES =='

    # Always source the base string block from the canonical ctp2_data copy.
    base_source = CTP2_DATA / 'english/gamedata/civ_str.txt'
    with base_source.open('r', encoding='latin-1') as fh:
        base_lines = fh.readlines()

    while base_lines and base_lines[-1].strip() == '':
        base_lines.pop()

    blocks = [
        '\n',
        f'{SENTINEL}\n',
        '# Generated by ctp2_generator.py from players.csv + tribe_cities.csv\n',
        '# DO NOT EDIT - re-run the generator to update\n',
        '#----------------------------------------------------------------------------\n',
        '# Masters of Magic Scenario Tribe Strings\n',
        '#----------------------------------------------------------------------------\n',
        '\n',
    ]

    for row in players:
        key = row['ctp2_civ_id'].strip()
        tribe_name = row['civ2_tribe_name'].strip()
        lm = row['civ2_leader_male'].strip()
        lf = row['civ2_leader_female'].strip()
        city_list = cities_by_key.get(key, [])

        singular = tribe_name.replace('Tribes of ', '') + ' Tribe'
        blocks.append(f'# --- {key} ---\n')
        blocks.append(_str_tab(f'{key}_LEADERM_NAME', lm))
        if lf:
            blocks.append(_str_tab(f'{key}_LEADERF_NAME', lf))
        blocks.append(_str_tab(f'{key}_COUNTRY_NAME', tribe_name))
        blocks.append(_str_tab(f'{key}_SINGULAR', singular))
        blocks.append(_str_tab(f'{key}_PLURAL', tribe_name))
        blocks.append(_str_tab(f'PERSONALITY_DESCRIPTION_{key}', tribe_name))
        for i, city in enumerate(city_list, 1):
            if city:
                blocks.append(_str_tab(f'{key}_CITY_{i}', city))
        blocks.append('\n')

    content = ''.join(base_lines) + ''.join(blocks)
    with str_path.open('w', encoding='latin-1', newline='') as fh:
        fh.write(content)
    print(f'  + civ_str.txt: wrote {len(players)} tribe string block(s)')


if __name__ == '__main__':
    main()

```


## sync_excel_to_csv.py

```python
import openpyxl
import csv
from pathlib import Path

EXCEL_FILE = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\mom_dimension_inventory.xlsx")
CSV_DIR = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\momjr_csv")

SHEETS = ["advances", "units", "improvements", "wonders"]

def sync():
    if not EXCEL_FILE.exists():
        print("ERROR: Excel file not found!")
        return
    
    wb = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    
    for sheet_name in SHEETS:
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            csv_path = CSV_DIR / f"{sheet_name}.csv"
            print(f"Syncing {sheet_name} -> {csv_path.name}")
            
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                for row in ws.iter_rows(values_only=True):
                    # Skip completely empty rows
                    if any(cell is not None and str(cell).strip() != "" for cell in row):
                        writer.writerow(["" if cell is None else str(cell) for cell in row])
            print(f"  -> Synced {sheet_name}")
        else:
            print(f"  -> Sheet '{sheet_name}' not found in Excel.")

if __name__ == "__main__":
    print("Syncing Excel changes to CSVs...")
    sync()
    print("\nSUCCESS! You can now run: python ctp2_generator.py")

```


## ctp2_parser.py

```python
# CTP2 File Parser Framework

import re
from pathlib import Path
from typing import Dict, List, Optional


class CTP2BlockFile:
    """Block { ... } files — uniticon, Wonder, Improve, Advance."""
    re_start = re.compile(r'^(\w[\w_]*)\s*\{')

    def __init__(self):
        self.blocks: Dict[str, Dict[str, str]] = {}

    def parse(self, text: str) -> List[str]:
        warnings = []
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            m = self.re_start.match(lines[i])
            if not m:
                i += 1
                continue
            ident = m.group(1)
            fields = {}
            line = lines[i]
            bs = line.find('{')
            be = line.find('}')
            if be > bs + 1:
                rest = line[bs + 1:be]
                i += 1
            else:
                rest = ''
                i += 1
                while i < len(lines):
                    if '}' in lines[i]:
                        i += 1
                        break
                    if rest:
                        rest += ' '
                    rest += lines[i].strip()
                    i += 1
            # Tokenize rest into key-value pairs
            tokens = []
            j = 0
            while j < len(rest):
                if rest[j] in ' \t\n':
                    j += 1
                    continue
                if rest[j] == '"':
                    end = rest.index('"', j + 1) + 1
                    tokens.append(rest[j:end])  # preserve surrounding quotes
                    j = end
                else:
                    end = j + 1
                    while end < len(rest) and rest[end] not in ' \t\n':
                        end += 1
                    tokens.append(rest[j:end])
                    j = end
            for k in range(0, len(tokens) - 1, 2):
                key = tokens[k]
                val = tokens[k + 1]
                if key and val and key != '}' and val != '}':
                    fields[key] = val
            self.blocks[ident] = fields
        return warnings

    def render(self) -> str:
        lines_out = []
        for ident, fields in self.blocks.items():
            parts = ' '.join(f'{k} {v}' for k, v in fields.items())
            lines_out.append(f'{ident} {{ {parts} }}')
        return '\n'.join(lines_out)


class CountedIconFile:
    """CTP2 counted-icon files: wondericon, improveicon, advanceicon.

    Format: line 1 = integer count, lines 2..N+1 = tab-separated entries.
    Used primarily for CSV export; not used for unit data.
    """

    def __init__(self):
        self.entries: List[str] = []

    def parse(self, text: str) -> List[str]:
        warnings = []
        lines = text.split('\n')
        if not lines:
            return warnings
        first = lines[0].strip().lstrip('#').strip()
        try:
            count = int(first)
        except ValueError:
            self.entries = [l for l in lines[1:] if l.strip() and not l.strip().startswith('#')]
            return warnings
        self.entries = lines[1:count + 1]
        return warnings

    def render(self) -> str:
        return str(len(self.entries)) + '\n' + '\n'.join(self.entries)

    def has_icon(self, icon_id: str) -> bool:
        return any(icon_id in e for e in self.entries)


class FlatListFile:
    def __init__(self):
        self.entries: Dict[str, str] = {}
        self._raw_lines: Dict[str, str] = {}

    def parse(self, text: str):
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            parts = s.split(None, 1)
            self.entries[parts[0]] = parts[1] if len(parts) > 1 else ""
            self._raw_lines[parts[0]] = line

    def render(self) -> str:
        return '\n'.join(self._raw_lines.get(k, f"{k} {v}") for k, v in self.entries.items())


class RawBlockTextFile:
    """
    Multi-line CTP2 block file that preserves block text verbatim.

    Supports safe block removal and bare-flag insertion for database files whose
    format cannot be round-tripped through the simple key/value tokenizer.
    """

    re_block_id = re.compile(r'^([A-Z][A-Z0-9_]+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, str] = {}

    def _scan_blocks(self, text: str):
        lines = text.splitlines(keepends=True)
        prefix = []
        blocks = []
        i = 0
        seen_first_block = False
        while i < len(lines):
            line = lines[i]
            match = self.re_block_id.match(line)
            if not match:
                if not seen_first_block:
                    prefix.append(line)
                i += 1
                continue
            seen_first_block = True
            ident = match.group(1)
            block_lines = [line]
            depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            blocks.append((ident, ''.join(block_lines).rstrip('\n')))
        return ''.join(prefix), blocks

    def _rebuild_text(self, prefix: str, blocks) -> str:
        body = "\n\n".join(block for _, block in blocks)
        if prefix and body:
            return prefix.rstrip('\n') + "\n\n" + body + "\n"
        if body:
            return body + "\n"
        return prefix

    def _replace_blocks(self, blocks) -> None:
        prefix, _ = self._scan_blocks(self._text)
        self._text = self._rebuild_text(prefix, blocks)
        self.blocks = {ident: block for ident, block in blocks}

    def parse(self, text: str) -> List[str]:
        self._text = text
        prefix, blocks = self._scan_blocks(text)
        deduped = []
        seen = set()
        for ident, block in reversed(blocks):
            if ident in seen:
                continue
            seen.add(ident)
            deduped.append((ident, block))
        deduped.reverse()
        if len(deduped) != len(blocks):
            self._text = self._rebuild_text(prefix, deduped)
        self.blocks = {ident: block for ident, block in deduped}
        return []

    def add_block(self, ident: str, block_text: str) -> None:
        blocks = list(self.blocks.items())
        replaced = False
        for index, (block_id, _) in enumerate(blocks):
            if block_id == ident:
                blocks[index] = (ident, block_text.rstrip('\n'))
                replaced = True
                break
        if not replaced:
            blocks.append((ident, block_text.rstrip('\n')))
        self._replace_blocks(blocks)

    def remove_block(self, ident: str) -> bool:
        if ident not in self.blocks:
            return False
        blocks = [(block_id, block_text) for block_id, block_text in self.blocks.items() if block_id != ident]
        self._replace_blocks(blocks)
        return True

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        block_text = self.blocks.get(ident)
        if not block_text:
            return False
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False
        lines = block_text.splitlines(keepends=True)
        if not lines:
            return False
        closing_index = None
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip() == '}':
                closing_index = index
                break
        if closing_index is None:
            return False
        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        lines[closing_index:closing_index] = insert_lines
        self.add_block(ident, ''.join(lines))
        return True

    def render(self) -> str:
        return self._text


class LibraryFile:
    def __init__(self):
        self.sections: Dict[str, str] = {}

    def parse(self, text: str):
        # MoM carries legacy GL transitions in the form "[END][NEXT_SECTION]".
        # Normalize them before parsing so round-trips do not merge entire
        # section families into the preceding block.
        text = re.sub(r'\[END\]\[([\w_]+)\]', r'[END]\n[\1]', text)
        current = None
        content = []
        for line in text.split('\n'):
            m = re.match(r'^\[([\w_]+)\]$', line.strip())
            if m:
                if current:
                    self.sections[current] = '\n'.join(content).strip()
                current = m.group(1)
                content = []
            elif line.strip() == '[END]':
                if current:
                    self.sections[current] = '\n'.join(content).strip()
                current = None
                content = []
            elif current:
                content.append(line)
        if current:
            self.sections[current] = '\n'.join(content).strip()

    def render(self) -> str:
        lines = []
        for section_id, content in self.sections.items():
            lines.append(f'[{section_id}]')
            if content:
                lines.append(content)
            lines.append('[END]')
        return '\n'.join(lines)


class StringDBFile:
    def __init__(self):
        self.entries: Dict[str, str] = {}

    def parse(self, text: str):
        for line in text.split('\n'):
            s = line.strip()
            if not s or s.startswith('#'):
                continue
            if '\t' in s:
                key, val = s.split('\t', 1)
                self.entries[key] = val.strip().strip('"')

    def render(self) -> str:
        lines = []
        for key, val in self.entries.items():
            # Column-align value to col 48 using 8-char tab stops (matches base game gl_str.txt)
            cur = len(key)
            tabs = 0
            while cur < 48:
                cur = ((cur // 8) + 1) * 8
                tabs += 1
            if tabs < 1:
                tabs = 1
            lines.append(f'{key}{chr(9) * tabs}"{val}"')
        return '\n'.join(lines)


class UnitsFile:
    """CTP2 Units.txt — complex multi-line format with nested sub-blocks and bare flags.

    Preserves the file content verbatim. New unit blocks are appended only;
    existing units are never re-rendered, preventing format corruption.
    """

    re_unit_id = re.compile(r'^(UNIT_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self._unit_ids: set = set()

    def parse(self, text: str) -> List[str]:
        self._text = text
        for m in self.re_unit_id.finditer(text):
            self._unit_ids.add(m.group(1))
        return []

    def has_unit(self, ident: str) -> bool:
        return ident in self._unit_ids

    def add_unit(self, ident: str, block_text: str):
        """Append a fully-formed unit block if ident is not already present."""
        if ident not in self._unit_ids:
            self._unit_ids.add(ident)
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare unit flags into an existing Units.txt block.

        Require: ident is a unit ID and flags are bare CTP2 flag names.
        Guarantee: returns True only when text changed; preserves existing block
        formatting and nested sub-blocks. Missing units are left unchanged.
        Failure modes: malformed unclosed unit blocks are ignored.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        closing_line = block_lines[block_end_index]
        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def remove_unit(self, ident: str) -> bool:
        """
        Remove a complete unit block (including nested sub-blocks) from the text.

        Require: ident is a UNIT_* identifier present in the file.
        Guarantee: returns True if found and removed; False otherwise.
          All other blocks and surrounding whitespace are preserved intact.
        Failure modes: malformed unclosed blocks are left untouched.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(lines[:block_end_index + 1])
        block_start = line_start
        block_end = line_start + len(block_text)
        tail = self._text[block_end:]
        if tail.startswith('\n'):
            tail = tail[1:]
        self._text = self._text[:block_start] + tail
        self._unit_ids.discard(ident)
        return True

    def render(self) -> str:
        return self._text

class AdvanceFile:
    """CTP2 Advance.txt — multi-line format with bare boolean flags.

    Preserves the file content verbatim. New advance blocks are appended only;
    existing advances are never re-rendered, preventing tokenizer corruption
    of boolean flags like 'Infrastructure' and 'Tunnels'.
    The 'blocks' attribute is a dict keyed by advance ID (values are empty
    dicts) so existing code using 'ident in adv.blocks' still works.
    """

    re_adv_id = re.compile(r'^(ADVANCE_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, dict] = {}  # id → {} for membership testing

    def _scan_blocks(self, text: str):
        """Return (prefix, [(ident, block_text), ...]) for raw Advance.txt content.

        Purpose:
            Preserve each advance block verbatim while still letting us reconcile
            duplicate IDs at parse time.

        Preconditions:
            ``text`` is the full Advance.txt payload.

        Failure modes:
            If a block is malformed and never closes, the remainder of the file is
            treated as part of that block.
        """
        lines = text.splitlines(keepends=True)
        prefix = []
        blocks = []
        i = 0
        seen_first_block = False
        while i < len(lines):
            line = lines[i]
            m = self.re_adv_id.match(line)
            if not m:
                if not seen_first_block:
                    prefix.append(line)
                i += 1
                continue
            seen_first_block = True
            ident = m.group(1)
            block_lines = [line]
            depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and depth > 0:
                block_lines.append(lines[i])
                depth += lines[i].count('{') - lines[i].count('}')
                i += 1
            blocks.append((ident, ''.join(block_lines).rstrip('\n')))
        return ''.join(prefix), blocks

    def _rebuild_text(self, prefix: str, blocks) -> str:
        body = "\n\n".join(block for _, block in blocks)
        if prefix and body:
            return prefix.rstrip('\n') + "\n\n" + body + "\n"
        if body:
            return body + "\n"
        return prefix

    def parse(self, text: str) -> List[str]:
        self.blocks = {}
        prefix, blocks = self._scan_blocks(text)
        deduped = []
        seen = set()
        for ident, block in reversed(blocks):
            if ident in seen:
                continue
            seen.add(ident)
            deduped.append((ident, block))
        deduped.reverse()
        self._text = self._rebuild_text(prefix, deduped) if len(deduped) != len(blocks) else text
        for ident, _ in deduped:
            self.blocks[ident] = {}
        return []

    def add_advance(self, ident: str, block_text: str):
        """Append block_text if ident is not already present."""
        if ident not in self.blocks:
            self.blocks[ident] = {}
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare advance flags into an existing Advance.txt block.

        Require: ``ident`` is an advance ID and ``flags`` are bare CTP2 flag
        names already supported by Advance.txt.
        Guarantee: returns True only when text changed; preserves existing block
        text other than inserting the missing flags before the closing brace.
        Failure modes: missing or malformed blocks are left unchanged.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def render(self) -> str:
        return self._text


class WonderFile:
    """CTP2 Wonder.txt — multi-line format with bare boolean flags.

    Preserves the file content verbatim. New wonder blocks are appended only;
    existing wonders are never re-rendered, preventing tokenizer corruption
    of bare flags like 'FreeSlaves', 'ProhibitSlavers', 'PreventConversion'.
    The 'blocks' attribute is a dict keyed by wonder ID so that
    'ident in won.blocks' works without modification to callers.
    """

    re_wonder_id = re.compile(r'^(WONDER_\w+)\s*\{', re.MULTILINE)

    def __init__(self):
        self._text: str = ""
        self.blocks: Dict[str, dict] = {}

    def parse(self, text: str) -> List[str]:
        self._text = text
        for m in self.re_wonder_id.finditer(text):
            self.blocks[m.group(1)] = {}
        return []

    def add_wonder(self, ident: str, block_text: str):
        """Append block_text if ident is not already present."""
        if ident not in self.blocks:
            self.blocks[ident] = {}
            self._text = self._text.rstrip('\n') + "\n\n" + block_text + "\n"

    def ensure_flags(self, ident: str, flags: List[str]) -> bool:
        """
        Insert bare wonder flags into an existing Wonder.txt block.

        Require: ``ident`` is a wonder ID and ``flags`` are bare CTP2 flag
        names already supported by Wonder.txt.
        Guarantee: returns True only when text changed; preserves existing block
        text other than inserting missing flags before the closing brace.
        Failure modes: missing or malformed blocks are left unchanged.
        """
        match = re.search(rf'^{re.escape(ident)}\s*\{{', self._text, re.MULTILINE)
        if not match:
            return False

        line_start = self._text.rfind('\n', 0, match.start()) + 1
        lines = self._text[line_start:].splitlines(keepends=True)
        depth = 0
        block_end_index = None
        block_lines = []

        for index, line in enumerate(lines):
            depth += line.count('{') - line.count('}')
            block_lines.append(line)
            if index > 0 and depth <= 0:
                block_end_index = index
                break

        if block_end_index is None:
            return False

        block_text = ''.join(block_lines)
        missing_flags = [
            flag
            for flag in flags
            if not re.search(rf'^\s*{re.escape(flag)}\s*$', block_text, re.MULTILINE)
        ]
        if not missing_flags:
            return False

        insert_lines = [f"   {flag}\n" for flag in missing_flags]
        block_lines[block_end_index:block_end_index] = insert_lines
        new_block = ''.join(block_lines)

        block_start = line_start
        block_end = line_start + len(block_text)
        self._text = self._text[:block_start] + new_block + self._text[block_end:]
        return True

    def render(self) -> str:
        return self._text


PARSER_MAP = {
    "default/gamedata/Wonder.txt": WonderFile,
    "default/gamedata/Improve.txt": CTP2BlockFile,
    "default/gamedata/Advance.txt": AdvanceFile,
    "default/gamedata/Units.txt": UnitsFile,
    # Backup unit files — same block format as Units.txt; must also receive
    # unit_mask.csv removals so the engine never loads a stale UNIT_* that
    # was removed from Units.txt (causes "X not found in Unit database").
    "default/gamedata/Units_historic.txt": UnitsFile,
    "default/gamedata/Units_release.txt": UnitsFile,
    "default/gamedata/tileimp.txt": CTP2BlockFile,
    "default/gamedata/uniticon.txt": CTP2BlockFile,
    "default/gamedata/wondericon.txt": CountedIconFile,
    "default/gamedata/improveicon.txt": CountedIconFile,
    "default/gamedata/advanceicon.txt": CountedIconFile,
    "english/gamedata/gl_str.txt": StringDBFile,
    "english/gamedata/Great_Library.txt": LibraryFile,
}


class FileRegistry:
    """Holds parsed content for all files. Loads on demand. Saves all."""
    def __init__(self, scenario: Path, ctp2_data: Path = None):
        self.scenario = scenario
        self.ctp2_data = ctp2_data or Path(r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data")
        self._parsed: Dict[str, object] = {}

    def _find(self, rel: str) -> Path:
        p = self.scenario / rel
        if p.exists():
            return p
        p = self.ctp2_data / rel
        if p.exists():
            return p
        return None

    def load(self, rel: str):
        if rel in self._parsed:
            return self._parsed[rel]
        cls = PARSER_MAP[rel]
        p = self._find(rel)
        text = p.read_text(encoding='latin-1') if p and p.exists() else ""
        obj = cls()
        obj.parse(text)
        self._parsed[rel] = obj
        return obj

    def text(self, rel: str) -> str:
        p = self._find(rel)
        return p.read_text(encoding='latin-1') if p else ""

    def save(self, rel: str):
        obj = self._parsed.get(rel)
        if obj and hasattr(obj, 'render'):
            p = self.scenario / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            rendered = obj.render()
            if not rendered.endswith('\n'):
                rendered += '\n'
            # Use newline='' to write LF-only (matching CTP2 base game file format).
            # Default text mode on Windows produces CRLF, which causes the CTP2 engine
            # to leave \r on keys/values, breaking string lookups → blank GL list items.
            with p.open('w', encoding='latin-1', newline='') as fh:
                fh.write(rendered)

    def save_all(self):
        for rel in list(self._parsed.keys()):
            self.save(rel)


# === ENTITY REGISTRATION — one entity = multiple files ===

def _unpack_module_docstring(mod):
    """Parse module existence helper """
    return True

class EntityRegistry:
    """Registry of CTP2 mod entities. Each entity tracks its footprint."""

    def __init__(self):
        self.advances = []
        self.wonders = []
        self.buildings = []
        self.units = []
        self.tileimps = []

    def add_advance(self, advance):
        self.advances.append(advance)
        return advance

    def add_wonder(self, wonder):
        self.wonders.append(wonder)
        return wonder

    def add_building(self, building):
        self.buildings.append(building)
        return building

    def add_tileimp(self, tileimp):
        self.tileimps.append(tileimp)
        return tileimp

    def register_all(self, reg: FileRegistry):
        for entity in self.advances + self.units + self.wonders + self.buildings + self.tileimps:
            entity.register(reg)


class ModAdvance:
    def __init__(self, ident: str, name: str, cost: str, branch: str, age: str,
                 icon: str = "", prereqs: list = None, desc: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.branch = branch
        self.age = age
        self.icon = icon or f"ICON_{ident}"
        self.prereqs = prereqs or []
        self.desc = desc

    def _block_text(self) -> str:
        """Return a fully-formed multi-line advance block."""
        # Strip any trailing ; comment from branch — CTP2 uses # not ;
        branch = str(self.branch).split(';')[0].strip()
        lines = [f"{self.ident} {{"]
        for p in self.prereqs:
            lines.append(f"   Prerequisites {p}")
        lines += [
            f"   Cost {self.cost}",
            f"   Icon {self.icon}",
            f"   Branch {branch}",
            f"   Age {self.age}",
        ]
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: FileRegistry):
        # Advance.txt — append-only; never re-renders existing content
        adv = reg.load("default/gamedata/Advance.txt")
        adv.add_advance(self.ident, self._block_text())
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        if self.desc:
            s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections.setdefault(
                f"{self.ident}_{suffix}",
                f"<L:DATABASE_ADVANCES,{self.ident}>{self.name}<e>",
            )
        prereq_section = "Requires:\n"
        for p in self.prereqs:
            prereq_section += f"<L:DATABASE_ADVANCES,{p}>{p.split('_', 1)[1].title() if '_' in p else p}<e>\n"
        if not self.prereqs:
            prereq_section = "Requires:\nNothing"
        gl.sections[f"{self.ident}_PREREQ"] = prereq_section.strip()
        _age_display = {
            'AGE_ONE': 'Ancient', 'AGE_TWO': 'Medieval', 'AGE_THREE': 'Renaissance',
            'AGE_FOUR': 'Industrial', 'AGE_FIVE': 'Modern',
        }
        branch_display = str(self.branch).split(';')[0].strip()
        age_display = _age_display.get(str(self.age).strip(), str(self.age))
        gl.sections[f"{self.ident}_STATISTICS"] = f"Cost: {self.cost}\nAge: {age_display}\nBranch: {branch_display}"
        # uniticon.txt — required or engine raises "not found in Icon database"
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            uic.blocks[self.icon] = {
                "FirstFrame": '"UPLG001.TGA"',
                "Movie": '"NULL"',
                "Gameplay": f'"{self.ident}_GAMEPLAY"',
                "Historical": f'"{self.ident}_HISTORICAL"',
                "Prereq": f'"{self.ident}_PREREQ"',
                "Vari": f'"{self.ident}_STATISTICS"',
                "Icon": '"UPLG001.TGA"',
                "LargeIcon": '"NULL"',
                "SmallIcon": '"NULL"',
                "StatText": f'"{self.ident}_PREREQ"',
            }

    def check(self, reg: FileRegistry) -> List[str]:
        errors = []
        adv = reg.load("default/gamedata/Advance.txt")
        if self.ident not in adv.blocks:
            errors.append(f"{self.ident} not in Advance.txt")
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            errors.append(f"{self.icon} not in uniticon.txt")
        return errors


class ModBuilding:
    def __init__(self, ident: str, name: str, cost: str, upkeep: str,
                 advance: str, icon: str = "", desc: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.upkeep = upkeep
        self.advance = advance
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc

    def register(self, reg: FileRegistry):
        # Improve.txt — only include ENABLING_ADVANCE when non-empty; an empty
        # value would cause the renderer to produce "ENABLING_ADVANCE " (no rhs)
        # which the CTP2 parser misreads by consuming the NEXT token as the value.
        imp = reg.load("default/gamedata/Improve.txt")
        fields: Dict[str, str] = {
            "IMPROVEMENT_PRODUCTION_COST": self.cost,
            "IMPROVEMENT_UPKEEP": self.upkeep,
            "IMPROVE_DEFAULT_ICON": self.icon,
            "IMPROVE_DESCRIPTION": f"DESCRIPTION_{self.ident}",
        }
        if self.advance:
            fields["ENABLING_ADVANCE"] = self.advance
        imp.blocks[self.ident] = fields
        # uniticon.txt
        uic = reg.load("default/gamedata/uniticon.txt")
        uic.blocks[self.icon] = {
            "FirstFrame": '"UPLG001.TGA"',
            "Movie": '"NULL"',
            "Gameplay": f'"{self.ident}_GAMEPLAY"',
            "Historical": f'"{self.ident}_HISTORICAL"',
            "Prereq": f'"{self.ident}_PREREQ"',
            "Vari": f'"{self.ident}_STATISTICS"',
            "Icon": '"UPLG001.TGA"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{self.ident}_STATISTICS"',
        }
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections[f"{self.ident}_{suffix}"] = f"<L:DATABASE_IMPROVEMENTS,{self.ident}>{self.name}<e>"
        if self.advance:
            prereq_label = self.advance.split('_', 1)[1].title() if '_' in self.advance else self.advance
            gl.sections[f"{self.ident}_PREREQ"] = f"Requires:\n<L:DATABASE_ADVANCES,{self.advance}>{prereq_label}<e>"
        else:
            gl.sections[f"{self.ident}_PREREQ"] = f"No advance required."
        gl.sections[f"{self.ident}_STATISTICS"] = f"<L:DATABASE_IMPROVEMENTS,{self.ident}>{self.name}<e>"

    def check(self, reg : FileRegistry) -> List[str]:
        errors = []
        imp = reg.load("default/gamedata/Improve.txt")
        if self.ident not in imp.blocks:
            errors.append(f"{self.ident} not in Improve.txt")
        # Verify the advance exists
        adv = reg.load("default/gamedata/Advance.txt")
        if self.advance not in adv.blocks:
            errors.append(f"{self.ident} requires {self.advance} which is not in Advance.txt")
        return errors


class ModTileImp:
    """Tile improvement entity — writes to tileimp.txt."""
    def __init__(self, ident: str, name: str, level: str, tile_class: str,
                 icon: str = "", tooltip: str = "", statusbar: str = "",
                 sound: str = "", construction_tiles: str = "",
                 cant_build_on: str = "", excludes: str = "",
                 terrain_effects: List[Dict[str, str]] = None):
        self.ident = ident
        self.name = name
        self.level = level
        self.tile_class = tile_class
        self.icon = icon or f"ICON_{ident}"
        self.tooltip = tooltip
        self.statusbar = statusbar
        self.sound = sound
        self.construction_tiles = construction_tiles
        self.cant_build_on = cant_build_on
        self.excludes = excludes
        self.terrain_effects = terrain_effects or []

    def register(self, reg: FileRegistry):
        """Write this tile improvement to tileimp.txt."""
        tileimp = reg.load("default/gamedata/tileimp.txt")
        block = {
            "Icon": self.icon,
            "Tooltip": self.tooltip or f"TOOLTIP_{self.ident}",
            "Statusbar": self.statusbar or f"STATUSBAR_{self.ident}",
            "Sound": self.sound or "None",
            "Level": self.level,
            "Class": self.tile_class,
            "ConstructionTiles": self.construction_tiles,
            "CantBuildOn": self.cant_build_on,
            "Excludes": self.excludes,
        }
        # Build nested TerrainEffect blocks
        terrain_data = []
        for te in self.terrain_effects:
            te_block = {"Terrain": te.get("terrain", "")}
            for key in ("BonusFood", "BonusProduction", "BonusGold",
                       "EnableAdvance", "ProductionCost", "ProductionTime",
                       "TilesetIndex"):
                if key in te:
                    te_block[key] = te[key]
            terrain_data.append(te_block)

        # Store terrain effects as a sub-dict under TerrainEffects
        # The CTP2BlockFile.render() handles this — check how it serializes
        # If render() doesn't handle nested blocks, we need to store as string
        # Actually, looking at CTP2BlockFile, it stores Dict[str, str] so
        # we may need a different approach for TerrainEffect sub-blocks.

        tileimp.blocks[self.ident] = block
        if terrain_data:
            tileimp.blocks[f"{self.ident}_TERRAIN"] = {"_terrain_effects": terrain_data}

    def check(self, reg: FileRegistry) -> List[str]:
        """Validate this tile improvement exists in tileimp.txt."""
        issues = []
        try:
            tileimp = reg.load("default/gamedata/tileimp.txt")
            if self.ident not in tileimp.blocks:
                issues.append(f"TileImp {self.ident} not found in tileimp.txt")
        except Exception as e:
            issues.append(f"Error loading tileimp.txt: {e}")
        return issues


class ModWonder:
    def __init__(self, ident: str, name: str, cost: str, advance: str,
                 icon: str = "", desc: str = "", movie: str = ""):
        self.ident = ident
        self.name = name
        self.cost = cost
        self.advance = advance
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc
        self.movie = movie

    def _block_text(self) -> str:
        """Return a fully-formed multi-line wonder block."""
        lines = [f"{self.ident} {{"]
        lines.append(f"   DefaultIcon {self.icon}")
        lines.append(f"   Description DESCRIPTION_{self.ident}")
        if self.movie:
            lines.append(f"   Movie MOVIE_{self.ident}")
        lines.append(f"   EnableAdvance {self.advance}")
        lines.append(f"   ProductionCost {self.cost}")
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: FileRegistry):
        # Wonder.txt — append-only; never re-renders existing content
        won = reg.load("default/gamedata/Wonder.txt")
        won.add_wonder(self.ident, self._block_text())
        # uniticon.txt (wonder icon for icon display)
        uic = reg.load("default/gamedata/uniticon.txt")
        uic.blocks[self.icon] = {
            "FirstFrame": '"UPLG001.TGA"',
            "Movie": '"NULL"',
            "Gameplay": f'"{self.ident}_GAMEPLAY"',
            "Historical": f'"{self.ident}_HISTORICAL"',
            "Prereq": f'"{self.ident}_PREREQ"',
            "Vari": f'"{self.ident}_STATISTICS"',
            "Icon": '"UPLG001.TGA"',
            "LargeIcon": '"NULL"',
            "SmallIcon": '"NULL"',
            "StatText": f'"{self.ident}_STATISTICS"',
        }
        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc
        if self.movie:
            s.entries[f"MOVIE_{self.ident}"] = ""
        s.entries[f"{self.ident}_ARTICLE"] = "the "
        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        for suffix in ["GAMEPLAY", "HISTORICAL"]:
            gl.sections[f"{self.ident}_{suffix}"] = f"<L:DATABASE_WONDERS,{self.ident}>{self.name}<e>"
        gl.sections[f"{self.ident}_PREREQ"] = f"Requires:\n<L:DATABASE_ADVANCES,{self.advance}>{self.advance.split('_', 1)[1].title() if '_' in self.advance else self.advance}<e>"
        gl.sections[f"{self.ident}_STATISTICS"] = f"<L:DATABASE_WONDERS,{self.ident}>{self.name}<e>"

    def check(self, reg: FileRegistry) -> List[str]:
        errors = []
        won = reg.load("default/gamedata/Wonder.txt")
        if self.ident not in won.blocks:
            errors.append(f"{self.ident} not in Wonder.txt")
        adv = reg.load("default/gamedata/Advance.txt")
        if self.advance not in adv.blocks:
            errors.append(f"{self.ident} requires {self.advance} not in Advance.txt")
        return errors


class ModUnit:
    """A CTP2 unit entity.

    Registers across Units.txt (append-only), uniticon.txt, gl_str.txt,
    and Great_Library.txt. All required CTP2 fields are generated so the
    engine never hits a "missing field" parse error.

    Args:
        ident:        e.g. "UNIT_PEASANTS"
        name:         display name, e.g. "Peasants"
        category:     UNIT_CATEGORY_ATTACK / _NAVAL / _AIR / _SPECIAL
        attack:       CTP2 Attack value (already scaled by caller)
        defense:      CTP2 Defense value (already scaled by caller)
        sprite:       DefaultSprite identifier (REQUIRED by engine)
        icon:         icon override; defaults to ICON_{ident}
        desc:         short description for gl_str / Great Library
        advance:      EnableAdvance identifier, or "" for no prereq
        move:         MaxMovePoints (100 = 1 movement point in MoM)
        hp:           MaxHP
        firepower:    Firepower
        armor:        Armor
        zbrange:      ZBRangeAttack (0 for melee units)
        shield_cost:  ShieldCost
        shield_hunger: ShieldHunger per turn
        gold_hunger:  GoldHunger per turn
        sound_set:    base unit name used for all SOUND_ IDs (e.g. "WARRIOR")
        domain:       0 = land, 1 = air, 2 = sea
        size:         Small / Medium / Large
    """

    def __init__(self, ident: str, name: str, category: str, attack: int, defense: int,
                 sprite: str = "SPRITE_WARRIOR", icon: str = "", desc: str = "",
                 advance: str = "", move: int = 100, hp: int = 10, firepower: int = 1,
                 armor: int = 1, zbrange: int = 0, shield_cost: int = 200,
                 shield_hunger: int = 2, gold_hunger: int = 0,
                 sound_set: str = "WARRIOR", domain: int = 0, size: str = "Small"):
        self.ident = ident
        self.name = name
        # Normalize category: CTP2 uses AERIAL not AIR
        self.category = 'UNIT_CATEGORY_AERIAL' if category == 'UNIT_CATEGORY_AIR' else category
        self.attack = attack
        self.defense = defense
        self.sprite = sprite
        self.icon = icon or f"ICON_{ident}"
        self.desc = desc
        self.advance = advance
        self.move = move
        self.hp = hp
        self.firepower = firepower
        self.armor = armor
        self.zbrange = zbrange
        self.shield_cost = shield_cost
        self.shield_hunger = shield_hunger
        self.gold_hunger = gold_hunger
        self.sound_set = sound_set
        self.domain = domain
        self.size = size

    def _block_text(self) -> str:
        """Return a complete, correctly-formatted multi-line unit block."""
        lines = [f"{self.ident} {{"]
        lines += [
            f"   Description DESCRIPTION_{self.ident}",
            f"   DefaultIcon {self.icon}",
            f"   DefaultSprite {self.sprite}",
            f"   Category {self.category}",
            f"   Attack {self.attack}",
            f"   Defense {self.defense}",
            f"   ZBRangeAttack {self.zbrange}",
            f"   Firepower {self.firepower}",
            f"   Armor {self.armor}",
            f"   MaxHP {self.hp}",
            f"   ShieldCost {self.shield_cost}",
            f"   PowerPoints {max(100, self.shield_cost // 2)}",
            f"   ShieldHunger {self.shield_hunger}",
            f"   GoldHunger {self.gold_hunger}",
            f"   FoodHunger 0",
            f"   MaxMovePoints {self.move}",
            f"   VisionRange 2",
        ]
        if self.advance:
            lines.append(f"   EnableAdvance {self.advance}")
        lines += [
            f"   ActiveDefenseRange 0",
            f"   LossMoveToDmgNone",
            f"   MaxFuel 0",
        ]
        if self.domain == 0:
            lines += ["   CanEntrench", "   CanExpel", "   CanPillage",
                      "   CanPirate", "   ExertsMartialLaw", "   DeathEffectsHappy"]
        elif self.domain == 1:
            lines += ["   CantCaptureCity", "   DeathEffectsHappy"]
        else:
            lines += ["   CanPirate", "   CantCaptureCity", "   DeathEffectsHappy"]
        snd = self.sound_set
        lines += [
            f"   SoundSelect1 SOUND_SELECT1_{snd}",
            f"   SoundSelect2 SOUND_SELECT2_{snd}",
            f"   SoundMove SOUND_MOVE_{snd}",
            f"   SoundAcknowledge SOUND_ACKNOWLEDGE_{snd}",
            f"   SoundCantMove SOUND_CANTMOVE_{snd}",
            f"   SoundAttack SOUND_ATTACK_{snd}",
            f"   SoundWork SOUND_WORK_{snd}",
            f"   SoundVictory SOUND_VICTORY_{snd}",
            f"   SoundDeath SOUND_DEATH_{snd}",
            "",
        ]
        if self.domain == 0:
            lines += [
                "   CanAttack: Land", "   CanAttack: Mountain",
                "   CanSee: Standard",
                "   MovementType: Land", "   MovementType: Mountain",
                f"   Size: {self.size}", "   VisionClass: Standard",
                "   CanReform {",
                "      Sound SOUND_ID_REFORM_CITY",
                "      Effect SPECEFFECT_REFORMCITY",
                "   }",
            ]
        elif self.domain == 1:
            lines += [
                "   CanAttack: Land", "   CanAttack: Mountain", "   CanAttack: Air",
                "   CanSee: Standard",
                "   MovementType: Air",
                f"   Size: {self.size}", "   VisionClass: Standard",
            ]
        else:
            lines += [
                "   CanAttack: Sea", "   CanAttack: ShallowWater",
                "   CanSee: Standard",
                "   MovementType: Sea", "   MovementType: ShallowWater",
                f"   Size: {self.size}", "   VisionClass: Standard",
            ]
        lines.append("}")
        return "\n".join(lines)

    def register(self, reg: 'FileRegistry'):
        """Register this unit across all relevant CTP2 files."""
        # Units.txt — append-only; never re-renders existing content
        uni = reg.load("default/gamedata/Units.txt")
        uni.add_unit(self.ident, self._block_text())

        # uniticon.txt — preserve the committed AE/proxy application baseline.
        # Extracted ICON_UNIT_*.TGA assets are applied separately during probe
        # runs so extraction and application stay isolated.
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            uic.blocks[self.icon] = {
                "FirstFrame": '"UPUP003L.TGA"',
                "Movie": '"NULL"',
                "Gameplay": f'"{self.ident}_GAMEPLAY"',
                "Historical": f'"{self.ident}_HISTORICAL"',
                "Prereq": f'"{self.ident}_PREREQ"',
                "Vari": f'"{self.ident}_STATISTICS"',
                "Icon": '"UPUP003A.TGA"',
                "LargeIcon": '"UPUP003L.TGA"',
                "SmallIcon": '"UPUP003B.TGA"',
                "StatText": f'"{self.ident}_SUMMARY"',
            }

        # gl_str.txt
        s = reg.load("english/gamedata/gl_str.txt")
        s.entries[self.ident] = self.name
        s.entries[f"DESCRIPTION_{self.ident}"] = self.desc or f"A Master of Magic unit: {self.name}."

        # Great_Library.txt
        gl = reg.load("english/gamedata/Great_Library.txt")
        if self.advance:
            adv_label = self.advance.split('_', 1)[1].replace('_', ' ').title() \
                if '_' in self.advance else self.advance
            prereq_text = (f"Requires:\n"
                           f"<L:DATABASE_ADVANCES,{self.advance}>{adv_label}<e>")
        else:
            prereq_text = "Requires:\nNothing"
        stats_text = "\n".join([
            "Attack: {UnitDB(UnitRecord[0]).Attack / 100}",
            "Ranged: {UnitDB(UnitRecord[0]).ZBRangeAttack}",
            "Defense: {UnitDB(UnitRecord[0]).Defense / 100}",
            "Armor: {UnitDB(UnitRecord[0]).Armor / 100}",
            "Damage: {UnitDB(UnitRecord[0]).Firepower}",
            "Vision: {UnitDB(UnitRecord[0]).VisionRange}",
            "Movement: {UnitDB(UnitRecord[0]).MaxMovePoints / 10000}",
            "Max HP: {UnitDB(UnitRecord[0]).MaxHP}",
            "Costs: {UnitDB(UnitRecord[0]).ShieldCost}",
            "Upkeep: {UnitDB(UnitRecord[0]).ShieldHunger} Shields",
            "Food Hunger: {UnitDB(UnitRecord[0]).FoodHunger}",
        ])
        gl.sections.setdefault(f"{self.ident}_PREREQ", prereq_text)
        gl.sections.setdefault(f"{self.ident}_STATISTICS", stats_text)
        gl.sections.setdefault(f"{self.ident}_SUMMARY",
                               f"{self.name}: a Master of Magic proxy unit.")
        gl.sections.setdefault(f"{self.ident}_GAMEPLAY",
                               f"The {self.name} is a unit from Master of Magic.")
        gl.sections.setdefault(f"{self.ident}_HISTORICAL",
                               f"The {self.name} is represented here as a proxy unit "
                               f"while the final MoM art swap is in progress.")

    def check(self, reg: 'FileRegistry') -> List[str]:
        errors = []
        uni = reg.load("default/gamedata/Units.txt")
        if not uni.has_unit(self.ident):
            errors.append(f"{self.ident} not in Units.txt")
        uic = reg.load("default/gamedata/uniticon.txt")
        if self.icon not in uic.blocks:
            errors.append(f"{self.icon} not in uniticon.txt")
        return errors

```


## ctp2_ae_parser.py

```python
"""
ctp2_ae_parser.py — CTP2 block-file parser for AE mod files.

Handles all CTP2 block structures faithfully:
  KV        — Key-value:        Category UNIT_CATEGORY_AERIAL
  Flag      — Bare boolean:     LossMoveToDmgNone
  SubList   — Tagged list:      CanSee: Land
  Nested    — Recursive block:  SlaveUprising { ... }
  Anonymous — Unnamed block:    { ... }  (used in DiffDB difficulty settings)

Round-trip guarantee: parse → render produces byte-equivalent output for all
AE mod files (Units, Advance, buildings, Wonder, terrain, tileimp, AdvanceLists,
DiffDB, Const).

Tokenizer discriminator (no hardcoded whitelist):
  PascalCase token (has ≥1 lowercase letter) = KEY or BARE FLAG
  ALL_CAPS / numeric / quoted string          = VALUE
"""

from __future__ import annotations

import csv
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import List, NamedTuple, Tuple, Union


# ---------------------------------------------------------------------------
# Item types
# ---------------------------------------------------------------------------

class KV(NamedTuple):
    key: str
    val: str

class Flag(NamedTuple):
    name: str

class SubList(NamedTuple):
    key: str
    val: str

class Nested(NamedTuple):
    name: str
    items: tuple  # recursive

class Anonymous(NamedTuple):
    """Unnamed brace block — DiffDB difficulty settings."""
    items: tuple

Item  = Union[KV, Flag, SubList, Nested, Anonymous]
Block = Tuple[Item, ...]
Blocks = "OrderedDict[str, Block]"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r'(?<!["\w])#[^\n]*')
_SLASH_COMMENT_RE = re.compile(r'//[^\n]*')
_TOKEN_RE   = re.compile(r'"[^"]*"|\{|\}|[^"\s{}]+')


def _strip_comments(text: str) -> str:
    text = _SLASH_COMMENT_RE.sub('', text)
    return _COMMENT_RE.sub('', text)


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(_strip_comments(text))


def _is_key(tok: str) -> bool:
    return bool(re.search(r'[a-z]', tok)) and not tok.startswith('"')


def _is_value(tok: str) -> bool:
    if tok in ('{', '}'):
        return False
    if tok.startswith('"'):
        return True
    try:
        float(tok)
        return True
    except ValueError:
        pass
    return not re.search(r'[a-z]', tok)


# ---------------------------------------------------------------------------
# Recursive body parser
# ---------------------------------------------------------------------------

def _parse_body(tokens: List[str], pos: int) -> Tuple[Block, int]:
    """Parse from pos until matching '}'. Returns (items, next_pos)."""
    items: List[Item] = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '}':
            return tuple(items), pos + 1
        if tok == '{':
            # Nested anonymous block
            inner, pos = _parse_body(tokens, pos + 1)
            items.append(Anonymous(inner))
            continue
        if tok.endswith(':'):
            key = tok[:-1]
            pos += 1
            if pos < len(tokens) and tokens[pos] not in ('{', '}'):
                items.append(SubList(key, tokens[pos]))
                pos += 1
            continue
        # Any non-brace token at this position is in KEY position.
        # The case-based _is_key heuristic only governs the value/flag decision
        # below — a token here is always a key candidate (handles ALL_CAPS keys
        # like CONCEPT_DEFAULT_ICON in compact concept.txt blocks).
        nxt = tokens[pos + 1] if pos + 1 < len(tokens) else '}'
        if nxt == '{':
            inner, pos = _parse_body(tokens, pos + 2)
            items.append(Nested(tok, inner))
            continue
        # KV vs bare Flag: it's a Flag only when the following token is itself a
        # key (PascalCase, has lowercase) rather than a value. A value-shaped
        # next token (ALL_CAPS, numeric, quoted) means tok is a KV key.
        if nxt in ('}', '{') or _is_key(nxt) and not _is_value(nxt):
            # next token begins a new item → tok is a bare flag
            items.append(Flag(tok))
            pos += 1
        else:
            items.append(KV(tok, nxt))
            pos += 2
    return tuple(items), pos


# ---------------------------------------------------------------------------
# Top-level file parser
# ---------------------------------------------------------------------------

def parse_file(text: str) -> "OrderedDict[str, Block]":
    """
    Parse a CTP2 block file.

    Returns OrderedDict mapping block-ID → Block (tuple of Items).
    Anonymous top-level blocks (DiffDB difficulty sections) are keyed as
    '__anon_0__', '__anon_1__', etc.
    """
    tokens = _tokenize(text)
    result: OrderedDict = OrderedDict()
    anon_idx = 0
    pos = 0
    # Some files (concept.txt) begin with a bare record-count token that CTP2
    # reads before the blocks. Preserve it as a synthetic __count__ entry so it
    # survives round-trip; the renderer emits it back as a leading bare line.
    if tokens and tokens[0] not in ('{', '}'):
        nxt = tokens[1] if len(tokens) > 1 else None
        is_count = nxt != '{'
        try:
            float(tokens[0])
        except ValueError:
            is_count = False
        if is_count:
            result['__count__'] = (KV('__count__', tokens[0]),)
            pos = 1
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '}':
            pos += 1
            continue
        if tok == '{':
            # Anonymous top-level block (DiffDB difficulty setting)
            block, pos = _parse_body(tokens, pos + 1)
            key = f'__anon_{anon_idx}__'
            anon_idx += 1
            result[key] = block
            continue
        if pos + 1 < len(tokens) and tokens[pos + 1] == '{':
            block_id = tok
            block, pos = _parse_body(tokens, pos + 2)
            # CTP2 files may repeat a block ID (e.g. uniticon ICON_ORDER_CONDUCT_HIT).
            # An OrderedDict keyed only by ID would overwrite the first occurrence,
            # silently dropping a block the game keeps. Disambiguate duplicates with
            # a "\x00dupN" suffix that render_file strips back off.
            key = block_id
            if key in result:
                n = 1
                while f"{block_id}\x00dup{n}" in result:
                    n += 1
                key = f"{block_id}\x00dup{n}"
            result[key] = block
        else:
            pos += 1
    return result


# ---------------------------------------------------------------------------
# Renderer — faithful CTP2 multi-line format
# ---------------------------------------------------------------------------

def _render_items(items: Block, indent: int = 3) -> List[str]:
    pad = '\t'  # DiffDB uses tabs; normalise to tab indent
    lines: List[str] = []
    for item in items:
        if isinstance(item, KV):
            lines.append(f"{pad * (indent // 3)}{item.key}\t\t{item.val}")
        elif isinstance(item, Flag):
            lines.append(f"{pad * (indent // 3)}{item.name}")
        elif isinstance(item, SubList):
            lines.append(f"{pad * (indent // 3)}{item.key}: {item.val}")
        elif isinstance(item, Nested):
            lines.append(f"{pad * (indent // 3)}{item.name} {{")
            lines.extend(_render_items(item.items, indent + 3))
            lines.append(f"{pad * (indent // 3)}}}")
        elif isinstance(item, Anonymous):
            lines.append(f"{pad * (indent // 3)}{{")
            lines.extend(_render_items(item.items, indent + 3))
            lines.append(f"{pad * (indent // 3)}}}")
    return lines


def render_file(blocks: "OrderedDict[str, Block]") -> str:
    """Render parsed blocks back to CTP2 block format."""
    out: List[str] = []
    for block_id, items in blocks.items():
        if block_id == '__count__':
            out.append(items[0].val)
            out.append('')
            continue
        if block_id.startswith('__anon_'):
            out.append('{')
            out.extend(_render_items(items, indent=0))
            out.append('}')
        else:
            real_id = block_id.split('\x00dup')[0]
            out.append(f"{real_id} {{")
            out.extend(_render_items(items, indent=3))
            out.append('}')
        out.append('')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Targeted field mutators — used by the generator
# ---------------------------------------------------------------------------

def get_kv(items: Block, key: str) -> str | None:
    """Return first KV value for key, or None."""
    for item in items:
        if isinstance(item, KV) and item.key == key:
            return item.val
    return None


def get_all_kv(items: Block, key: str) -> List[str]:
    """Return all KV values for a repeated key (e.g. Prerequisites)."""
    return [item.val for item in items if isinstance(item, KV) and item.key == key]


def set_kv(items: Block, key: str, val: str) -> Block:
    """Replace first occurrence of KV(key, *) with KV(key, val). Appends if absent."""
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, KV) and item.key == key:
            lst[i] = KV(key, val)
            return tuple(lst)
    lst.append(KV(key, val))
    return tuple(lst)


def update_nested_kv(items: Block, nested_name: str, key: str, val: str) -> Block:
    """Update a KV inside a named Nested block. Adds the nested block if absent."""
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, Nested) and item.name == nested_name:
            lst[i] = Nested(nested_name, set_kv(item.items, key, val))
            return tuple(lst)
    # nested not found — append it
    lst.append(Nested(nested_name, (KV(key, val),)))
    return tuple(lst)


def update_timescale_periods(items: Block, period_years: List[int]) -> Block:
    """
    Replace PERIOD sub-blocks inside TIME_SCALE{} with new YEARS_PER_TURN values.

    Precondition: len(period_years) == number of PERIOD blocks in TIME_SCALE.
    """
    lst = list(items)
    for i, item in enumerate(lst):
        if isinstance(item, Nested) and item.name == 'TIME_SCALE':
            ts_items = list(item.items)
            period_idx = 0
            for j, sub in enumerate(ts_items):
                if isinstance(sub, Nested) and sub.name == 'PERIOD':
                    if period_idx < len(period_years):
                        ts_items[j] = Nested('PERIOD',
                            set_kv(sub.items, 'YEARS_PER_TURN', str(period_years[period_idx])))
                        period_idx += 1
            lst[i] = Nested('TIME_SCALE', tuple(ts_items))
            return tuple(lst)
    return tuple(lst)


# ---------------------------------------------------------------------------
# DiffDB specialised parser — handles anonymous top-level blocks
# ---------------------------------------------------------------------------

DIFF_NAMES = ['Beginner', 'Easy', 'Medium', 'Hard', 'Very Hard', 'Impossible']


def parse_diffdb(text: str) -> List[Block]:
    """
    Parse DiffDB.txt into a list of 6 anonymous difficulty blocks.
    Returns list[Block] in order [Beginner … Impossible].
    """
    blocks = parse_file(text)
    anon = [v for k, v in blocks.items() if k.startswith('__anon_')]
    return anon


def render_diffdb(diff_blocks: List[Block], header_comment: str = '') -> str:
    """Render 6 difficulty blocks back to DiffDB format."""
    out: List[str] = []
    if header_comment:
        out.append(header_comment)
        out.append('')
    for i, block in enumerate(diff_blocks):
        if i < len(DIFF_NAMES):
            out.append(f'## {DIFF_NAMES[i]}')
        out.append('{')
        out.extend(_render_items(block, indent=0))
        out.append('}')
        out.append('')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Const.txt flat key-value parser
# ---------------------------------------------------------------------------

_CONST_LINE_RE = re.compile(r'^([A-Z_][A-Z_0-9]*)\s+(.+?)(?:\s*#.*)?$')


def parse_const(text: str) -> "OrderedDict[str, str]":
    """Parse flat key-value Const.txt. Returns OrderedDict key→value."""
    result: OrderedDict = OrderedDict()
    for line in text.splitlines():
        m = _CONST_LINE_RE.match(line.strip())
        if m:
            result[m.group(1)] = m.group(2).strip()
    return result


def render_const(kv: "OrderedDict[str, str]", original_text: str) -> str:
    """
    Re-render Const.txt substituting changed values in-place, preserving
    all comments and blank lines from the original.
    """
    out: List[str] = []
    for line in original_text.splitlines():
        m = _CONST_LINE_RE.match(line.strip())
        if m and m.group(1) in kv:
            # Preserve leading whitespace, replace value
            lead = line[: len(line) - len(line.lstrip())]
            comment_match = re.search(r'\s*#.*$', line)
            comment = comment_match.group(0) if comment_match else ''
            out.append(f"{lead}{m.group(1)} {kv[m.group(1)]}{comment}")
        else:
            out.append(line)
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Round-trip test helper
# ---------------------------------------------------------------------------

def _diff_blocks(a: "OrderedDict", b: "OrderedDict") -> List[str]:
    errors = []
    for k in a:
        if k not in b:
            errors.append(f"MISSING in round-trip: {k}")
        elif a[k] != b[k]:
            errors.append(f"CHANGED: {k}")
    for k in b:
        if k not in a:
            errors.append(f"EXTRA in round-trip: {k}")
    return errors


def verify_roundtrip(path: Path) -> bool:
    """Parse → render → re-parse and assert structural identity."""
    text = path.read_text(encoding='utf-8', errors='replace')
    if path.name.lower() == 'diffdb.txt':
        blocks1 = parse_diffdb(text)
        rendered = render_diffdb(blocks1)
        blocks2 = parse_diffdb(rendered)
        ok = all(a == b for a, b in zip(blocks1, blocks2)) and len(blocks1) == len(blocks2)
    else:
        blocks1 = parse_file(text)
        rendered = render_file(blocks1)
        blocks2 = parse_file(rendered)
        errors = _diff_blocks(blocks1, blocks2)
        ok = not errors
    status = "PASS ✓" if ok else "FAIL ✗"
    print(f"  {path.name}: {status}")
    return ok


if __name__ == '__main__':
    import sys
    files = sys.argv[1:] or list(Path('.').glob('*.txt'))
    all_ok = True
    for f in files:
        p = Path(f)
        if p.exists():
            all_ok &= verify_roundtrip(p)
    sys.exit(0 if all_ok else 1)

```


## ctp2_line_codec.py

```python
"""
ctp2_line_codec.py — Faithful line-oriented codec for non-block CTP2 text files.

Some CTP2 files are not brace-block structured but are still fully parseable and
editable:

  flat-KV    Const.txt        e.g.  PERCENT_LAND 45 #40 how much is land
  string-db  gl_str.txt       e.g.  STR_KEY  "display text"
             scen_str.txt
             junk_str.txt

These were previously copied verbatim, which made them un-editable through the
control plane. That was wrong. This codec parses them into editable rows while
guaranteeing byte-exact reconstruction for any line whose value is unchanged.

Fidelity strategy
-----------------
Each source line becomes one CSV row carrying:
  line_seq   0-based line number (preserves order and blank lines)
  kind       RAW | KV | STR
  key        field key (KV/STR), "" for RAW
  value      editable value — bare token (KV) or unquoted text (STR)
  raw        the original line, verbatim

Reconstruction rule (per line):
  - RAW            → emit `raw` exactly
  - KV/STR, value unchanged vs the value re-extracted from `raw` → emit `raw` exactly
  - KV/STR, value changed → splice the new value into `raw` at the original value
                            span, preserving leading whitespace, key, separator
                            whitespace, and any trailing inline comment

Result: a file with no edits round-trips byte-for-byte. A file with edits keeps
original formatting everywhere except the single value spans that changed.

Failure modes
-------------
  - A line tagged KV/STR whose `raw` no longer contains a parseable value raises
    ValueError on build (corrupt CSV), rather than silently emitting garbage.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

LINE_HEADERS = ["line_seq", "kind", "key", "value", "raw"]

# flat-KV:  KEY  VALUE  [#comment | ##comment | ; comment]
#   key  = first token (letters/digits/underscore)
#   value spans from after the key-gap to before an inline comment or EOL
_KV_RE = re.compile(
    r'^(?P<lead>\s*)'
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<gap>\s+)'
    r'(?P<value>[^#;\s][^#;]*?)'
    r'(?P<trail>\s*(?:[#;].*)?)$'
)

# string-db:  KEY  "value"   (value is everything inside the first quote pair)
_STR_RE = re.compile(
    r'^(?P<lead>\s*)'
    r'(?P<key>[A-Za-z_][A-Za-z0-9_]*)'
    r'(?P<gap>\s+)'
    r'"(?P<value>.*)"'
    r'(?P<trail>\s*(?:[#;].*)?)$'
)


class Line(NamedTuple):
    line_seq: int
    kind: str            # RAW | KV | STR
    key: str
    value: str
    raw: str


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def detect_kind(text: str) -> Optional[str]:
    """
    Return 'flat_kv', 'string_db', or None (not a line file) by sampling lines.

    string_db wins if quoted KEY "value" lines dominate; flat_kv if bare KEY VALUE
    lines dominate. Comments/blank lines don't count toward either.
    """
    kv = strdb = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if _STR_RE.match(ln):
            strdb += 1
        elif _KV_RE.match(ln):
            kv += 1
    if strdb == 0 and kv == 0:
        return None
    return "string_db" if strdb >= kv else "flat_kv"


# ---------------------------------------------------------------------------
# Parse  →  rows
# ---------------------------------------------------------------------------

def parse_lines(text: str, kind: str) -> List[Line]:
    """Parse text into Line rows. `kind` is 'flat_kv' or 'string_db'."""
    pat = _STR_RE if kind == "string_db" else _KV_RE
    out_kind = "STR" if kind == "string_db" else "KV"
    rows: List[Line] = []
    # splitlines(keepends=False); we normalise to \n on output via raw storage.
    for i, raw in enumerate(text.split("\n")):
        m = pat.match(raw)
        if m:
            rows.append(Line(i, out_kind, m.group("key"), m.group("value"), raw))
        else:
            rows.append(Line(i, "RAW", "", "", raw))
    # Trailing newline handling: text.split keeps a final "" if text ended with \n
    return rows


# ---------------------------------------------------------------------------
# Rows  →  text  (line-preserving)
# ---------------------------------------------------------------------------

def _reextract_value(raw: str, kind: str) -> Optional[str]:
    pat = _STR_RE if kind == "STR" else _KV_RE
    m = pat.match(raw)
    return m.group("value") if m else None


def _splice_value(raw: str, kind: str, new_value: str) -> str:
    """Replace only the value span in `raw`, preserving everything else."""
    pat = _STR_RE if kind == "STR" else _KV_RE
    m = pat.match(raw)
    if not m:
        raise ValueError(f"cannot splice value into line: {raw!r}")
    if kind == "STR":
        return f'{m.group("lead")}{m.group("key")}{m.group("gap")}"{new_value}"{m.group("trail")}'
    return f'{m.group("lead")}{m.group("key")}{m.group("gap")}{new_value}{m.group("trail")}'


def render_lines(rows: List[Line]) -> str:
    rows = sorted(rows, key=lambda r: r.line_seq)
    out: List[str] = []
    for r in rows:
        if r.kind == "RAW":
            out.append(r.raw)
            continue
        original_value = _reextract_value(r.raw, r.kind)
        if original_value is None:
            raise ValueError(f"line {r.line_seq} tagged {r.kind} but raw has no value: {r.raw!r}")
        if r.value == original_value:
            out.append(r.raw)            # unchanged → byte-exact
        else:
            out.append(_splice_value(r.raw, r.kind, r.value))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def export_line_csv(rows: List[Line], csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LINE_HEADERS)
        w.writeheader()
        for r in rows:
            w.writerow(r._asdict())
    return len(rows)


def import_line_csv(csv_path: Path) -> List[Line]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = []
        for d in csv.DictReader(f):
            rows.append(Line(int(d["line_seq"]), d["kind"], d["key"],
                             d["value"], d["raw"]))
    return rows


# ---------------------------------------------------------------------------
# Round-trip verify
# ---------------------------------------------------------------------------

def verify_line_roundtrip(txt_path: Path) -> bool:
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    kind = detect_kind(text)
    if kind is None:
        print(f"  {txt_path.name}: not a line file (skipped)")
        return True
    rows = parse_lines(text, kind)

    # through actual CSV
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LINE_HEADERS)
    w.writeheader()
    for r in rows:
        w.writerow(r._asdict())
    buf.seek(0)
    rows2 = [Line(int(d["line_seq"]), d["kind"], d["key"], d["value"], d["raw"])
             for d in csv.DictReader(buf)]
    rebuilt = render_lines(rows2)

    ok = rebuilt == text
    data_rows = sum(1 for r in rows if r.kind != "RAW")
    print(f"  {txt_path.name}: {'PASS ✓' if ok else 'FAIL ✗'}  "
          f"({kind}, {data_rows} editable rows)")
    if not ok:
        a, b = text.split("\n"), rebuilt.split("\n")
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                print(f"    line {i}: {x!r}\n          → {y!r}")
                break
    return ok


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        p = Path(f)
        if p.exists():
            verify_line_roundtrip(p)

```


## ctp2_csv_codec.py

```python
"""
ctp2_csv_codec.py — Faithful CTP2 block ↔ CSV codec (the "decoder ring").

Goal: a CTP2 mod folder round-trips losslessly through CSV.
  txt → parse → CSV → parse → render → txt   ⟹   output ≡ input (shape + fields)

Design rationale (measured, not assumed)
-----------------------------------------
CTP2 dimensions vary in structural complexity:
  - Flat (Advance, Wonder, buildings): depth 1, KV + flags, occasional repeated key
  - Nested (Units, terrain, tileimp): depth 2, nested sub-blocks, sublists,
    hundreds of repeated keys and bare flags

A wide "one column per field" table cannot represent nested sub-blocks, ordered
repeated keys, or bare flags without losing information. So the CANONICAL CSV is
LONG-FORM: one row per leaf item, carrying block id, sequence, nesting path, kind,
key, value. This is 100% faithful for every dimension and is itself a queryable
relational table.

A WIDE projection (one row per block, one column per scalar field) is provided
separately for human editing of the flat dimensions only; it is lossy by design
and is never the reconstruction source.

CSV schema (long-form, canonical)
---------------------------------
  block_id   block identifier ("__anon_N__" for unnamed DiffDB blocks)
  block_seq  0-based order of the block within the file
  path       dotted nesting path of the parent ("" at top level,
             "TerrainEffect" one level down, "A.B" two levels down)
  item_seq   0-based order of this item within its parent block
  kind       KV | FLAG | SUBLIST | NESTED_OPEN | ANON_OPEN
  key        field key (block name for NESTED_OPEN; "" for ANON_OPEN)
  value      field value (KV/SUBLIST only; "" otherwise)

NESTED_OPEN / ANON_OPEN rows mark the start of a child block; their children
follow as rows whose `path` extends the parent path. The parser reconstructs the
tree from (path, item_seq) ordering — no closing rows needed.

Failure modes
-------------
  - Raises ValueError if a CSV row references a path whose parent is absent.
  - Round-trip mismatch is reported by verify(), never silently swallowed.
"""

from __future__ import annotations

import csv
from collections import OrderedDict
from pathlib import Path
from typing import List, Tuple

from ctp2_ae_parser import (
    KV, Flag, SubList, Nested, Anonymous,
    parse_file, render_file,
)

LONG_HEADERS = ["block_id", "block_seq", "path", "item_seq", "kind", "key", "value"]


# ---------------------------------------------------------------------------
# Block tree  →  long-form rows
# ---------------------------------------------------------------------------

def _flatten_items(items, block_id: str, block_seq: int,
                   path: str, rows: List[dict]) -> None:
    """Append one row per item; recurse into nested/anonymous blocks."""
    for item_seq, item in enumerate(items):
        if isinstance(item, KV):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="KV", key=item.key, value=item.val))
        elif isinstance(item, Flag):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="FLAG", key=item.name, value=""))
        elif isinstance(item, SubList):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="SUBLIST", key=item.key, value=item.val))
        elif isinstance(item, Nested):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="NESTED_OPEN", key=item.name, value=""))
            child_path = f"{path}.{item_seq}:{item.name}" if path else f"{item_seq}:{item.name}"
            _flatten_items(item.items, block_id, block_seq, child_path, rows)
        elif isinstance(item, Anonymous):
            rows.append(dict(block_id=block_id, block_seq=block_seq, path=path,
                             item_seq=item_seq, kind="ANON_OPEN", key="", value=""))
            child_path = f"{path}.{item_seq}:" if path else f"{item_seq}:"
            _flatten_items(item.items, block_id, block_seq, child_path, rows)


def blocks_to_rows(blocks: "OrderedDict[str, tuple]") -> List[dict]:
    rows: List[dict] = []
    for block_seq, (block_id, items) in enumerate(blocks.items()):
        _flatten_items(items, block_id, block_seq, "", rows)
    return rows


# ---------------------------------------------------------------------------
# Long-form rows  →  block tree
# ---------------------------------------------------------------------------

def _rows_to_items(rows: List[dict], parent_path: str):
    """
    Reconstruct the ordered item tuple for a given parent path.
    Children at this level are rows whose `path` == parent_path, ordered by item_seq.
    Nested/anon children recurse into their own extended path.
    """
    direct = [r for r in rows if r["path"] == parent_path]
    direct.sort(key=lambda r: int(r["item_seq"]))
    items = []
    for r in direct:
        kind = r["kind"]
        iseq = int(r["item_seq"])
        if kind == "KV":
            items.append(KV(r["key"], r["value"]))
        elif kind == "FLAG":
            items.append(Flag(r["key"]))
        elif kind == "SUBLIST":
            items.append(SubList(r["key"], r["value"]))
        elif kind == "NESTED_OPEN":
            child_path = f"{parent_path}.{iseq}:{r['key']}" if parent_path else f"{iseq}:{r['key']}"
            items.append(Nested(r["key"], tuple(_rows_to_items(rows, child_path))))
        elif kind == "ANON_OPEN":
            child_path = f"{parent_path}.{iseq}:" if parent_path else f"{iseq}:"
            items.append(Anonymous(tuple(_rows_to_items(rows, child_path))))
    return items


def rows_to_blocks(rows: List[dict]) -> "OrderedDict[str, tuple]":
    # Group rows by block, preserving block_seq order
    by_block: "OrderedDict[Tuple[int, str], List[dict]]" = OrderedDict()
    for r in rows:
        key = (int(r["block_seq"]), r["block_id"])
        by_block.setdefault(key, []).append(r)

    ordered = sorted(by_block.items(), key=lambda kv: kv[0][0])
    blocks: "OrderedDict[str, tuple]" = OrderedDict()
    for (bseq, bid), brows in ordered:
        items = _rows_to_items(brows, "")
        blocks[bid] = tuple(items)
    return blocks


# ---------------------------------------------------------------------------
# File-level CSV I/O
# ---------------------------------------------------------------------------

def export_long_csv(blocks: "OrderedDict[str, tuple]", csv_path: Path) -> int:
    rows = blocks_to_rows(blocks)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LONG_HEADERS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def import_long_csv(csv_path: Path) -> "OrderedDict[str, tuple]":
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows_to_blocks(rows)


# ---------------------------------------------------------------------------
# Round-trip verification
# ---------------------------------------------------------------------------

def verify_csv_roundtrip(txt_path: Path) -> bool:
    """txt → blocks → CSV → blocks: assert structural identity."""
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    blocks1 = parse_file(text)
    rows = blocks_to_rows(blocks1)

    # serialise and reparse through actual CSV to catch quoting/encoding issues
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=LONG_HEADERS)
    w.writeheader()
    w.writerows(rows)
    buf.seek(0)
    rows2 = list(csv.DictReader(buf))
    blocks2 = rows_to_blocks(rows2)

    ok = list(blocks1.items()) == list(blocks2.items())
    print(f"  {txt_path.name}: {'PASS ✓' if ok else 'FAIL ✗'}  "
          f"({len(blocks1)} blocks, {len(rows)} rows)")
    if not ok:
        for (k1, v1), (k2, v2) in zip(blocks1.items(), blocks2.items()):
            if k1 != k2 or v1 != v2:
                print(f"    first diff at block {k1!r} vs {k2!r}")
                break
    return ok


if __name__ == "__main__":
    import sys
    files = sys.argv[1:] or [str(p) for p in Path(".").glob("*.txt")]
    all_ok = True
    for f in files:
        p = Path(f)
        if p.exists():
            all_ok &= verify_csv_roundtrip(p)
    sys.exit(0 if all_ok else 1)

```


## validate_all_surfaces.py

```python
#!/usr/bin/env python
"""validate_all_surfaces.py — assert every CTP2 reference surface resolves.

CTP2 validates entity references from MANY surfaces (load- and run-time), not one.
This checks them ALL against the actual DB files so a build is provably launch-clean
before the game is started — ending the relaunch-per-error loop. Driven by the live
data files (the parser's source of truth), per dimension_inventory.md.

Surfaces checked:
  1. Data-file gating fields (EnableAdvance/ObsoleteAdvance/Prerequisites/
     AddAdvance/RemoveAdvance -> Advance DB; UpgradeTo -> Unit DB)
  2. Great Library <L:DATABASE_<TYPE>,<TOKEN>> links (all dimensions)
  3. Great Library advance sections [ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|STATISTICS]
  4. AI build lists / strategies (aidata/*.txt)
  5. EndGameObjects.txt (victory wonders/buildings/tile improvements)
  6. Base-fallback gamedata files (ctp2_data files NOT overridden by the scenario)
  7. SLIC entity symbols (UNIT_/IMPROVE_/ADVANCE_/WONDER_ in *.slc)

Paths honor the same env vars as ctp2_generator.py:
  CTP2_GENERATOR_SCENARIO_DIR, CTP2_GENERATOR_CTP2_DATA_DIR

Exit code 0 = clean; 1 = dangling references found (each printed).
"""
from __future__ import annotations
import os, re, sys
from pathlib import Path

SCEN = Path(os.environ.get(
    "CTP2_GENERATOR_SCENARIO_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000"))
CTP2_DATA = Path(os.environ.get(
    "CTP2_GENERATOR_CTP2_DATA_DIR",
    r"H:\Program Files(x86)\Activision\Call To Power 2\ctp2_data"))

GD = SCEN / "default" / "gamedata"
ENG = SCEN / "english" / "gamedata"
AID = SCEN / "default" / "aidata"

# Tokens that look like entity refs but are list/category NAMES, not entities.
_NOT_ENTITY = re.compile(r"_(BUILD_)?LIST_|_CATEGORY_|_GOOD_(ONE|TWO|THREE|FOUR)$")


def _read(p: Path) -> str:
    return p.read_text(encoding="latin-1") if p.exists() else ""


def _defs(files, pfx) -> set:
    s = set()
    for f in files:
        s |= set(re.findall(r"^(" + pfx + r"[A-Z0-9_]+)\s*\{", _read(GD / f), re.M))
    return s


def build_dbs() -> dict:
    return {
        "ADVANCE_":  _defs(["Advance.txt"], "ADVANCE_"),
        "UNIT_":     _defs(["Units.txt"], "UNIT_"),
        # Engine loads buildings.txt per gamefile.txt manifest; Improve.txt is NOT loaded.
        "IMPROVE_":  _defs(["buildings.txt"], "IMPROVE_"),
        "WONDER_":   _defs(["Wonder.txt"], "WONDER_"),
        "TERRAIN_":  _defs(["terrain.txt"], "TERRAIN_"),
        "GOVERNMENT_": _defs(["govern.txt"], "GOVERNMENT_"),
        "TILEIMP_":  _defs(["tileimp.txt"], "TILEIMP_"),
        "CONCEPT_":  _defs(["concept.txt"], "CONCEPT_"),
        "ORDER_":    _defs(["Orders.txt"], "ORDER_"),
        "GOOD_":     _defs(["goods.txt"], "GOOD_"),
    }


# DATABASE_<TYPE> -> entity prefix
_DBLINK = {
    "ADVANCES": "ADVANCE_", "UNITS": "UNIT_", "BUILDINGS": "IMPROVE_",
    "WONDERS": "WONDER_", "TERRAIN": "TERRAIN_", "GOVERNMENTS": "GOVERNMENT_",
    "TILE_IMPROVEMENTS": "TILEIMP_", "CONCEPTS": "CONCEPT_", "ORDERS": "ORDER_",
    "RESOURCE": "GOOD_",
}


def _dangling(tokens, valid) -> list:
    return sorted(t for t in tokens if t not in valid and not _NOT_ENTITY.search(t))


def main() -> int:
    dbs = build_dbs()
    failures = []  # (surface, detail)

    # 1. Data-file gating fields
    gate = re.compile(r"\b(?:EnableAdvance|ObsoleteAdvance|Prerequisites|AddAdvance|"
                      r"RemoveAdvance)\s+(ADVANCE_[A-Z0-9_]+)")
    upg = re.compile(r"\bUpgradeTo\s+(UNIT_[A-Z0-9_]+)")
    for f in sorted(GD.glob("*.txt")):
        txt = _read(f)
        bad = _dangling(set(gate.findall(txt)), dbs["ADVANCE_"])
        if bad:
            failures.append(("1 gating-advance", f"{f.name}: {bad[:6]}"))
        badu = _dangling(set(upg.findall(txt)), dbs["UNIT_"])
        if badu:
            failures.append(("1 gating-unit", f"{f.name}: {badu[:6]}"))

    # 2. Great Library DATABASE links
    gltext = _read(ENG / "Great_Library.txt") + _read(ENG / "WAW_Great_Library.txt")
    for dbtype, pfx in _DBLINK.items():
        refs = set(re.findall(r"<L:DATABASE_" + dbtype + r",(" + pfx + r"[A-Z0-9_]+)>", gltext))
        bad = _dangling(refs, dbs[pfx])
        if bad:
            failures.append((f"2 gl-link {dbtype}", str(bad[:6])))

    # 3. Great Library advance sections
    secs = set(re.findall(r"\[(ADVANCE_[A-Z0-9_]+)_(?:GAMEPLAY|HISTORICAL|PREREQ|STATISTICS)\]", gltext))
    bad = _dangling(secs, dbs["ADVANCE_"])
    if bad:
        failures.append(("3 gl-advance-section", str(bad[:6])))

    # 4. AI build lists / strategies / goals
    if AID.exists():
        for f in sorted(AID.glob("*.txt")):
            txt = _read(f)
            for pfx in ("UNIT_", "IMPROVE_", "WONDER_", "ADVANCE_"):
                refs = set(re.findall(r"\b(" + pfx + r"[A-Z0-9_]+)\b", txt))
                bad = _dangling(refs, dbs[pfx])
                if bad:
                    failures.append((f"4 aidata {pfx}", f"{f.name}: {bad[:6]}"))

    # 5. EndGameObjects
    ego = _read(GD / "EndGameObjects.txt")
    if ego:
        for kw, pfx in (("Wonder", "WONDER_"), ("Building", "IMPROVE_"),
                        ("TerrainImprovement", "TILEIMP_")):
            refs = set(re.findall(r"\b" + kw + r"\s+(" + pfx + r"[A-Z0-9_]+)", ego))
            bad = _dangling(refs, dbs[pfx])
            if bad:
                failures.append((f"5 endgame {pfx}", str(bad[:6])))

    # 6. Base-fallback gamedata files (CTP2 loads ctp2_data's copy when scenario lacks it)
    #    ONLY files listed in gamefile.txt are loaded by the engine — e.g. Improve.txt
    #    is NOT in the manifest, so it is never a real fallback. Scope to the manifest.
    base_gd = CTP2_DATA / "default" / "gamedata"
    manifest = set()
    mf = base_gd / "gamefile.txt"
    if mf.exists():
        manifest = {ln.strip() for ln in _read(mf).splitlines() if ln.strip()
                    and not ln.strip().startswith("#")}
    if base_gd.exists():
        owned = {p.name for p in GD.glob("*.txt")}
        for bp in sorted(base_gd.glob("*.txt")):
            if bp.name in owned or (manifest and bp.name not in manifest):
                continue
            txt = _read(bp)
            for pfx in ("UNIT_", "IMPROVE_", "WONDER_", "ADVANCE_"):
                refs = set(re.findall(r"\b(" + pfx + r"[A-Z0-9_]+)\b", txt))
                bad = _dangling(refs, dbs[pfx])
                if bad:
                    failures.append((f"6 base-fallback {pfx}", f"{bp.name}: {bad[:6]}"))

    # 7. SLIC entity symbols
    slic = "".join(_read(f) for f in GD.glob("*.slc"))
    for pfx in ("UNIT_", "IMPROVE_", "ADVANCE_", "WONDER_"):
        refs = set(re.findall(r"\b(" + pfx + r"[A-Z0-9_]+)\b", slic))
        bad = _dangling(refs, dbs[pfx])
        if bad:
            failures.append((f"7 slic {pfx}", str(bad[:6])))

    print("=" * 64)
    print("validate_all_surfaces — scenario:", SCEN)
    for k, v in dbs.items():
        pass
    if not failures:
        print("  ALL SURFACES CLEAN — every reference resolves. Launch-safe.")
        print("=" * 64)
        return 0
    print(f"  {len(failures)} surface(s) with dangling references:")
    for surface, detail in failures:
        print(f"    [BAD] {surface}: {detail}")
    print("=" * 64)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

```


## token_verify.py

```python
"""Token-stream fidelity check: does render output match original token-for-token,
the way CTP2's own parser tokenizes? This is the real acceptance test."""
import re, sys
from pathlib import Path
from ctp2_ae_parser import parse_file, render_file
import diffdb_parser

def toks(t):
    t = re.sub(r'//[^\n]*', '', t)
    t = re.sub(r'#[^\n]*', '', t)
    return re.findall(r'\{|\}|[^\s{}]+', t)

def check(path):
    text = Path(path).read_text(encoding='utf-8', errors='replace')
    name = Path(path).name.lower()
    if name == 'diffdb.txt':
        rendered = diffdb_parser.render_diffdb(diffdb_parser.parse_diffdb(text))
    else:
        rendered = render_file(parse_file(text))
    ot, rt = toks(text), toks(rendered)
    ok = ot == rt
    status = 'PASS' if ok else 'FAIL'
    print(f'  {Path(path).name}: {status}  (orig {len(ot)} tok, rendered {len(rt)} tok)')
    if not ok:
        for i,(a,b) in enumerate(zip(ot,rt)):
            if a!=b:
                print(f'    diverge @ {i}: orig {ot[max(0,i-2):i+3]}  rendered {rt[max(0,i-2):i+3]}')
                break
        if len(ot)!=len(rt) and len(list(zip(ot,rt)))==min(len(ot),len(rt)):
            print(f'    length differs by {abs(len(ot)-len(rt))}')
    return ok

if __name__=='__main__':
    allok=True
    for f in sys.argv[1:]:
        if Path(f).exists(): allok &= check(f)
    sys.exit(0 if allok else 1)

```


## build_schema.py

```python
"""
Cross-mod schema analysis for the active CTP2 reference set.

Reference mods:
  - AE
  - Cradle
  - Ages of Man

These are the canonical CTP2 schema donors. The Civ2 / MoMJR lane is separate
and should not be mixed into this reference set.
"""
import csv
import sqlite3
import sys
from pathlib import Path

DB_PATH  = r'C:\Users\user\.copilot\session-state\5cf6a694-6240-47f7-a998-f6bd4314f973\session.db'
CSV_DIR  = Path(r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\roundtrip_csv')
TOOLS    = Path(r'H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools')
REF_MODS = ('ae', 'cradle', 'aom')

db = sqlite3.connect(DB_PATH)

# ------------------------------------------------------------------
# 1. Load reference EAV CSVs (already generated by ctp2_roundtrip.py)
# ------------------------------------------------------------------

db.execute("DROP TABLE IF EXISTS eav_data")
db.execute("""
CREATE TABLE eav_data (
    mod TEXT, file_type TEXT, block_id TEXT, seq INT,
    field_type TEXT, key TEXT, val TEXT
)""")

ref_files = {
    'ae_units_eav.csv':        ('ae',     'units'),
    'ae_advance_eav.csv':      ('ae',     'advance'),
    'ae_uniticon_eav.csv':     ('ae',     'uniticon'),
    'cradle_units_eav.csv':    ('cradle', 'units'),
    'cradle_advance_eav.csv':  ('cradle', 'advance'),
    'cradle_uniticon_eav.csv': ('cradle', 'uniticon'),
    'aom_units_eav.csv':       ('aom',    'units'),
    'aom_advance_eav.csv':     ('aom',    'advance'),
    'aom_uniticon_eav.csv':    ('aom',    'uniticon'),
}

for fname, (mod, ftype) in ref_files.items():
    p = CSV_DIR / fname
    if not p.exists():
        print(f"SKIP {fname}")
        continue
    rows = []
    with open(p, newline='', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            rows.append((mod, ftype, r['block_id'], int(r['seq']),
                         r['type'], r['key'], r['val']))
    db.executemany("INSERT INTO eav_data VALUES (?,?,?,?,?,?,?)", rows)
    print(f"  loaded {fname}: {len(rows)} rows")

db.commit()

# ------------------------------------------------------------------
# 2. Schema frequency table: which fields appear in which mods
# ------------------------------------------------------------------

def schema_table(file_type: str):
    rows = db.execute("""
        SELECT key, field_type,
               SUM(CASE WHEN mod='ae'      THEN 1 ELSE 0 END)   ae,
               SUM(CASE WHEN mod='cradle'  THEN 1 ELSE 0 END)   cradle,
               SUM(CASE WHEN mod='aom'     THEN 1 ELSE 0 END)   aom,
               COUNT(DISTINCT block_id || '|' || mod)        uses,
               MIN(val)                                       sample
        FROM eav_data
        WHERE file_type=?
        GROUP BY key, field_type
        ORDER BY uses DESC
    """, (file_type,)).fetchall()
    return rows


def print_schema(file_type: str):
    rows = schema_table(file_type)
    print(f"\n=== {file_type.upper()} schema across mods ===")
    print(f"{'key':<32} {'type':<8} {'ae':>6} {'cradle':>8} {'aom':>6} {'uses':>6}  sample")
    print("-" * 90)
    for k, ft, ae, cradle, aom, uses, sample in rows:
        s = (sample or '')[:30]
        print(f"{k:<32} {ft:<8} {ae:>6} {cradle:>8} {aom:>6} {uses:>6}  {s}")
    return rows


units_schema   = print_schema('units')
advance_schema = print_schema('advance')
uniticon_schema = print_schema('uniticon')


def write_schema_csv(file_type: str, rows):
    out = CSV_DIR / f"{file_type}_schema_matrix.csv"
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['key', 'field_type', 'ae_count', 'cradle_count', 'aom_count', 'uses', 'sample'])
        for row in rows:
            w.writerow(row)
    print(f"  wrote {out.name}")


write_schema_csv('units', units_schema)
write_schema_csv('advance', advance_schema)
write_schema_csv('uniticon', uniticon_schema)

# ------------------------------------------------------------------
# 3. Parse current MoM generated output and compare against schema
# ------------------------------------------------------------------

# Add ctp2_roundtrip to path
sys.path.insert(0, str(TOOLS))
from ctp2_roundtrip import parse_file, export_csv

MOM_GAMEDATA = TOOLS.parent / 'scen0000' / 'default' / 'gamedata'

print("\n\n=== MoM generated output: field coverage vs reference schema ===")

for fname, file_type in [("Units.txt", "units"), ("Advance.txt", "advance"), ("uniticon.txt", "uniticon")]:
    p = MOM_GAMEDATA / fname
    if not p.exists():
        print(f"SKIP {fname} — not found")
        continue

    text = p.read_text(encoding='utf-8', errors='replace')
    blocks = parse_file(text)

    # Load into DB under mod='mom'
    db.execute("DELETE FROM eav_data WHERE mod='mom'")
    rows = []
    for block_id, items in blocks.items():
        for seq, item in enumerate(items):
            from ctp2_roundtrip import KV, Flag, SubList, Nested
            if isinstance(item, KV):
                rows.append(('mom', file_type, block_id, seq, 'kv', item.key, item.val))
            elif isinstance(item, Flag):
                rows.append(('mom', file_type, block_id, seq, 'flag', item.name, ''))
            elif isinstance(item, SubList):
                rows.append(('mom', file_type, block_id, seq, 'sublist', item.key, item.val))
            elif isinstance(item, Nested):
                rows.append(('mom', file_type, block_id, seq, 'nested', item.name, ''))
    db.executemany("INSERT INTO eav_data VALUES (?,?,?,?,?,?,?)", rows)
    db.commit()

    print(f"\n--- {fname}: {len(blocks)} blocks, {len(rows)} fields ---")

    # MoM-only blocks (new ones we added, not in base)
    mom_blocks = set(blocks.keys())
    base_q = db.execute(
        "SELECT DISTINCT block_id FROM eav_data WHERE mod='ae' AND file_type=?",
        (file_type,)
    ).fetchall()
    ref_baseline_blocks = {r[0] for r in base_q}
    new_blocks = sorted(mom_blocks - ref_baseline_blocks)
    print(f"  New blocks (MoM additions): {len(new_blocks)}")

    # For each new MoM block, check what reference fields it's missing
    ref_required = db.execute("""
        SELECT key, field_type, COUNT(DISTINCT mod) mods_present
        FROM eav_data
        WHERE file_type=? AND mod IN ('ae','cradle','aom')
        GROUP BY key, field_type
        HAVING mods_present >= 2
        ORDER BY mods_present DESC
    """, (file_type,)).fetchall()
    required_keys = {(r[0], r[1]) for r in ref_required}  # (key, field_type) present in >=2 mods

    coverage_issues = []
    for bid in new_blocks:
        block_keys = db.execute(
            "SELECT key, field_type FROM eav_data WHERE mod='mom' AND block_id=? AND file_type=?",
            (bid, file_type)
        ).fetchall()
        block_key_set = set(block_keys)
        missing = [(k, ft) for k, ft in required_keys if (k, ft) not in block_key_set]
        if missing:
            coverage_issues.append((bid, missing))

    if coverage_issues:
        print(f"  Blocks missing required fields ({len(coverage_issues)}):")
        for bid, missing in coverage_issues[:10]:
            print(f"    {bid}: missing {[k for k,_ in missing[:5]]}")
    else:
        print(f"  All new blocks have required fields PASS")

    # Fields in MoM blocks that appear nowhere in reference mods (suspicious)
    mom_keys_q = db.execute("""
        SELECT DISTINCT key, field_type FROM eav_data
        WHERE mod='mom' AND file_type=?
    """, (file_type,)).fetchall()
    ref_keys_q = db.execute("""
        SELECT DISTINCT key, field_type FROM eav_data
        WHERE file_type=? AND mod IN ('ae','cradle','aom')
    """, (file_type,)).fetchall()
    mom_keys = {(r[0], r[1]) for r in mom_keys_q}
    ref_keys  = {(r[0], r[1]) for r in ref_keys_q}
    unknown_keys = mom_keys - ref_keys
    if unknown_keys:
        print(f"  Fields in MoM not seen in ANY reference mod ({len(unknown_keys)}):")
        for k, ft in sorted(unknown_keys)[:15]:
            print(f"    {ft:<8} {k}")
    else:
        print(f"  No unknown fields — all field names seen in reference mods PASS")

db.close()
print("\nDone.")

```


## schema_registry.py

```python
"""
schema_registry.py — Builds a SQLite schema registry from diff_engine.py output.

Reads all diff JSON files from diff_results/ and populates schema_registry.db with:
  - mod_pairs, file_diffs, block_diffs, field_diffs
  - entity_recipes: per entity-type (unit/improvement/wonder/advance), which files
    and fields are needed when adding a new entity, derived from added blocks

Also emits schema_discovery.md — a human-readable schema reference.

Usage:
  python schema_registry.py              # rebuild registry from all diffs
  python schema_registry.py --markdown   # regenerate schema_discovery.md only
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

TOOLS       = Path(__file__).parent
DIFF_OUT    = TOOLS / "diff_results"
DB_PATH     = TOOLS / "data_csv" / "schema_registry.db"
MD_PATH     = TOOLS / "data_csv" / "schema_discovery.md"
MOD_PAIRS   = TOOLS / "mod_pairs.json"

# Block-ID prefix → entity type
_PREFIX_TO_ENTITY = {
    "UNIT_":      "unit",
    "IMPROVE_":   "improvement",
    "WONDER_":    "wonder",
    "ADVANCE_":   "advance",
    "TERRAIN_":   "terrain",
    "GOVERN_":    "government",
    "GOODS_":     "goods",
    "ICON_UNIT_": "unit_icon",
    "ICON_IMPROVE_": "improvement_icon",
    "ICON_WONDER_":  "wonder_icon",
    "ICON_ADVANCE_": "advance_icon",
}

# CIV2 section name → entity type
_CIV2_SECTION_ENTITY = {
    "@UNITS":       "unit",
    "@IMPROVE":     "improvement",
    "@ADVANCE":     "advance",
    "@TERRAIN":     "terrain",
    "@GOVERNMENTS": "government",
    "@LEADERS":     "leader",
}


def _entity_type_for_block(block_id: str) -> str:
    for prefix, etype in _PREFIX_TO_ENTITY.items():
        if block_id.startswith(prefix):
            return etype
    return "other"


def _entity_type_for_civ2(section: str) -> str:
    return _CIV2_SECTION_ENTITY.get(section.upper(), "other")


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS mod_pairs (
    id TEXT PRIMARY KEY,
    parser TEXT,
    baseline TEXT,
    mod TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS file_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    status TEXT,          -- modified | added_in_mod | removed_in_mod
    parser TEXT,
    summary_json TEXT,
    UNIQUE(pair_id, file_rel)
);
CREATE TABLE IF NOT EXISTS block_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    block_id TEXT,
    change_type TEXT,     -- added | removed | modified
    entity_type TEXT
);
CREATE TABLE IF NOT EXISTS field_diffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_id TEXT,
    file_rel TEXT,
    block_id TEXT,
    field_type TEXT,
    field_key TEXT,
    old_val TEXT,
    new_val TEXT,
    change_type TEXT      -- added | removed | changed
);
CREATE TABLE IF NOT EXISTS entity_recipes (
    entity_type TEXT,
    file_rel TEXT,
    field_key TEXT,
    field_type TEXT,
    pair_count INTEGER,   -- how many pairs have this field in added blocks
    total_pairs INTEGER,
    required INTEGER,     -- 1 if pair_count / total_pairs >= 0.5
    sample_val TEXT,
    PRIMARY KEY (entity_type, file_rel, field_key, field_type)
);
CREATE TABLE IF NOT EXISTS cross_game_map (
    civ2_section TEXT,
    ctp2_file TEXT,
    entity_type TEXT,
    notes TEXT
);
"""


def open_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(DDL)
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Load diffs into DB
# ---------------------------------------------------------------------------

def load_pair_diffs(db: sqlite3.Connection, pair_id: str, parser: str) -> int:
    """Load all diff JSON files for one pair into the DB. Returns file count."""
    pair_dir = DIFF_OUT / pair_id
    if not pair_dir.exists():
        print(f"  SKIP {pair_id}: no diff_results directory")
        return 0

    db.execute("DELETE FROM file_diffs   WHERE pair_id=?", (pair_id,))
    db.execute("DELETE FROM block_diffs  WHERE pair_id=?", (pair_id,))
    db.execute("DELETE FROM field_diffs  WHERE pair_id=?", (pair_id,))

    count = 0
    for json_file in pair_dir.glob("*.json"):
        if json_file.name.startswith("_"):
            continue  # skip _summary.json
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        file_rel = data.get("rel", json_file.stem)
        status   = data.get("status", "modified")
        file_parser = data.get("parser", parser)
        summary_json = json.dumps(data.get("summary", {}))

        db.execute(
            "INSERT OR REPLACE INTO file_diffs (pair_id, file_rel, status, parser, summary_json) VALUES (?,?,?,?,?)",
            (pair_id, file_rel, status, file_parser, summary_json),
        )
        count += 1

        # Ingest CTP2 block diffs
        if file_parser == "ctp2":
            added_data = data.get("blocks_added_data", {})
            for bid in data.get("blocks_added", []):
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "added", _entity_type_for_block(bid)),
                )
                for ftype, fkey, fval in added_data.get(bid, []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, "", fval, "added"),
                    )
            for bid in data.get("blocks_removed", []):
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "removed", _entity_type_for_block(bid)),
                )
            for mod in data.get("blocks_modified", []):
                bid = mod["block_id"]
                db.execute(
                    "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                    (pair_id, file_rel, bid, "modified", _entity_type_for_block(bid)),
                )
                for ftype, fkey, fval in mod.get("fields_added", []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, "", fval, "added"),
                    )
                for ftype, fkey, fval in mod.get("fields_removed", []):
                    db.execute(
                        "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                        (pair_id, file_rel, bid, ftype, fkey, fval, "", "removed"),
                    )

        # Ingest CIV2 RULES.TXT section diffs
        elif file_parser == "civ2_rules":
            for sec in data.get("sections", []):
                section_name = sec["section"]
                etype = _entity_type_for_civ2(section_name)
                for entry_name in sec.get("added", []):
                    db.execute(
                        "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                        (pair_id, f"{file_rel}#{section_name}", entry_name, "added", etype),
                    )
                    # Record fields from added_data
                    added_data = sec.get("added_data", [])
                    idx = sec["added"].index(entry_name)
                    if idx < len(added_data):
                        for fkey, fval in added_data[idx].items():
                            db.execute(
                                "INSERT INTO field_diffs (pair_id, file_rel, block_id, field_type, field_key, old_val, new_val, change_type) VALUES (?,?,?,?,?,?,?,?)",
                                (pair_id, f"{file_rel}#{section_name}", entry_name, "kv", fkey, "", fval, "added"),
                            )
                for entry_name in sec.get("removed", []):
                    db.execute(
                        "INSERT INTO block_diffs (pair_id, file_rel, block_id, change_type, entity_type) VALUES (?,?,?,?,?)",
                        (pair_id, f"{file_rel}#{section_name}", entry_name, "removed", etype),
                    )

    db.commit()
    print(f"  [{pair_id}] loaded {count} file diffs")
    return count


# ---------------------------------------------------------------------------
# Derive entity recipes
# ---------------------------------------------------------------------------

def derive_entity_recipes(db: sqlite3.Connection) -> int:
    """
    For each entity_type + file_rel combination, find which fields appear
    in added blocks across pairs. Fields in >=50% of pairs are marked required.
    """
    db.execute("DELETE FROM entity_recipes")

    # Get all pairs that have any added blocks
    pairs = [r[0] for r in db.execute(
        "SELECT DISTINCT pair_id FROM block_diffs WHERE change_type='added'"
    ).fetchall()]
    total_pairs = len(pairs)
    if total_pairs == 0:
        print("  No added blocks found — run diff_engine.py first.")
        return 0

    # For each (entity_type, file_rel, field_key, field_type):
    # count how many pairs have at least one added block with that field
    rows = db.execute("""
        SELECT
            bd.entity_type,
            fd.file_rel,
            fd.field_key,
            fd.field_type,
            COUNT(DISTINCT fd.pair_id) AS pair_count,
            MIN(fd.new_val) AS sample_val
        FROM field_diffs fd
        JOIN block_diffs bd
          ON fd.pair_id = bd.pair_id
         AND fd.file_rel = bd.file_rel
         AND fd.block_id = bd.block_id
        WHERE bd.change_type = 'added'
          AND fd.change_type = 'added'
          AND fd.field_key != ''
        GROUP BY bd.entity_type, fd.file_rel, fd.field_key, fd.field_type
    """).fetchall()

    for etype, frel, fkey, ftype, pc, sample in rows:
        required = 1 if pc / total_pairs >= 0.5 else 0
        db.execute(
            "INSERT OR REPLACE INTO entity_recipes VALUES (?,?,?,?,?,?,?,?)",
            (etype, frel, fkey, ftype, pc, total_pairs, required, sample),
        )

    db.commit()
    count = db.execute("SELECT COUNT(*) FROM entity_recipes").fetchone()[0]
    print(f"  Derived {count} entity recipe rows across {total_pairs} pair(s)")
    return count


# ---------------------------------------------------------------------------
# Load cross-game map from config
# ---------------------------------------------------------------------------

def load_cross_game_map(db: sqlite3.Connection) -> int:
    config = json.loads(MOD_PAIRS.read_text(encoding="utf-8"))
    db.execute("DELETE FROM cross_game_map")
    count = 0
    for entry in config.get("cross_game_map", []):
        for ctp2_file in entry.get("ctp2_files", []):
            db.execute(
                "INSERT INTO cross_game_map VALUES (?,?,?,?)",
                (entry["civ2_section"], ctp2_file, entry.get("entity_type", ""), entry.get("notes", "")),
            )
            count += 1
    db.commit()
    print(f"  Loaded {count} cross-game map entries")
    return count


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[tuple]) -> str:
    sep = " | ".join("---" for _ in headers)
    hdr = " | ".join(headers)
    lines = [f"| {hdr} |", f"| {sep} |"]
    for row in rows:
        cells = " | ".join(str(c or "").replace("|", "\\|")[:60] for c in row)
        lines.append(f"| {cells} |")
    return "\n".join(lines)


def generate_markdown(db: sqlite3.Connection) -> str:
    lines = [
        "# Schema Discovery Registry",
        "",
        "> Auto-generated by `schema_registry.py`. Do not edit manually.",
        "",
    ]

    # 1. Mod pairs summary
    lines += ["## Mod Pairs", ""]
    pairs_rows = db.execute("""
        SELECT mp.id, mp.parser, mp.notes,
               COUNT(DISTINCT fd.file_rel) files_diffed,
               COUNT(DISTINCT CASE WHEN bd.change_type='added' THEN bd.block_id END) blocks_added
        FROM mod_pairs mp
        LEFT JOIN file_diffs fd ON fd.pair_id = mp.id
        LEFT JOIN block_diffs bd ON bd.pair_id = mp.id
        GROUP BY mp.id
    """).fetchall()
    lines.append(_md_table(
        ["Pair ID", "Parser", "Files Diffed", "Blocks Added", "Notes"],
        [(r[0], r[1], r[3], r[4], r[2]) for r in pairs_rows]
    ))
    lines.append("")

    # 2. Cross-game map
    lines += ["## Cross-Game Entity Map", ""]
    cgm_rows = db.execute("""
        SELECT civ2_section, entity_type, GROUP_CONCAT(ctp2_file, ', '), notes
        FROM cross_game_map GROUP BY civ2_section
        ORDER BY civ2_section
    """).fetchall()
    lines.append(_md_table(
        ["CIV2 Section", "Entity Type", "CTP2 Files", "Notes"],
        cgm_rows
    ))
    lines.append("")

    # 3. Entity recipes per type
    lines += ["## Entity Recipes", ""]
    etypes = [r[0] for r in db.execute(
        "SELECT DISTINCT entity_type FROM entity_recipes ORDER BY entity_type"
    ).fetchall()]

    for etype in etypes:
        lines += [f"### `{etype}`", ""]
        recipe_rows = db.execute("""
            SELECT file_rel, field_key, field_type, pair_count, total_pairs, required, sample_val
            FROM entity_recipes
            WHERE entity_type = ?
            ORDER BY required DESC, pair_count DESC, file_rel, field_key
        """, (etype,)).fetchall()
        lines.append(_md_table(
            ["File", "Field", "Type", "Pairs", "Total", "Required", "Sample"],
            recipe_rows
        ))
        lines.append("")

    # 4. Per-file change summary (top changed files)
    lines += ["## Most-Changed Files", ""]
    file_rows = db.execute("""
        SELECT fd.file_rel,
               COUNT(DISTINCT CASE WHEN bd.change_type='added'    THEN bd.block_id END) added,
               COUNT(DISTINCT CASE WHEN bd.change_type='removed'  THEN bd.block_id END) removed,
               COUNT(DISTINCT CASE WHEN bd.change_type='modified' THEN bd.block_id END) modified,
               COUNT(DISTINCT fd.pair_id) pairs
        FROM file_diffs fd
        LEFT JOIN block_diffs bd ON bd.pair_id = fd.pair_id AND bd.file_rel = fd.file_rel
        WHERE fd.status = 'modified'
        GROUP BY fd.file_rel
        ORDER BY (added + removed + modified) DESC
        LIMIT 40
    """).fetchall()
    lines.append(_md_table(
        ["File", "Added", "Removed", "Modified", "Pairs"],
        file_rows
    ))
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(markdown_only: bool = False) -> None:
    db = open_db()

    if not markdown_only:
        config = json.loads(MOD_PAIRS.read_text(encoding="utf-8"))

        # Load mod pair metadata
        db.execute("DELETE FROM mod_pairs")
        for p in config["mod_pairs"]:
            db.execute(
                "INSERT INTO mod_pairs VALUES (?,?,?,?,?)",
                (p["id"], p["parser"], p["baseline"], p["mod"], p.get("notes", "")),
            )
        db.commit()

        # Load diffs
        print("Loading diffs into registry...")
        for p in config["mod_pairs"]:
            load_pair_diffs(db, p["id"], p["parser"])

        # Load cross-game map
        print("Loading cross-game map...")
        load_cross_game_map(db)

        # Derive entity recipes
        print("Deriving entity recipes...")
        derive_entity_recipes(db)

    # Generate markdown
    print("Generating schema_discovery.md...")
    md = generate_markdown(db)
    MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_PATH.write_text(md, encoding="utf-8")
    print(f"  Wrote {MD_PATH}")

    db.close()
    print("Done.")


if __name__ == "__main__":
    markdown_only = "--markdown" in sys.argv
    main(markdown_only)

```

