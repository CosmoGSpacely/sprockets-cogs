"""Compatibility alias for `specialists.cogs.planning`.

Specialist-owned implementation lives under `specialists/`; this root
module exists only for legacy imports and script entrypoints.
"""
from __future__ import annotations

import runpy as _runpy
import sys as _sys
from importlib import import_module as _import_module

_MODULE_NAME = "specialists.cogs.planning"

if __name__ == "__main__":
    _runpy.run_module(_MODULE_NAME, run_name="__main__")
else:
    _module = _import_module(_MODULE_NAME)
    _sys.modules[__name__] = _module
