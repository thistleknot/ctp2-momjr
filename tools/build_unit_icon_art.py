"""Build real unit ICON TGAs for a merged control plane from a Civ3 art archive.

Purpose:
    Merged super-mod units wear proxy icons (assign_proxy_art) until real art
    exists. This tool maps unit names to art in a Civ3 mod archive (CoMM3:
    HoMM3 creature roster), converts the matched art to CTP2 ICON format
    (160x120, uncompressed 16-bit RGB555, bottom-origin, desc byte 0x00 — the
    exact format of the shipped ICON_UNIT_*.tga files), and writes
    ICON_UNIT_<SANITIZED>.tga into a durable art dir that assign_proxy_art
    --art-dir installs ahead of the proxy pass.

    The name mapping is a CONTROL-PLANE STAGING SHEET (unit_art_map.csv in the
    csv dir, genre_mask pattern): generated on first run (token matcher +
    curated alias table), then owned by the reviewer — existing rows are never
    overwritten, only blank rows for newly merged units are filled in.

Preconditions:
    --csv dir has units.csv (name/source columns); --archive is a py7zr-readable
    7z whose listing contains COMM3/Art/... ; ffmpeg on PATH for .flc sources;
    Pillow importable.

Failure modes:
    SystemExit on missing inputs. Units with no mapping row are skipped (they
    keep proxy art). A mapped archive path that fails extraction/decoding logs
    and skips — never a partial TGA on disk.

Usage:
    build_unit_icon_art.py --csv <csv dir> --archive <CoMM3.7z> --out <art dir>
        [--real-art-dir <base pictures dir>] [--force]
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import py7zr
from PIL import Image

ICON_W, ICON_H = 160, 120

# Largest fraction of the 160x120 icon frame a unit's content may occupy. The
# bottom-UI preview draws this icon into a 96x72 box (controlpanel.ldl), so an
# icon whose content runs to the frame edge has no margin left and reads as
# oversized -- and anything protruding past the edge is simply cut off. 0.80
# matches the framing the SPRITE art already uses on the map. See fit_pad().
ICON_CONTENT_MAX_FRAC = 0.80

# Unit name (normalized) -> archive art key (normalized dir or pedia base name).
# Judgment calls mapping merged-mod creatures onto the HoMM3/CoMM3 roster;
# reviewable/overridable per row in unit_art_map.csv once generated.
ALIAS = {
    "faeriesprite": "elffairyb1",
    "elf": "elvenbowman",
    "elfarchers": "elvenbowman",
    "elfwarriors": "waywatcher",
    "rangers": "waywatcher",
    "elfriders": "greypegasus",
    "phoenix": "pheonixrecolor",
    "firebird": "firebird",
    "treefolk": "treeman",
    "lich": "undeadliche",
    "liches": "undeadliche",
    "ghost": "shadow2wightbrown",
    "dwarves": "longbeard",
    "berserkers": "craghack",
    "housecarls": "silverhelm",
    "witches": "charna",
    "sorcerer": "archmage",
    "druid": "enchanter",
    "mermen": "sirens",
    "merguards": "nagasentinel",
    "hawkmen": "harpym7",
    "eaglemen": "thunderbird",
    "nightriders": "wargrider",
    "cragwolves": "wargrider",
    "icedrake": "crystaldragon",
    "skydrake": "faeriedragonmed",
    "greatwyrm": "azuredragon",
    "greatdrake": "reddragon",
    "hellhound": "hellhound",
    "cavalry": "genericknight",
    "heavycavalry": "unicornknight",
    "crusader": "zealot",
    "swordsman": "italianfootknight",
    "pikeman": "aokpikeman",
    "pikemen": "aokpikeman",
    "crossbowman": "germancrossbow",
    "crossbowmen": "germancrossbow",
    "siegeengine": "catapultadv",
    "siegecatapult": "catapult",
    "bombard": "ballista",
    "tradecart": "wagon",
    "boat": "carrack2",
    "ship": "galleon",
    "waterairelementals": "waterelemental",
    "earthfireelementals": "fireelemental",
    "settlers": "dwarfsettler",
    "hobgoblin": "hobgoblinrider",
    "goblin": "goblinspearman",
    "goblins": "goblinspearman",
    "halfling": "halflinghm4",
    "wolfriders": "wargrider",
    # Visible-with-proxy batch (2026-07-16): shared art across sibling units is
    # deliberate (MoM shared-icon-group precedent).
    "peasant": "hobbitfarmhand",
    "roguethief": "darkelfassassin",
    "greatwizard": "archmage",
    "necromancer": "lichepriest",
    "frostgiant": "icegolem",
    "greateagles": "roc",
    "fellwraith": "greatershadow",
    "barrowwights": "shadow2wightbrown",
    "treeguards": "treeman",
    "enchpaladins": "unicornknight",
    "enchgiant": "giant",
    "enchogre": "ogremage",
    "changeling": "familiar",
    "unspeakablehorror": "beholder",
    "babayaga": "charna",
    "jackolantern": "impbrown",
    "tritonlegion": "naga",
    "longboat": "carrack2",
    "dragonboat": "piratefrigate",
    "shieldboat": "heavyfrigate",
    "ellida": "galleon",
    "skidbladnir": "shipoftheline",
    "crusaders": "zealot",
    "knightstemplar": "genericknight",
    "knighttemplar": "genericknight",
    "knightshosp": "italianfootknight",
    "cleric": "monk",
    "varangguard": "silverhelm",
    "trireme": "carrack2",
    "elitetrireme": "carrack2",
    "firetrireme": "carrack2",
    "quinquereme": "carrack2",
    "heptireme": "carrack2",
    "eliteheptireme": "carrack2",
    "earlygalley": "carrack2",
    "elitegalley": "carrack2",
    "caravel": "galleon",
    "ironclad": "shipoftheline",
    "transport": "heavyfrigate",
    "supplytrain": "wagon",
    "kingseye": "eyeofthemagi",
    "prophet": "monk",
    "lightinfantry": "aokpikeman",
    "medievalinfantry": "italianfootknight",
    "elitemedievalinfantry": "italianfootknight",
    "heavyinfantry": "italianfootknight",
    "hoplite": "aokpikeman",
    "elitepikemen": "aokpikeman",
    "hypaspists": "aokpikeman",
    "elitehypaspists": "aokpikeman",
    "pezhetairoi": "aokpikeman",
    "manatarms": "italianfootknight",
    "longbow": "archer",
    "elitelongbow": "archer",
    "feudalcavalry": "genericknight",
    "elitefeudalcavalry": "genericknight",
    "eliteheavycavalry": "unicornknight",
    "teutonicknight": "genericknight",
    "eliteteutonicknight": "genericknight",
    "belfroi": "catapultadv",
    "elitebelfroi": "catapultadv",
    "javelincavalryorcs": "wargrider",
    "horsemanelves": "silverpegasus",
    "horsemanrohan": "genericknight",
    "spearmanorcs": "goblinspearman",
    "warriororcs": "orc",
    "hopliteorcs": "goblinspearman",
    "hypaspistsorcs": "goblinspearman",
    "legionorcs": "hornedgrunt",
    "manatarmsorcs": "gnollknight",
    "pikemenorcs": "goblinspearman",
    "slingerorcs": "goblinspearman2",
    "archerorcs": "orc",
    "compositearcherorcs": "orcchieftan",
    "hwarriors": "hobgoblinrider",
    "engineers": "hgworker",
    "legion": "italianfootknight",
    "clubwarrior": "06warrior",
    "warrior": "06warrior",
}

# Archive entries that are scenery/artifacts/buildings, never unit portraits.
EXCL = re.compile(
    r"(?i)^(artft|artifact|d_|bgate|bguard|keymtent|abandoned|campfire|crystalcavern"
    r"|crypt|castle|conflux|archerstower|antimagic|art-|cover|chainlightning"
    r"|barbresource|altarsacrifice|alchem|spell|mono|monolith|gempond|goldmine"
    r"|orepit|sawmill|lavamountain|kelp|moat|tower$|.*moat$|.*tower$|gate)"
)


def sanitize(name: str) -> str:
    """Identifier sanitizer — MUST match ctp2_generator.sanitize exactly."""
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    return re.sub(r"[^A-Z0-9_]", "", s)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(s: str) -> set[str]:
    """Word tokens: split on separators and camelCase, singularized."""
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", s)
    out = set()
    for p in parts:
        p = p.lower()
        if len(p) < 3 or p.isdigit():
            continue
        out.add(p[:-1] if p.endswith("s") and len(p) > 3 else p)
    return out


def build_pools(names: list[str]) -> tuple[dict, dict]:
    """(pedia larges, unit-dir best flc) keyed by normalized art name."""
    ped: dict[str, str] = {}
    flcs: dict[str, list[str]] = {}
    for line in sorted(names, key=lambda l: ("old" in l.lower(), l)):
        p = line.split("/")
        if len(p) == 6 and p[2] == "Civilopedia" and p[4] == "Units":
            m = re.match(r"(?i)^(.*?)[-_]?(?:large|lg)(?:old)?\d*(?:old)?\.pcx$", p[5])
            if m and not EXCL.match(m.group(1)):
                ped.setdefault(norm(m.group(1)), line)
        if len(p) >= 5 and p[2] == "Units" and p[4].lower().endswith(".flc") \
                and not EXCL.match(p[3]):
            flcs.setdefault(p[3], []).append(line)

    def best(paths: list[str]) -> str:
        for pref in ("default", "fidget", "run", "attack", "victory"):
            for x in sorted(paths):
                if pref in x.split("/")[-1].lower():
                    return x
        return sorted(paths)[0]

    dirs = {norm(d): best(v) for d, v in flcs.items()}
    return ped, dirs


def match_unit(name: str, ped: dict, dirs: dict,
               ped_tokens: dict, dir_tokens: dict) -> tuple[str, str] | None:
    """Return (kind, archive_path) for a unit name, else None."""
    n = norm(name)
    keys = [n]
    if n in ALIAS:
        keys.insert(0, ALIAS[n])
    for k in keys:
        for cand in (k, k[:-1] if k.endswith("s") else k + "s",
                     k + "e", k[:-1] if k.endswith("e") else k):
            if cand in ped:
                return "pedia", ped[cand]
            if cand in dirs:
                return "flc", dirs[cand]
    # Token subset: every unit token appears in the candidate's token set.
    want = tokens(name)
    if not want:
        return None
    best = None
    for pool_tok, pool, kind in ((ped_tokens, ped, "pedia"),
                                 (dir_tokens, dirs, "flc")):
        for key, toks in pool_tok.items():
            if want <= toks:
                cand = (len(toks - want), 0 if kind == "pedia" else 1, kind, pool[key])
                if best is None or cand < best:
                    best = cand
    return (best[2], best[3]) if best else None


def cover_crop(im: Image.Image) -> Image.Image:
    """Scale to cover 160x120 then center-crop (portrait sources)."""
    scale = max(ICON_W / im.width, ICON_H / im.height)
    im = im.resize((max(1, round(im.width * scale)),
                    max(1, round(im.height * scale))), Image.LANCZOS)
    left = (im.width - ICON_W) // 2
    top = (im.height - ICON_H) // 2
    return im.crop((left, top, left + ICON_W, top + ICON_H))


def fit_pad(im: Image.Image, max_frac: float = 1.0) -> Image.Image:
    """
    Scale to fit inside 160x120, pad black (sprite-frame sources).

    Require:   max_frac in (0, 1] -- the largest fraction of the icon frame the
               image is allowed to occupy on either axis.
    Guarantee: returns a 160x120 RGB canvas with the image centred on it.
    Failure:   none; a max_frac of 1.0 reproduces the original fill-the-frame
               behaviour exactly.

    max_frac exists because of the OVER-ZOOM BUG (root-caused 2026-07-25). This
    was called as fit_pad(crop_to_content(im)): crop tight to the content, then
    scale that crop up until it fills 160x120. Every unit therefore rendered at
    the same 0.95 content extent regardless of its natural proportion -- measured
    across all 55 MoM icons, the height extent was EXACTLY 0.95 for every single
    one, while the same units' SPRITE art sat at a median 0.66. Two visible
    symptoms, one cause:
      * broad figures (GUARDIAN_SPIRIT) overran the bottom-UI preview box and
        clipped at the frame edge -- "too big for the unit preview ui";
      * thin figures with a protruding weapon (SPEARMEN) had the tip severed by
        the frame, leaving a floating sliver -- the icon no longer matched the
        map sprite, "the carpet doesn't match the drapes".
    ICON_CONTENT_MAX_FRAC leaves the frame margin the preview box needs, and
    keeps relative unit sizing intact instead of normalising it away.
    """
    scale = min(ICON_W * max_frac / im.width, ICON_H * max_frac / im.height)
    im = im.resize((max(1, round(im.width * scale)),
                    max(1, round(im.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGB", (ICON_W, ICON_H), (0, 0, 0))
    canvas.paste(im, ((ICON_W - im.width) // 2, (ICON_H - im.height) // 2))
    return canvas


def scrub_chroma(im: Image.Image) -> Image.Image:
    """Blacken Civ3 magenta/green chroma-key backgrounds."""
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b = px[x, y][:3]
            if (r > 200 and b > 200 and g < 90) or (g > 200 and r < 90 and b < 90):
                px[x, y] = (0, 0, 0)
    return im


def write_icon_tga(path: Path, im: Image.Image) -> None:
    """CTP2 ICON format: 160x120, type-2 16-bit RGB555, bottom-origin, desc 0x00."""
    im = im.convert("RGB")
    header = bytearray(18)
    header[2] = 2
    header[12:14] = ICON_W.to_bytes(2, "little")
    header[14:16] = ICON_H.to_bytes(2, "little")
    header[16] = 16
    header[17] = 0x00
    rows = []
    px = im.load()
    for y in range(ICON_H - 1, -1, -1):
        row = bytearray()
        for x in range(ICON_W):
            r, g, b = px[x, y]
            row += (((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)).to_bytes(2, "little")
        rows.append(bytes(row))
    path.write_bytes(bytes(header) + b"".join(rows))


def crop_to_content(im: Image.Image, margin: int = 4) -> Image.Image:
    """Crop to the non-black bounding box (FLC frames are a small sprite on a
    scrubbed background — without this the icon is a dot in a black field)."""
    bbox = im.convert("L").point(lambda v: 255 if v > 16 else 0).getbbox()
    if not bbox:
        return im
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(im.width, bbox[2] + margin)
    bottom = min(im.height, bbox[3] + margin)
    return im.crop((left, top, right, bottom))


def convert(kind: str, src: Path) -> Image.Image:
    if kind == "pedia":
        return cover_crop(Image.open(src).convert("RGB"))
    png = src.with_suffix(".png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                    "-frames:v", "1", str(png)], check=True)
    im = scrub_chroma(Image.open(png).convert("RGB"))
    return fit_pad(crop_to_content(im), ICON_CONTENT_MAX_FRAC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--real-art-dir", type=Path,
                        default=Path("Scenarios/mom/scen0000/default/graphics/pictures"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    units_csv = args.csv / "units.csv"
    if not units_csv.exists():
        raise SystemExit(f"{args.csv} has no units.csv")
    if not args.archive.exists():
        raise SystemExit(f"archive not found: {args.archive}")
    args.out.mkdir(parents=True, exist_ok=True)

    with py7zr.SevenZipFile(args.archive) as z:
        listing = z.getnames()
    ped, dirs = build_pools(listing)

    def _ped_base(path: str) -> str:
        """Cleaned pedia base name (large/lg suffix stripped) — tokenizing the
        raw filename glues the suffix onto the last word ('06warriorlarge')
        and silently kills token matches."""
        fname = path.split("/")[-1]
        m = re.match(r"(?i)^(.*?)[-_]?(?:large|lg)(?:old)?\d*(?:old)?\.pcx$", fname)
        return m.group(1) if m else fname.rsplit(".", 1)[0]

    ped_tokens = {k: tokens(_ped_base(v)) for k, v in ped.items()}
    dir_tokens = {k: tokens(v.split("/")[3]) for k, v in dirs.items()}

    with units_csv.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    have_real = {f.name.upper() for f in args.real_art_dir.iterdir()} \
        if args.real_art_dir.exists() else set()
    need = [r for r in rows
            if f"ICON_UNIT_{sanitize(r['name'])}.TGA" not in have_real]

    # Staging sheet: keep existing rows verbatim, fill only new/blank units.
    map_path = args.csv / "unit_art_map.csv"
    existing: dict[str, dict[str, str]] = {}
    if map_path.exists():
        with map_path.open(newline="", encoding="utf-8-sig") as fh:
            existing = {r["unit"]: r for r in csv.DictReader(fh)}
    sheet: list[dict[str, str]] = []
    auto = 0
    for r in need:
        row = existing.get(r["name"])
        if row is None or not row.get("archive_path"):
            hit = match_unit(r["name"], ped, dirs, ped_tokens, dir_tokens)
            row = {"unit": r["name"], "source": r["source"],
                   "kind": hit[0] if hit else "",
                   "archive_path": hit[1] if hit else ""}
            if hit:
                auto += 1
        sheet.append(row)
    with map_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["unit", "source", "kind", "archive_path"],
                           lineterminator="\r\n")
        w.writeheader()
        w.writerows(sheet)
    mapped = [r for r in sheet if r["archive_path"]]
    print(f"  unit_art_map.csv: {len(sheet)} unit(s) needing art, "
          f"{len(mapped)} mapped ({auto} auto-filled this run)")

    todo = [r for r in mapped
            if args.force or not (args.out / f"ICON_UNIT_{sanitize(r['unit'])}.tga").exists()]
    if not todo:
        print("  nothing to build (all mapped icons present; use --force to redo)")
        return 0
    wanted = {r["archive_path"] for r in todo}
    with tempfile.TemporaryDirectory() as tmp:
        with py7zr.SevenZipFile(args.archive) as z:
            z.extract(path=tmp, targets=sorted(wanted))
        built = failed = 0
        for r in sorted(todo, key=lambda r: r["unit"]):
            src = Path(tmp) / r["archive_path"]
            dst = args.out / f"ICON_UNIT_{sanitize(r['unit'])}.tga"
            try:
                write_icon_tga(dst, convert(r["kind"], src))
                built += 1
            except Exception as exc:  # skip bad member, never leave partial art
                if dst.exists():
                    dst.unlink()
                print(f"  [skip] {r['unit']}: {exc}")
                failed += 1
    print(f"  built {built} icon TGA(s) into {args.out} ({failed} skipped)")
    counts = Counter(r["kind"] for r in todo)
    print(f"  sources: {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
