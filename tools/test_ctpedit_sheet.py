"""Tests for `ctpedit.py sheet` -- unit art enters the harness only as a spritesheet.

NO GOVERNING SPEC. Basis: operator 2026-09-28 -- "the harness shouldn't try to
overwrite the images from source ... we should allow the harness to accept a
spritesheet". subprocess.run is replaced, so no art is read or written.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import ctpedit as E


class _Done:
    def __init__(self, rc=0):
        self.returncode = rc


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake_run(cmd, cwd=None, **_kw):
        seen.append([Path(c).name if i == 1 else c for i, c in enumerate(cmd)])
        return _Done(0)

    monkeypatch.setattr(E.subprocess, "run", fake_run)
    return seen


def _args(**kw):
    base = dict(action="import", png="sheet.png", apply=False, only=None)
    base.update(kw)
    return argparse.Namespace(**base)


def test_dry_run_import_touches_nothing_downstream(calls):
    with pytest.raises(SystemExit) as ex:
        E.cmd_sheet(_args())
    assert ex.value.code == 0
    assert [c[1] for c in calls] == ["spritesheet.py"]
    assert "--apply" not in calls[0]


def test_apply_imports_then_builds_sprites_then_audits(calls):
    with pytest.raises(SystemExit):
        E.cmd_sheet(_args(apply=True, only=["LAMP"]))
    assert [c[1] for c in calls] == ["spritesheet.py", "build_sprites.py", "mom_audit.py"]
    assert calls[0][-3:] == ["--apply", "--only", "LAMP"]


def test_relative_sheet_path_resolves_against_the_callers_cwd(calls, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        E.cmd_sheet(_args())
    assert calls[0][3] == str((tmp_path / "sheet.png").resolve())


def test_failed_import_stops_before_the_build(monkeypatch):
    seen = []

    def fail(cmd, cwd=None, **_kw):
        seen.append(cmd)
        return _Done(3)

    monkeypatch.setattr(E.subprocess, "run", fail)
    with pytest.raises(SystemExit) as ex:
        E.cmd_sheet(_args(apply=True))
    assert ex.value.code == 3 and len(seen) == 1


def test_export_passes_out_path_and_builds_nothing(calls):
    with pytest.raises(SystemExit):
        E.cmd_sheet(_args(action="export", png="out.png"))
    assert calls[0][2] == "export" and calls[0][3] == "--out" and len(calls) == 1
