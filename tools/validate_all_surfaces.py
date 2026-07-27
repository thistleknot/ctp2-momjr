#!/usr/bin/env python
"""validate_all_surfaces.py — assert every CTP2 reference surface resolves.

CTP2 validates entity references from MANY surfaces (load- and run-time), not one.
This checks them ALL against the actual DB files so a build is provably launch-clean
before the game is started — ending the relaunch-per-error loop. Driven by the live
data files (the parser's source of truth), per dimension_inventory.md.

Surfaces checked:
  1. Data-file gating fields (EnableAdvance/ObsoleteAdvance/Prerequisites/
     AddAdvance/RemoveAdvance -> Advance DB; UpgradeTo -> Unit DB)
  2. Great Library <L:DATABASE_<TYPE>,<TOKEN>> links: (a) <TYPE> is a real engine
     database name (else greatlibrary.cpp:352 crash), (b) <TOKEN> resolves (all dims)
  3. Great Library advance sections [ADVANCE_X_GAMEPLAY|HISTORICAL|PREREQ|STATISTICS]
  4. AI build lists / strategies (aidata/*.txt)
  5. EndGameObjects.txt (victory wonders/buildings/tile improvements)
  6. Base-fallback gamedata files (ctp2_data files NOT overridden by the scenario)
  7. SLIC entity symbols (UNIT_/IMPROVE_/ADVANCE_/WONDER_ in *.slc)
  8. Improve/Wonder double-load guard (no concept in BOTH buildings.txt & Wonder.txt)
  9. UI textures: (a) every .ldl texture ref resolves loose or in a .zfs archive,
     (b) no corrupt loose TGA shadowing archive art (Blt16To16 crash class)

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


def _strip_slic_comments(txt: str) -> str:
    """Drop // and /* */ comments so prose idents are not read as references."""
    txt = re.sub(r"/\*.*?\*/", " ", txt, flags=re.S)
    return re.sub(r"//[^\n]*", "", txt)


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

# The ONLY database names the engine's hypertext parser accepts, verbatim from
# greatlibrary.cpp s_database_names[]. Any <L:DATABASE_X,...> whose X is not in this
# set makes Get_Database_From_Name() hit Assert(false) at greatlibrary.cpp:352 ->
# 0xC0000005 the instant that entry renders (e.g. the MoM DATABASE_IMPROVEMENTS typo,
# which should be DATABASE_BUILDINGS/DATABASE_WONDERS). DEFAULT/SEARCH are valid engine
# names but never appear in authored links.
_ENGINE_DB_NAMES = {
    "DEFAULT", "UNITS", "BUILDINGS", "WONDERS", "ADVANCES", "TERRAIN",
    "CONCEPTS", "GOVERNMENTS", "TILE_IMPROVEMENTS", "RESOURCE", "ORDERS", "SEARCH",
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
    settle = re.compile(r"\bSettleBuilding\s+(IMPROVE_[A-Z0-9_]+)")
    for f in sorted(GD.glob("*.txt")):
        txt = _read(f)
        bad = _dangling(set(gate.findall(txt)), dbs["ADVANCE_"])
        if bad:
            failures.append(("1 gating-advance", f"{f.name}: {bad[:6]}"))
        badu = _dangling(set(upg.findall(txt)), dbs["UNIT_"])
        if badu:
            failures.append(("1 gating-unit", f"{f.name}: {badu[:6]}"))
        badb = _dangling(set(settle.findall(txt)), dbs["IMPROVE_"])
        if badb:
            failures.append(("1 gating-building", f"{f.name}: {badb[:6]}"))

    # 2. Great Library DATABASE links
    gltext = _read(ENG / "Great_Library.txt") + _read(ENG / "WAW_Great_Library.txt")
    # 2a. Engine-DB-name guard: any <L:DATABASE_X,...> whose X is not a real engine
    # database name hits Assert(false) at greatlibrary.cpp:352 -> 0xC0000005 the moment
    # the entry renders. The per-type loop below only inspects KNOWN names, so an unknown
    # name (the DATABASE_IMPROVEMENTS typo) was silently skipped and shipped. Catch it here.
    linknames = set(re.findall(r"<[Ll]:DATABASE_([A-Z0-9_]+)\s*,", gltext))
    bad_names = sorted(n for n in linknames if n not in _ENGINE_DB_NAMES)
    if bad_names:
        failures.append(("2 gl-link BAD-DB-NAME (crash: greatlibrary.cpp:352)", str(bad_names[:6])))
    # 2b. Token resolution within each known DB type.
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
    #    Comments are stripped first: the SLIC compiler never sees them, so an
    #    ident quoted in prose is not a reference. Without this, mom_func.slc's
    #    own doc comment (`CityHasBuilding(city, "IMPROVE_X")`, an illustrative
    #    placeholder) reported as a dangling ref and made the run NOT
    #    launch-clean forever.
    slic = "".join(_strip_slic_comments(_read(f)) for f in GD.glob("*.slc"))
    for pfx in ("UNIT_", "IMPROVE_", "ADVANCE_", "WONDER_"):
        refs = set(re.findall(r"\b(" + pfx + r"[A-Z0-9_]+)\b", slic))
        bad = _dangling(refs, dbs[pfx])
        if bad:
            failures.append((f"7 slic {pfx}", str(bad[:6])))

    # 8. Improve/Wonder double-load guard: no concept may exist as BOTH an
    # IMPROVE_ block (buildings.txt) AND a WONDER_ block (Wonder.txt). The engine
    # then loads the same concept into two databases -> conflicting indices ->
    # Build Manager render corruption (the "fuglies"; same class as the Improve.txt
    # double-load fixed in 7afc935). See lessons_learned.md.
    imp_stems = {i[len("IMPROVE_"):] for i in dbs["IMPROVE_"]}
    won_stems = {w[len("WONDER_"):] for w in dbs["WONDER_"]}
    overlap = sorted(imp_stems & won_stems)
    if overlap:
        failures.append(("8 improve/wonder double-load", str(overlap[:8])))

    # 9. UI-texture integrity. The engine resolves every texture named in an .ldl
    # from a loose graphics file first, else from a .zfs archive; a name in neither
    # is a launch failure, and a corrupt loose file SHADOWING a good archive copy is
    # worse: it feeds the blitter a mis-sized surface -> Blt16To16 0xC0000005 (the
    # 2026-07-09 turn-0 crash: 120x120 desc=0x21 placeholder uptg20e.tga shadowing
    # the real InitProgressWindow sheet in pic555.zfs). Stock CTP2 art never sets
    # the TGA top-left-origin bit (desc & 0x20), so that bit marks an impostor.
    import struct
    ldl_files = list((CTP2_DATA / "default" / "uidata" / "layouts").glob("*.ldl")) \
              + list((CTP2_DATA / "english" / "uidata" / "layouts").glob("*.ldl")) \
              + list(SCEN.rglob("*.ldl"))
    tex_re = re.compile(r'"([A-Za-z0-9_\-.]+\.(?:tga|bmp|pcx|jpg))"', re.I)
    refs = set()
    for f in ldl_files:
        refs |= {m.lower() for m in tex_re.findall(_read(f))}
    loose = {}
    for root in (CTP2_DATA / "default" / "graphics", CTP2_DATA / "english" / "graphics",
                 SCEN / "default" / "graphics", SCEN / "english" / "graphics"):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file():
                    loose.setdefault(p.name.lower(), p)
    zfs_blobs = [p.read_bytes().upper() for p in CTP2_DATA.rglob("*.zfs")]

    def _in_zfs(name):
        stem = name.rsplit(".", 1)[0].upper().encode("ascii", "ignore")
        return bool(stem) and any(stem in blob for blob in zfs_blobs)

    # 9a. No NEW dangling .ldl texture reference. The stock install itself carries
    # ~240 ldl refs that resolve nowhere (never-instantiated blocks; the engine
    # skips them), so an absolute check drowns in baseline noise. Instead compare
    # against the recorded stock baseline and fail only on regressions — i.e. a
    # MoM-side edit introducing a texture ref that resolves neither loose nor in
    # a .zfs archive. str_tbl_ldl_* are string-table tokens, not filenames.
    baseline_path = Path(__file__).parent / "ldl_texture_baseline.txt"
    baseline = {ln.strip().lower() for ln in _read(baseline_path).splitlines()
                if ln.strip() and not ln.startswith("#")}
    dangling_tex = {r for r in refs if r not in loose and not _in_zfs(r)
                    and not r.startswith("str_tbl_ldl_")}
    new_dangling = sorted(dangling_tex - baseline)
    if new_dangling:
        failures.append(("9a ldl-texture NEW unresolved", str(new_dangling[:8])))

    # 9b. No corrupt loose TGA. NOTE: desc=0x21 (top-left origin) is LEGITIMATE
    # here — patch_ctp2_images.py extracts archive .rim entries as top-origin TGAs
    # byte-identical to stock art (verified sha1 vs pic555.zfs 2026-07-09), so the
    # desc byte is NOT an impostor signal. Corruption = truncated header or a
    # type-2 uncompressed payload smaller than its declared width*height*bpp.
    bad_loose = []
    for name, p in sorted(loose.items()):
        if not name.endswith(".tga"):
            continue
        raw = p.read_bytes()
        if len(raw) < 18:
            # 0-byte/short files: known baseline orphan UPCB47X.tga (badTGA.txt,
            # referenced nowhere) is tolerated; anything else is a real defect.
            if name != "upcb47x.tga":
                bad_loose.append(f"{name} (truncated {len(raw)}B)")
            continue
        idlen, _, imgtype = raw[0], raw[1], raw[2]
        w, h, bpp = struct.unpack_from("<HHB", raw, 12)
        if imgtype == 2 and len(raw) < 18 + idlen + w * h * (bpp // 8):
            bad_loose.append(f"{name} (short payload: {len(raw)}B < {w}x{h}x{bpp}bpp)")
    if bad_loose:
        failures.append(("9b ldl-texture corrupt-loose", str(bad_loose[:8])))

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
