import csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import ctp2_parser as P

SCEN = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\scen0000")
CSV = Path(r"H:\Program Files(x86)\Activision\Call To Power 2\Scenarios\mom\tools\data_csv")
CSV.mkdir(parents=True, exist_ok=True)


def load(rel: str) -> str:
    p = SCEN / rel
    return p.read_text(encoding='latin-1') if p.exists() else ""


def save(rel: str, text: str):
    (SCEN / rel).write_text(text, encoding='latin-1')


def export_csv(rows, name):
    with open(str(CSV / name), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)


def export_flatlist(src, dst):
    f = P.FlatListFile()
    f.parse(load("default/gamedata/wondermovie.txt"))
    export_csv([['key', 'value']] + [(k, v.strip('"')) for k, v in f.entries.items()], dst)


def export_wondericon(dst):
    f = P.CountedIconFile()
    f.parse(load("default/gamedata/wondericon.txt"))
    export_csv([['icon_id']] + [[e.split('\t')[0]] for e in f.entries], dst)


def export_blocks(src, dst):
    f = P.CTP2BlockFile()
    f.parse(load(src))
    if not f.blocks:
        return
    all_f = sorted({k for b in f.blocks.values() for k in b})
    rows = [['id'] + all_f]
    for i, b in f.blocks.items():
        rows.append([i] + [b.get(k, '') for k in all_f])
    export_csv(rows, dst)


def export_strings(dst):
    f = P.StringDBFile()
    f.parse(load("english/gamedata/gl_str.txt"))
    export_csv([['key', 'value']] + list(f.entries.items()), dst)


def export_gl(dst):
    f = P.LibraryFile()
    f.parse(load("english/gamedata/Great_Library.txt"))
    export_csv([['section_id', 'content']] + list(f.sections.items()), dst)


if __name__ == '__main__':
    print("Generating CSVs from scenario files...")
    export_blocks("default/gamedata/Wonder.txt", "wonder.csv")
    export_blocks("default/gamedata/Improve.txt", "improve.csv")
    export_flatlist("wondermovie.csv")
    export_wondericon("wondericon.csv")
    export_strings("gl_str.csv")
    export_gl("great_library.csv")
    print("Done.")
