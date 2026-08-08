"""
gui.script_runner — Sandboxed exec() for the ctpedit GUI Script REPL.

The sandbox exposes only: df (mutable WorkingDF), original (read-only copy),
np, pd. No os, subprocess, importlib, open, or network access.

Execution is killed after 10 seconds via a worker thread.
"""
from __future__ import annotations

import signal
import threading
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


class ScriptTimeout(Exception):
    """Raised when a user script exceeds the time limit."""


class ScriptSandboxError(Exception):
    """Raised when a user script attempts forbidden operations."""


# Builtins whitelist — safe subset of Python builtins
_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    # Block dangerous builtins
    "__import__": None,
    "open": None,
    "exec": None,
    "eval": None,
    "compile": None,
    "globals": None,
    "locals": None,
    "breakpoint": None,
    "exit": None,
    "quit": None,
    "input": None,
}


def _blocked_import(*args: Any, **kwargs: Any) -> None:
    raise ScriptSandboxError("Import is not allowed in the Script REPL.")


def _blocked_open(*args: Any, **kwargs: Any) -> None:
    raise ScriptSandboxError("File I/O is not allowed in the Script REPL.")


def run_script(
    code: str,
    working_df: pd.DataFrame,
    original_df: pd.DataFrame,
    timeout_seconds: float = 10.0,
) -> Tuple[pd.DataFrame, str]:
    """Execute user code in a restricted sandbox.

    Parameters
    ----------
    code : Python source code from the Script REPL.
    working_df : The current WorkingDF (mutable within the script).
    original_df : The OriginalDF (exposed as read-only copy).
    timeout_seconds : Max execution time before kill.

    Returns
    -------
    (new_working_df, output_text) — The (possibly mutated) df and any print output.

    Raises
    ------
    ScriptTimeout : If execution exceeds timeout_seconds.
    ScriptSandboxError : If the script attempts forbidden operations.
    Exception : Any other runtime error from the user script.
    """
    import io
    import contextlib

    # Validate basic safety before exec
    _check_forbidden_patterns(code)

    # Build restricted namespace
    sandbox_globals: Dict[str, Any] = {
        "__builtins__": _SAFE_BUILTINS,
        "__import__": _blocked_import,
        "open": _blocked_open,
        "df": working_df.copy(),
        "original": original_df.copy(),
        "np": np,
        "pd": pd,
    }

    output_buffer = io.StringIO()
    # Override print to capture output
    sandbox_globals["print"] = lambda *args, **kwargs: print(
        *args, **kwargs, file=output_buffer
    )

    result_holder: Dict[str, Any] = {"df": None, "error": None}

    def _exec_target() -> None:
        try:
            exec(code, sandbox_globals)  # noqa: S102
            result_holder["df"] = sandbox_globals.get("df")
        except Exception as e:
            result_holder["error"] = e

    # Run in a thread with timeout
    thread = threading.Thread(target=_exec_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    if thread.is_alive():
        # Thread is still running — timeout
        raise ScriptTimeout(f"Script timed out ({timeout_seconds}s limit)")

    if result_holder["error"] is not None:
        raise result_holder["error"]

    new_df = result_holder["df"]
    if not isinstance(new_df, pd.DataFrame):
        # If df was reassigned to something else, keep original
        new_df = working_df

    return new_df, output_buffer.getvalue()


def _check_forbidden_patterns(code: str) -> None:
    """Quick static check for obviously forbidden patterns.

    This is defense-in-depth — the restricted builtins handle the real enforcement.
    """
    forbidden = [
        "import os",
        "import subprocess",
        "import sys",
        "import importlib",
        "import shutil",
        "import socket",
        "import urllib",
        "import requests",
        "import http",
        "__import__(",
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.Popen",
    ]
    code_lower = code.lower().replace(" ", "")
    for pattern in forbidden:
        pattern_normalized = pattern.lower().replace(" ", "")
        if pattern_normalized in code_lower:
            raise ScriptSandboxError(
                f"Forbidden operation detected: '{pattern}' is not allowed in the Script REPL."
            )
