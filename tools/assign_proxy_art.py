"""Populate proxy art for every csv-defined entity missing its own icon TGA.

Purpose:
    Merged super-mods pull in units/advances/improvements that have no icon art
    on disk, so the generator falls back to the UPLG001 placeholder (ugly grey
    box). This borrows real art: for each entity whose ICON_<X>.tga is absent
    from the scenario pictures dir, copy a deterministic proxy from the same
    dimension's real-art pool, named exactly as the generator expects
    (sanitize(name)). Run AFTER copying the base scenario, BEFORE ctp2_generator
    — the generator's icon reconcile then points at the now-present TGA.

    Deterministic (sorted target -> sorted pool round-robin) so a regen is
    byte-stable. Entities that already have real art are skipped, so a base mod
    whose visible entities all ship art (e.g. MoM) gets zero proxies.

Usage:
    assign_proxy_art.py --scenario <scen0000 dir> --csv <merged csv dir>

Desc-byte guard: proxies are copied verbatim from already-normalized source
TGAs (desc byte 0x00), so the GL SourceList crash guard is preserved.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from pathlib import Path

DIMENSIONS = (
    ("units.csv", "UNIT_", "ICON_UNIT_"),
    ("advances.csv", "ADVANCE_", "ICON_ADVANCE_"),
    ("improvements.csv", "IMPROVE_", "ICON_IMPROVE_"),
)


def sanitize(name: str) -> str:
    """Identifier sanitizer — MUST match ctp2_generator.sanitize exactly."""
    s = name.upper().replace(" ", "_").replace("'", "").replace("-", "_")
    return re.sub(r"[^A-Z0-9_]", "", s)


def pool_for(pictures: Path, icon_prefix: str) -> list[Path]:
    """Real TGAs already on disk for this dimension, sorted for determinism."""
    hits = [p for p in pictures.iterdir()
            if p.is_file() and p.name.upper().startswith(icon_prefix)
            and p.suffix.lower() == ".tga"]
    return sorted(hits, key=lambda p: p.name.upper())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--art-dir", type=Path, default=None,
                        help="dir of REAL icon TGAs (e.g. built by "
                             "build_unit_icon_art.py); installed into the "
                             "scenario pictures dir FIRST — overwriting any "
                             "proxy — so the proxy pass only fills what real "
                             "art doesn't cover")
    args = parser.parse_args()
    pictures = args.scenario / "default" / "graphics" / "pictures"
    if not pictures.exists():
        raise SystemExit(f"no pictures dir under {args.scenario}")

    if args.art_dir and args.art_dir.exists():
        installed = 0
        for tga in sorted(args.art_dir.glob("*.tga")):
            shutil.copy2(tga, pictures / tga.name)
            installed += 1
        print(f"  real art: installed {installed} TGA(s) from {args.art_dir}")

    # Theme buckets for UNIT proxies: a donor icon is classified by inferring
    # a sphere from its own unit name; a target unit draws only from its own
    # sphere's bucket (falling back to the human/neutral bucket, then the full
    # pool). Prevents the round-robin handing a dragon to 'Engineers' or a
    # treasure chest to a line infantryman.
    from assign_unit_factions import infer_sphere

    def donor_theme(icon_path: Path, icon_prefix: str) -> str:
        name = icon_path.stem[len(icon_prefix):].replace("_", " ").title()
        sphere = infer_sphere(name)
        return sphere if sphere != "neutral" else "neutral"

    unit_sphere: dict[str, str] = {}
    tax_path = args.csv / "unit_factions.csv"
    if tax_path.exists():
        with tax_path.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                s = (r.get("sphere") or "").strip()
                unit_sphere[r["unit_id"]] = s if s in (
                    "life", "nature", "death", "chaos", "sorcery") else "neutral"

    # icon TGA filename -> civ2 category, for the advance proxy buckets below.
    advance_category: dict[str, str] = {}
    adv_category_of_name: dict[str, str] = {}
    adv_csv = args.csv / "advances.csv"
    if adv_csv.exists():
        with adv_csv.open(newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                nm = (r.get("name") or "").split(";")[0].strip()
                if not nm:
                    continue
                cat = (r.get("category") or "").split(";")[0].strip()
                adv_category_of_name[nm] = cat
                advance_category[f"ICON_ADVANCE_{sanitize(nm)}.TGA"] = cat

    total_proxied = 0
    for fname, prefix, icon_prefix in DIMENSIONS:
        csv_path = args.csv / fname
        if not csv_path.exists():
            continue
        pool = pool_for(pictures, icon_prefix)
        if not pool:
            print(f"  [skip] {icon_prefix}: no real-art pool to borrow from")
            continue
        buckets: dict[str, list[Path]] = {}
        if fname == "units.csv":
            for donor in pool:
                buckets.setdefault(donor_theme(donor, icon_prefix), []).append(donor)
        elif fname == "advances.csv":
            # Advance art is CATEGORY art, not per-advance art: the 96 shipped
            # ICON_ADVANCE_*.tga collapse to exactly 11 distinct images, one per
            # civ2 @CIVILIZE category (0=Military 1=Economic 2=Social 3=Academic
            # 4=Applied ...). Currency, Banking and Trade -- all category 1 --
            # are byte-identical. A blind round-robin therefore hands a new
            # economic advance whatever cell the counter lands on, which is a
            # visible mismatch in the Great Library for no reason: the control
            # plane already states the category. Bucket by it, same shape as the
            # unit sphere buckets above.
            for donor in pool:
                buckets.setdefault(advance_category.get(donor.name.upper(), ""),
                                   []).append(donor)

        # Existing target ids on disk (skip — real or already-proxied art).
        have = {p.name.upper() for p in pictures.iterdir() if p.is_file()}
        with csv_path.open(newline="", encoding="utf-8-sig") as fh:
            names = [r["name"].strip() for r in csv.DictReader(fh)
                     if (r.get("name") or "").strip()]

        missing = []
        for name in sorted(set(names)):
            tga = f"{icon_prefix}{sanitize(name)}.tga"
            if tga.upper() not in have:
                missing.append((name, tga))

        counters: dict[str, int] = {}
        for name, tga in missing:
            donor_pool = pool
            if fname == "units.csv":
                theme = unit_sphere.get(f"{prefix}{sanitize(name)}", "neutral")
                donor_pool = buckets.get(theme) or buckets.get("neutral") or pool
                key = theme
            elif fname == "advances.csv":
                cat = adv_category_of_name.get(name, "")
                donor_pool = buckets.get(cat) or pool
                key = f"{icon_prefix}{cat}"
            else:
                key = icon_prefix
            i = counters.get(key, 0)
            counters[key] = i + 1
            shutil.copy2(donor_pool[i % len(donor_pool)], pictures / tga)
            total_proxied += 1
        print(f"  {icon_prefix}: {len(missing)} proxied from {len(pool)} real art(s)")

    print(f"proxy art: {total_proxied} icon(s) borrowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
