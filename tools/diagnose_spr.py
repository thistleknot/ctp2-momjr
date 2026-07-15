"""
diagnose_spr.py  —  Discriminate invisible-unit root cause (H1 vs H2).

H1: Source TGA has no usable art  (placeholder / black extraction — all pixels
    would be keyed transparent by build_sprites.py's pure-black rule).

H2: TGA has art, but the compiled SPR is still all-transparent
    (keying threshold too tight, or makespr produced blank frames).

Usage:
    python diagnose_spr.py [TGA_PATH] [SPR_PATH]

Defaults to SPRITE_PEASANTS.tga / GU104.SPR in their standard locations.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow required: pip install Pillow")

_TOOLS    = Path(__file__).resolve().parent
_SCENARIO = _TOOLS.parent / "scen0000"

_DEFAULT_TGA = _SCENARIO / "default" / "graphics" / "pictures" / "SPRITE_PEASANTS.tga"
_DEFAULT_SPR = Path(
    r"H:\Program Files(x86)\Activision\Call To Power 2"
    r"\ctp2_data\default\graphics\sprites\GU104.SPR"
)

# SPR constants (mirrors makespr.py)
_FRPS_TAG   = 0x53505246
_VERSION0   = 0x00010003
_UNIT_TYPE  = 4
_EMPTY_ROW  = 0xFFFF


# ── TGA inspection ─────────────────────────────────────────────────────────────

def _corner_bg(img: Image.Image) -> tuple[int, int, int]:
    """Sample the four 3×3 corner patches; return their average colour."""
    w, h = img.size
    samples: list[tuple[int, int, int]] = []
    for xs in (range(min(3, w)), range(max(0, w - 3), w)):
        for ys in (range(min(3, h)), range(max(0, h - 3), h)):
            for x in xs:
                for y in ys:
                    r, g, b, *_ = img.getpixel((x, y))
                    samples.append((r, g, b))
    if not samples:
        return (0, 0, 0)
    return (
        sum(s[0] for s in samples) // len(samples),
        sum(s[1] for s in samples) // len(samples),
        sum(s[2] for s in samples) // len(samples),
    )


def _manhattan(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])


def diagnose_tga(path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"TGA DIAGNOSIS: {path.name}  ({path.stat().st_size:,} bytes)")
    print('='*60)

    img = Image.open(str(path)).convert("RGBA")
    w, h = img.size
    total = w * h
    print(f"  Dimensions : {w}×{h}  ({total:,} pixels)")

    bg = _corner_bg(img)
    print(f"  Corner BG  : {bg}")

    px = img.load()

    # pixels surviving pure-black keying (build_sprites.py's current rule)
    pure_black_bg  = sum(
        1 for y in range(h) for x in range(w)
        if (px[x, y][0] == 0 and px[x, y][1] == 0 and px[x, y][2] == 0)
    )
    surviving_pure = total - pure_black_bg

    # pixels surviving corner-sampled keying at various thresholds
    thresholds = [10, 15, 20, 30]
    surviving: dict[int, int] = {}
    for t in thresholds:
        surviving[t] = sum(
            1 for y in range(h) for x in range(w)
            if _manhattan((px[x, y][0], px[x, y][1], px[x, y][2]), bg) > t
        )

    print(f"\n  --- Pixel survival after background keying ---")
    print(f"  Pure-black rule  (r==g==b==0)  : {surviving_pure:5d} / {total} opaque pixels")
    for t in thresholds:
        pct = surviving[t] * 100 / total
        print(f"  Corner-key dist >{t:2d}           : {surviving[t]:5d} / {total}  ({pct:.1f}%)")

    print()
    if surviving_pure < 50:
        print("  [H1 LIKELY]  Very few pixels survive pure-black keying.")
        print("               The source TGA is a near-blank placeholder.")
        print("               → Re-extract from Civ2 BMP before rebuilding SPR.")
    elif surviving_pure < 200:
        print("  [H1 POSSIBLE]  Marginal pixel count after pure-black keying.")
        print("                 Art may exist but be very faint/small.")
    else:
        print("  [H1 UNLIKELY]  TGA has sufficient art pixels.")

    best_t = max(thresholds, key=lambda t: surviving[t])
    if surviving[best_t] > surviving_pure * 1.5:
        print(f"  [NOTE] Corner-key (dist>{best_t}) keeps {surviving[best_t] - surviving_pure} more")
        print(f"         pixels than the pure-black rule — background is not exactly (0,0,0).")
        print(f"         rebuild_peasant_spr.py uses corner-key to capture these.")


# ── SPR inspection ─────────────────────────────────────────────────────────────

def _parse_frame_blob(blob: bytes, width: int, height: int) -> tuple[int, int]:
    """
    Parse a frame blob as written by makespr.encode_frame.
    Returns (empty_rows, nonempty_rows).
    """
    if len(blob) < 2 + height * 2:
        return height, 0   # blob too small → treat as all-empty
    fh = struct.unpack_from("<H", blob, 0)[0]
    row_offs = struct.unpack_from(f"<{fh}H", blob, 2)
    empty = sum(1 for r in row_offs if r == _EMPTY_ROW)
    return empty, fh - empty


def diagnose_spr(path: Path) -> None:
    print(f"\n{'='*60}")
    print(f"SPR DIAGNOSIS: {path.name}  ({path.stat().st_size:,} bytes)")
    print('='*60)

    data = path.read_bytes()
    n    = len(data)

    if n < 32:
        print("  [FAIL] File too small to be a valid SPR.")
        return

    # Header
    tag, ver, stype = struct.unpack_from("<III", data, 0)
    valid = (tag == _FRPS_TAG and ver == _VERSION0 and stype == _UNIT_TYPE)
    print(f"  Magic   : {hex(tag)}  {'OK' if tag == _FRPS_TAG else 'BAD — not FRPS'}")
    print(f"  Version : {hex(ver)}  {'OK' if ver == _VERSION0 else 'BAD'}")
    print(f"  Type    : {stype}  {'OK (unit)' if stype == _UNIT_TYPE else 'BAD'}")
    if not valid:
        print("  [FAIL] Invalid SPR header — file is corrupt or not a CTP2 unit sprite.")
        return

    # Offset table
    act_offsets = struct.unpack_from("<5I", data, 12)
    names = ["MOVE", "ATTACK", "IDLE", "VICTORY", "WORK"]
    print(f"\n  Action offsets:")
    for nm, off in zip(names, act_offsets):
        present = "PRESENT" if off != 0xFFFFFFFF else "absent"
        print(f"    {nm:<10}: {hex(off)}  ({present})")

    move_off = act_offsets[0]
    if move_off == 0xFFFFFFFF or move_off >= n - 6:
        print("\n  [FAIL] MOVE action absent or offset out of range.")
        return

    # MOVE action sprite header
    spr_type, width, height = struct.unpack_from("<HHH", data, move_off)
    is_faced = (spr_type == 1)
    hp_bytes = 5 * 8 if is_faced else 8
    ff_nf_off = move_off + 6 + hp_bytes
    if ff_nf_off + 4 > n:
        print("  [FAIL] Truncated sprite header in MOVE action.")
        return

    first_frame, num_frames = struct.unpack_from("<HH", data, ff_nf_off)
    n_facings = 5 if is_faced else 1
    print(f"\n  MOVE action: {width}×{height}, {'5-facing' if is_faced else '1-facing'}, "
          f"{num_frames} frame(s)")

    # Size tables: interleaved per facing — full[j][0..N-1] then mini[j][0..N-1]
    # Layout: [full[0][0..N], mini[0][0..N], full[1][0..N], mini[1][0..N], ...]
    size_tbl_off = ff_nf_off + 4
    size_count   = n_facings * num_frames * 2   # full + mini per facing×frame
    if size_tbl_off + size_count * 4 > n:
        print("  [FAIL] Truncated size table.")
        return

    sizes = struct.unpack_from(f"<{size_count}I", data, size_tbl_off)
    # Build per-facing lists
    full_sizes: list[list[int]] = []
    mini_sizes: list[list[int]] = []
    stride = num_frames
    for j in range(n_facings):
        base = j * stride * 2
        full_sizes.append(list(sizes[base : base + stride]))
        mini_sizes.append(list(sizes[base + stride : base + stride * 2]))

    # Walk frame data: for each facing j, full frames then mini frames
    frame_data_start = size_tbl_off + size_count * 4
    offset = frame_data_start

    print(f"\n  Frame data (full frames per facing):")
    all_empty = True
    for f_idx in range(n_facings):
        for fr in range(num_frames):
            sz = full_sizes[f_idx][fr]
            if offset + sz > n:
                print(f"    facing {f_idx+1} frame {fr}: [TRUNCATED]")
                offset += sz
                continue
            blob  = data[offset:offset + sz]
            empty, nonempty = _parse_frame_blob(blob, width, height)
            status = "ALL EMPTY (transparent)" if nonempty == 0 else f"{nonempty}/{empty + nonempty} rows have pixels"
            print(f"    facing {f_idx+1} frame {fr}: {sz:5d} bytes  => {status}")
            if nonempty > 0:
                all_empty = False
            offset += sz
        # skip mini frames
        for fr in range(num_frames):
            offset += mini_sizes[f_idx][fr]

    print()
    if all_empty:
        print("  [H2 CONFIRMED]  All frame rows are EMPTY_TABLE_ENTRY.")
        print("                  The SPR was compiled but all pixels were keyed transparent.")
        print("                  Run rebuild_peasant_spr.py to recompile with better keying.")
    else:
        print("  [H2 CLEAR]  SPR has non-empty rows — the compiled sprite has visible pixels.")
        print("              If the unit is still invisible in-game, check:")
        print("              • SPRITE_PEASANTS registered in newsprite.txt with the right ID")
        print("              • GU104.SPR in ctp2_data/default/graphics/sprites/ (not scenario)")
        print("              • DefaultSprite SPRITE_PEASANTS in Units.txt (not SPRITE_SETTLER)")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    tga_path = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_TGA
    spr_path = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_SPR

    for p, label in ((tga_path, "TGA"), (spr_path, "SPR")):
        if not p.exists():
            print(f"[ERROR] {label} not found: {p}")
            sys.exit(1)

    diagnose_tga(tga_path)
    diagnose_spr(spr_path)
    print()


if __name__ == "__main__":
    main()
