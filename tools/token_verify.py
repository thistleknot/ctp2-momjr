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
