"""Great Library descriptions: a GAMEPLAY and a HISTORICAL blurb for every element.

Thesis
------
Every Great Library article has two halves, and they have different truth
conditions. GAMEPLAY says what the thing *does* -- costs, yields, combat
numbers, what unlocks it. That is a fact about the database, so hand-writing it
guarantees it goes stale the first time a cost is retuned. HISTORICAL says where
the thing comes from in the fiction. No amount of database introspection
produces that, so it has to be authored.

So the two halves are sourced differently:

    GAMEPLAY    derived, every run, from the live DB blocks the generator just
                wrote. Never authored unless a row explicitly overrides it.
    HISTORICAL  authored once in the control plane
                (momjr_csv/gl_descriptions.csv), keyed by element id.

Necessary conditions
--------------------
- Runs LAST in the generator's Great Library pass. Earlier passes seed stub
  sections ("X is a Master of Magic unit."); this pass must overwrite them, so
  it cannot use the `if key not in sections` guard the earlier passes use.
- Derivation reads the in-memory registry, not disk. The generator has not
  necessarily saved Units.txt when this runs.
- Filler detection is shared with the gate (gate_gl_descriptions.py) so that
  "what counts as missing" has exactly one definition.

Invariants
----------
- Deterministic: same DB in, same bytes out. Blocks are visited in sorted order.
- Authored text always wins over derived text.
- Never invents numbers. If a field is absent from the block it is omitted from
  the sentence rather than defaulted.

Failure modes
-------------
- An element live in the DB but absent from the csv keeps a derived GAMEPLAY and
  an empty HISTORICAL -- the gate fails, loudly, rather than the article
  silently rendering blank in game.
"""
from __future__ import annotations

import csv
import re
from collections import OrderedDict
from pathlib import Path

CSV_NAME = "gl_descriptions.csv"

# prefix -> (dimension name, scenario-relative DB file, GL database name)
DIMENSIONS = OrderedDict([
    ("UNIT_",       ("units",       "default/gamedata/Units.txt",     "DATABASE_UNITS")),
    ("IMPROVE_",    ("buildings",   "default/gamedata/buildings.txt", "DATABASE_BUILDINGS")),
    ("WONDER_",     ("wonders",     "default/gamedata/Wonder.txt",    "DATABASE_WONDERS")),
    ("ADVANCE_",    ("advances",    "default/gamedata/Advance.txt",   "DATABASE_ADVANCES")),
    ("TILEIMP_",    ("tileimp",     "default/gamedata/tileimp.txt",   "DATABASE_TILE_IMPROVEMENTS")),
    ("GOVERNMENT_", ("governments", "default/gamedata/govern.txt",    "DATABASE_GOVERNMENTS")),
    ("CONCEPT_",    ("concepts",    None,                             "DATABASE_CONCEPTS")),
    ("TERRAIN_",    ("terrain",     "default/gamedata/terrain.txt",   "DATABASE_TERRAIN")),
    ("ORDER_",      ("orders",      None,                             "DATABASE_ORDERS")),
])

# Dimensions whose elements are split across more than one DB file. Terrain is
# the only one: the tiles live in terrain.txt and the special resources that sit
# on them live in goods.txt, but both use the TERRAIN_ prefix and both get their
# own Great Library article.
EXTRA_SOURCES = {"terrain": ["default/gamedata/goods.txt"]}

# Stub text the earlier generator passes emit. Anything matching is "not a
# description" for both this module and the gate.
_FILLER_PATTERNS = [
    re.compile(r"^$"),
    re.compile(r"^.{0,59}$", re.S),
    re.compile(r"^.* is a .* (unit|city improvement|wonder)\.$", re.S),
    re.compile(r"^.* serves in the armies of .*\.$", re.S),
    re.compile(r"^.* currently uses runtime .* data .*$", re.S),
    re.compile(r"^Summary of .*\.$", re.S),
]


def strip_markup(text: str) -> str:
    """Reduce a GL section to the prose a player would actually read."""
    if text is None:
        return ""
    # Every hypertext control tag: <L:db,ident> links, <e> end, and the single
    # letter formatting tags <c:r,g,b> <h:r,g,b> <t:font> <p:n> <b:n> <i:n>
    # <s:n> <u:n> that ctp2_HyperTextBox::ParseText consumes without drawing.
    return re.sub(r"<e>", "", re.sub(r"<[A-Za-z]:[^>]*>", "", text)).strip()


# The exact stub an earlier pass writes when it believes an element has no
# enabling advance. Matched rather than compared so trailing whitespace and the
# stray full stop in the original template do not defeat the reconciliation.
_NO_PREREQ = re.compile(r"^\s*No advance required\.?\s*$", re.I)


def is_filler(text: str) -> bool:
    """True when a section carries no real description.

    The single definition of 'missing', shared with gate_gl_descriptions.py so
    the gate and the writer can never disagree about what needs filling.
    """
    body = strip_markup(text)
    return any(p.match(body) for p in _FILLER_PATTERNS)


def scan_blocks(text: str) -> "OrderedDict[str, str]":
    """Split a CTP2 database file into top-level `IDENT { ... }` blocks."""
    blocks: "OrderedDict[str, str]" = OrderedDict()
    for m in re.finditer(r"^([A-Z][A-Z0-9_]*)\s*\{(.*?)^\}", text, re.M | re.S):
        blocks[m.group(1)] = m.group(2)
    return blocks


def parse_block(block: str) -> tuple[dict, set]:
    """Return (scalar fields, bare flags) for one block body.

    Nested sub-blocks are skipped: their keys are not element-level facts and
    including them would put e.g. a sound effect id into a combat sentence.
    """
    fields, flags = {}, set()
    depth = 0
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        depth += line.count("{") - line.count("}")
        if depth > 0 or line.startswith("}") or "{" in line:
            continue
        line = line.split(";", 1)[0].strip()
        if not line or line.endswith(":"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            fields.setdefault(parts[0], parts[1].strip())
        elif not parts[0].endswith(":"):
            flags.add(parts[0])
    # Kept so a deriver can reach into a nested sub-block (terrain hides every
    # yield inside EnvBase). Not a real field: the leading underscores keep it
    # out of any lookup a deriver does by DB key name.
    fields["__raw__"] = block
    return fields, flags


def humanize(ident: str, prefix: str) -> str:
    return ident[len(prefix):].replace("_", " ").title()


def _name(ident: str, prefix: str, strings) -> str:
    entry = getattr(strings, "entries", {}).get(ident)
    return entry if entry else humanize(ident, prefix)


_GL_LINK = re.compile(r"<L:DATABASE_[A-Z0-9_]+,([A-Z0-9_]+)>([^<]+)<e>")


def _harvest_labels(gl_library) -> dict:
    """Map ident -> the display name the Great Library index actually shows.

    gl_str is not the authority here: several terrain idents have no gl_str
    entry at all, so the derived prose fell back to humanize() and called
    TERRAIN_BROWN_MOUNTAIN "Brown Mountain" inside an article the index titles
    "Desert Mountain". The stock GL articles carry the real label in their own
    link stubs, so read it back out of them.

    A section whose entire body is one link IS that element's stub and is
    canonical. Links appearing inside prose are only a fallback, and there
    first-wins is wrong: prose pluralises ("found in Desert Mountains") while
    the PREREQ "Location:" lists carry the singular. Vote instead — most
    frequent spelling wins, ties broken by the shorter string, which picks the
    singular over the plural.
    """
    labels = {}
    fallback = {}
    for text in (getattr(gl_library, "sections", None) or {}).values():
        hits = _GL_LINK.findall(text or "")
        if len(hits) == 1 and _GL_LINK.sub("", text or "").strip() == "":
            labels[hits[0][0]] = hits[0][1].strip()
        else:
            for ident, label in hits:
                counts = fallback.setdefault(ident, {})
                label = label.strip()
                counts[label] = counts.get(label, 0) + 1
    for ident, counts in fallback.items():
        best = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
        labels.setdefault(ident, best[0][0])
    return labels


def _link(db: str, ident: str, label: str) -> str:
    return f"<L:{db},{ident}>{label}<e>"


def _int(fields: dict, key: str):
    try:
        return int(str(fields.get(key, "")).split()[0])
    except (ValueError, IndexError):
        return None


# --------------------------------------------------------------------------
# Derivers. Each returns GAMEPLAY prose, or "" when the dimension carries no
# numbers worth stating (those dimensions are authored-only).
# --------------------------------------------------------------------------

_UNIT_TRAITS = OrderedDict([
    ("CanSettle",        "can found cities"),
    ("CanBombard",       "can bombard from a distance"),
    ("CanEntrench",      "can entrench for a defensive bonus"),
    ("CanExpel",         "can expel enemy units without killing them"),
    ("CanPillage",       "can pillage tile improvements"),
    ("CanPirate",        "can raid trade routes"),
    ("ExertsMartialLaw", "exerts martial law in a city"),
    ("CanInvestigate",   "can investigate cities"),
    ("CanEstablishEmbassy", "can establish embassies"),
    ("CanStealTechnology", "can steal technology"),
    ("CanInciteRevolution", "can incite revolution"),
    ("CanAssassinate",   "can assassinate"),
    ("CanCarry",         "can carry other units"),
    ("IsFlanker",        "flanks in combat"),
])


def _gameplay_unit(ident, fields, flags, ctx) -> str:
    name = ctx["name"](ident, "UNIT_")
    atk, dfn = _int(fields, "Attack"), _int(fields, "Defense")
    hp, fp = _int(fields, "MaxHP"), _int(fields, "Firepower")
    cost = _int(fields, "ShieldCost")
    move = _int(fields, "MaxMovePoints")
    vision = _int(fields, "VisionRange")

    # Written without a verb agreeing with the unit name: MoM names are a mix of
    # singular and plural ("Spearmen", "Wraith"), so "X fights" is wrong half the
    # time. Leading with the stat line sidesteps it entirely.
    bits = []
    stats = []
    if atk is not None:
        stats.append(f"attack {atk}")
    if dfn is not None:
        stats.append(f"defense {dfn}")
    if hp is not None:
        stats.append(f"{hp} hit points")
    if fp is not None:
        stats.append(f"firepower {fp}")
    if stats:
        bits.append(f"{name}: " + ", ".join(stats) + ".")
    if move is not None:
        step = move / 100.0
        bits.append(
            f"Moves {step:g} tile{'s' if step != 1 else ''} per turn"
            + (f" and sees {vision} tiles." if vision is not None else ".")
        )
    if cost is not None:
        bits.append(f"Costs {cost} production to build.")
    adv = fields.get("EnableAdvance")
    if adv:
        bits.append("Requires " + _link("DATABASE_ADVANCES", adv,
                                        ctx["name"](adv, "ADVANCE_")) + ".")
    traits = [d for f, d in _UNIT_TRAITS.items() if f in flags]
    if traits:
        bits.append("This unit " + _join(traits) + ".")
    return " ".join(bits)


def _gameplay_building(ident, fields, flags, ctx) -> str:
    name = ctx["name"](ident, "IMPROVE_")
    cost = _int(fields, "ProductionCost")
    if cost is None:
        cost = _int(fields, "ShieldCost")
    upkeep = _int(fields, "Upkeep")

    bits = []
    if cost is not None:
        line = f"{name} costs {cost} production to build"
        if upkeep:
            line += f" and {upkeep} gold per turn to maintain"
        elif upkeep == 0:
            line += " and costs nothing to maintain"
        bits.append(line + ".")
    adv = fields.get("EnableAdvance")
    if adv:
        bits.append("It becomes available with " + _link(
            "DATABASE_ADVANCES", adv, ctx["name"](adv, "ADVANCE_")) + ".")
    effects = _effect_sentences(fields)
    if effects:
        bits.append("In the city that builds it, " + _join(effects) + ".")
    return " ".join(bits)


def _gameplay_wonder(ident, fields, flags, ctx) -> str:
    name = ctx["name"](ident, "WONDER_")
    cost = _int(fields, "ProductionCost")
    if cost is None:
        cost = _int(fields, "ShieldCost")
    bits = []
    if cost is not None:
        bits.append(f"{name} costs {cost} production, and only one may exist in the world.")
    else:
        bits.append(f"Only one {name} may exist in the world.")
    adv = fields.get("EnableAdvance")
    if adv:
        bits.append("It becomes available with " + _link(
            "DATABASE_ADVANCES", adv, ctx["name"](adv, "ADVANCE_")) + ".")
    effects = _effect_sentences(fields)
    if effects:
        bits.append("It " + _join(effects) + ".")
    return " ".join(bits)


# Effect fields worth stating, in the order a player cares about them.
_EFFECTS = OrderedDict([
    ("FoodPercent",       "increases food by {pct}%"),
    ("ProductionPercent", "increases production by {pct}%"),
    ("CommercePercent",   "increases commerce by {pct}%"),
    ("SciencePercent",    "increases science by {pct}%"),
    ("GoldPercent",       "increases gold by {pct}%"),
    ("HappyInc",          "adds {n} happiness"),
    ("DefenseBonus",      "raises defense by {pct}%"),
    ("CrimeCoef",         "changes crime by {pct}%"),
    ("PollutionCoef",     "changes pollution by {pct}%"),
    ("MaxPopIncrement",   "raises the population limit by {n}"),
])


def _effect_sentences(fields: dict) -> list:
    out = []
    for key, tmpl in _EFFECTS.items():
        raw = fields.get(key)
        if raw is None:
            continue
        try:
            val = float(str(raw).split()[0])
        except (ValueError, IndexError):
            continue
        if val == 0:
            continue
        out.append(tmpl.format(pct=f"{val * 100:g}" if abs(val) <= 1 else f"{val:g}",
                               n=f"{val:g}"))
    return out


def _gameplay_advance(ident, fields, flags, ctx) -> str:
    name = ctx["name"](ident, "ADVANCE_")
    cost = _int(fields, "Cost")
    bits = []
    prereqs = [p for p in str(fields.get("Prerequisites", "")).split() if p.startswith("ADVANCE_")]
    # Prerequisites can repeat across lines; scan the raw block for all of them.
    prereqs = ctx["prereqs"].get(ident, prereqs)
    if prereqs:
        bits.append("Researching " + name + " requires " + _join(
            [_link("DATABASE_ADVANCES", p, ctx["name"](p, "ADVANCE_")) for p in prereqs]) + ".")
    else:
        bits.append(f"{name} needs no prior research and is available from the first turn.")
    if cost is not None:
        bits.append(f"It costs {cost} science to complete.")

    unlocks = ctx["unlocks"].get(ident, {})
    for kind, db, prefix, label in (
        ("units", "DATABASE_UNITS", "UNIT_", "the unit"),
        ("buildings", "DATABASE_BUILDINGS", "IMPROVE_", "the city improvement"),
        ("wonders", "DATABASE_WONDERS", "WONDER_", "the wonder"),
        ("tileimp", "DATABASE_TILE_IMPROVEMENTS", "TILEIMP_", "the tile improvement"),
    ):
        items = sorted(unlocks.get(kind, []))
        if not items:
            continue
        plural = label if len(items) == 1 else label.replace("the ", "the ") + "s"
        bits.append("It enables " + plural + " " + _join(
            [_link(db, i, ctx["name"](i, prefix)) for i in items]) + ".")
    if not unlocks:
        bits.append("It unlocks no units or buildings directly, and serves as a step toward later research.")
    return " ".join(bits)


def _gameplay_tileimp(ident, fields, flags, ctx) -> str:
    # Terraform tileimps have no string entry and no GL stub of their own, so
    # humanize() would name them after the raw ident ("Terraform Brown
    # Mountain") inside an article the index titles "Terraform Desert
    # Mountain". The terrain they produce does carry the canonical label.
    terra = fields.get("TerraformTerrain")
    if terra:
        name = "Terraform " + ctx["name"](terra, "TERRAIN_")
    else:
        name = ctx["name"](ident, "TILEIMP_")
    bits = [f"{name} is built on the map by public works rather than in a city."]
    adv = fields.get("EnableAdvance")
    if adv:
        bits.append("It becomes available with " + _link(
            "DATABASE_ADVANCES", adv, ctx["name"](adv, "ADVANCE_")) + ".")
    return " ".join(bits)


def _gameplay_government(ident, fields, flags, ctx) -> str:
    name = ctx["name"](ident, "GOVERNMENT_")
    bits = []
    adv = fields.get("EnableAdvance")
    if adv:
        bits.append(f"{name} becomes available with " + _link(
            "DATABASE_ADVANCES", adv, ctx["name"](adv, "ADVANCE_")) + ".")
    else:
        bits.append(f"{name} is a form of government.")
    for key, tmpl in (("MaxScienceRate", "Science may be set as high as {v}%."),
                      ("MaxProductionLevel", "Production may be pushed to {v}%."),
                      ("MartialLawUnits", "Up to {v} units may impose martial law."),
                      ("TooManyCitiesThreshold", "Unhappiness begins past {v} cities."),
                      ("EmpireSizeBonus", "It carries an empire size bonus of {v}.")):
        v = _int(fields, key)
        if v is not None:
            bits.append(tmpl.format(v=v))
    return " ".join(bits)


def _subblock(block: str, name: str) -> dict:
    """Fields of a named nested block, e.g. EnvBase inside a terrain block.

    parse_block deliberately skips nested blocks, but terrain keeps every number
    that matters inside EnvBase, so the deriver has to reach in for it.
    """
    m = re.search(r"^\s*" + name + r"\s*\{(.*?)^\s*\}", block, re.S | re.M)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        parts = line.strip().split()
        if len(parts) == 2:
            out[parts[0]] = parts[1]
    return out


def _gameplay_terrain(ident, fields, flags, ctx) -> str:
    """Terrain tiles and the special resources that sit on them.

    Two block shapes share the TERRAIN_ prefix: tiles (terrain.txt, numbers
    nested in EnvBase) and goods (goods.txt, numbers at the top level). The
    presence of Probability is what tells them apart.
    """
    name = ctx["name"](ident, "TERRAIN_")
    if "Probability" in fields:  # a special resource
        yields = []
        for key, label in (("Food", "food"), ("Production", "production"),
                           ("Shield", "production"), ("Gold", "gold")):
            v = _int(fields, key)
            if v:
                yields.append(f"{v} {label}")
        bits = [f"{name} is a special resource."]
        if yields:
            bits.append("A tile carrying it produces " + _join(yields) + " per turn.")
        try:
            pct = float(fields.get("Probability", "")) * 100.0
            bits.append(f"It appears on roughly {pct:g}% of eligible tiles.")
        except ValueError:
            pass
        return " ".join(bits)

    env = _subblock(fields.get("__raw__", ""), "EnvBase")
    # Zero yields are stated rather than omitted: "no food" is the single most
    # decision-relevant fact about a tile, and dropping it left tiles like
    # Desert and Tundra with a one-clause article that read as a stub.
    yields = []
    for key, label in (("Food", "food"), ("Shield", "production"), ("Gold", "gold")):
        v = _int(env, key) or 0
        yields.append(f"{v} {label}" if v else f"no {label}")
    bits = [f"A {name} tile produces " + _join(yields) + " per turn."]
    mv = _int(env, "Movement")
    if mv is not None:
        bits.append(f"Costs {mv / 100.0:g} movement to cross.")
    # Terrain Defense is a fraction of the unit's own defence (hills 0.5,
    # mountains 1.0), not a percentage point value, so it has to be scaled and
    # read as a float -- an int parse silently drops every value below 1.
    try:
        dfn = float(env.get("Defense", "0"))
    except ValueError:
        dfn = 0.0
    if dfn:
        bits.append(f"Defenders here gain {dfn * 100:g}%.")
    return " ".join(bits)


DERIVERS = {
    "terrain": _gameplay_terrain,
    "units": _gameplay_unit,
    "buildings": _gameplay_building,
    "wonders": _gameplay_wonder,
    "advances": _gameplay_advance,
    "tileimp": _gameplay_tileimp,
    "governments": _gameplay_government,
}


def _join(items) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f" and {items[-1]}"


# --------------------------------------------------------------------------
# Control plane
# --------------------------------------------------------------------------

def load_authored(csv_dir: Path) -> dict:
    """Read gl_descriptions.csv -> {element: {'gameplay':…, 'historical':…}}."""
    path = Path(csv_dir) / CSV_NAME
    if not path.is_file():
        return {}
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ident = (row.get("element") or "").strip()
            if not ident:
                continue
            out[ident] = {
                "gameplay": (row.get("gameplay") or "").strip(),
                "historical": (row.get("historical") or "").strip(),
            }
    return out


def collect_elements(load_text) -> dict:
    """Gather live element blocks per dimension.

    `load_text(rel)` returns the current text of a scenario file, or None. It is
    a callback so the generator can pass in-memory (unsaved) content while the
    gate passes what is on disk.
    """
    live = {}
    for prefix, (dimension, rel, _db) in DIMENSIONS.items():
        if rel is None:
            continue
        blocks = {}
        for source in [rel] + EXTRA_SOURCES.get(dimension, []):
            text = load_text(source)
            if not text:
                continue
            blocks.update({i: b for i, b in scan_blocks(text).items()
                           if i.startswith(prefix) and not _is_hidden(b)})
        if blocks:
            live[dimension] = (prefix, blocks)
    return live


def _is_hidden(block: str) -> bool:
    """True for elements the Great Library never lists.

    NoIndex / GLHidden are the engine's own 'do not show this' flags. Describing
    them would be work no player can ever read, and would make the gate demand
    prose for base-game units the mod deliberately suppressed.
    """
    return bool(re.search(r"^\s*(NoIndex|GLHidden)\s*$", block, re.M))


def _build_context(live: dict, strings) -> dict:
    """Reverse indexes the derivers need: what each advance unlocks, and prereqs."""
    unlocks: dict = {}
    for dimension in ("units", "buildings", "wonders", "tileimp"):
        if dimension not in live:
            continue
        _prefix, blocks = live[dimension]
        for ident, block in blocks.items():
            fields, _flags = parse_block(block)
            adv = fields.get("EnableAdvance")
            if adv:
                unlocks.setdefault(adv, {}).setdefault(dimension, set()).add(ident)

    prereqs = {}
    if "advances" in live:
        _prefix, blocks = live["advances"]
        for ident, block in blocks.items():
            found = []
            for line in block.splitlines():
                line = line.split(";", 1)[0].strip()
                if line.startswith("Prerequisites"):
                    found += [t for t in line.split()[1:] if t.startswith("ADVANCE_")]
            # An advance listing itself is a generator artifact, not a dependency.
            prereqs[ident] = [p for p in dict.fromkeys(found) if p != ident]

    return {
        "unlocks": unlocks,
        "prereqs": prereqs,
        "name": lambda ident, prefix: _name(ident, prefix, strings),
    }


# Body text colour for every Great Library section.
#
# ctp2_HyperTextBox::InitCommon hardcodes m_hyperColor = RGB(50,50,50) and
# never reads the LDL fontcolor* attributes, so the dark grey CANNOT be changed
# from ctp_template.ldl or greatlibrary.ldl -- measured: a widthpix marker in
# the same template applied while the colour did not. The one supported
# override is the in-text <c:r,g,b> tag the parser handles. MoM's article pane
# is a dark brown pattern, so grey-on-brown is nearly unreadable; near-white
# with a black shadow reads cleanly.
_TEXT_COLOR = "<c:245,240,225><h:0,0,0>"


def apply_text_color(gl_library, tag: str = _TEXT_COLOR) -> int:
    """Prefix every section with the body-colour tag. Idempotent."""
    changed = 0
    for key, text in list((getattr(gl_library, "sections", None) or {}).items()):
        text = text or ""
        if text.startswith(tag) or not text.strip():
            continue
        # Drop any colour tag a previous run wrote before re-stamping, so the
        # output stays byte-stable when the constant changes.
        text = re.sub(r"^(?:<[ch]:\d+,\d+,\d+>)+", "", text)
        gl_library.sections[key] = tag + text
        changed += 1
    return changed


def apply_descriptions(load_text, gl_library, gl_strings, csv_dir, verbose=True) -> dict:
    """Write GAMEPLAY and HISTORICAL for every live element. Overwrites filler.

    Returns a report: {'written': n, 'derived': n, 'authored': n, 'missing': [...]}
    """
    authored = load_authored(csv_dir)
    live = collect_elements(load_text)
    ctx = _build_context(live, gl_strings)
    labels = _harvest_labels(gl_library)
    _base_name = ctx["name"]
    ctx["name"] = lambda ident, prefix: labels.get(ident) or _base_name(ident, prefix)

    written = derived = auth = 0
    missing = []

    # Authored-only dimensions have no DB file; take their element list from the
    # csv itself so concepts and orders can be described at all.
    csv_only = {}
    for ident in authored:
        for prefix, (dimension, rel, _db) in DIMENSIONS.items():
            if rel is None and ident.startswith(prefix):
                csv_only.setdefault(dimension, (prefix, {}))[1][ident] = ""
    for dimension, payload in csv_only.items():
        live.setdefault(dimension, payload)

    for dimension in sorted(live):
        prefix, blocks = live[dimension]
        deriver = DERIVERS.get(dimension)
        for ident in sorted(blocks):
            fields, flags = parse_block(blocks[ident])
            row = authored.get(ident, {})

            gameplay = row.get("gameplay") or ""
            if gameplay:
                auth += 1
            elif deriver:
                gameplay = deriver(ident, fields, flags, ctx)
                derived += 1
            historical = row.get("historical") or ""
            if historical:
                auth += 1

            for suffix, content in (("_GAMEPLAY", gameplay), ("_HISTORICAL", historical)):
                key = ident + suffix
                if not content:
                    if is_filler(gl_library.sections.get(key, "")):
                        missing.append(key)
                    continue
                if gl_library.sections.get(key) != content:
                    gl_library.sections[key] = content
                    written += 1

            # PREREQ is written by an earlier pass, before the improvement
            # advances are patched in, so a handful of elements end up claiming
            # "No advance required" in the same article whose GAMEPLAY names the
            # advance. Running last, the live DB is authoritative -- reconcile.
            enabler = fields.get("EnableAdvance")
            pkey = ident + "_PREREQ"
            if enabler and _NO_PREREQ.match(gl_library.sections.get(pkey, "")):
                label = ctx["name"](enabler, "ADVANCE_")
                gl_library.sections[pkey] = (
                    f"Requires:\n<L:DATABASE_ADVANCES,{enabler}>{label}<e>")
                written += 1

    recolored = apply_text_color(gl_library)
    if verbose:
        print(f"GL descriptions: {recolored} sections recoloured")
        print(f"GL descriptions: {written} sections written "
              f"({derived} derived, {auth} authored), {len(missing)} still missing")
    return {"written": written, "derived": derived, "authored": auth, "missing": sorted(missing)}
