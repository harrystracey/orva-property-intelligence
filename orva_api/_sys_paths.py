"""
Single source of truth for sys.path augmentation inside orva_api.

Historically every router / service did its own `sys.path.insert(0, ...)`
block to pull in top-level modules (data_processor, whatsapp_bot, ...).
Importing this module once is enough: it augments sys.path idempotently
the first time any orva_api submodule is loaded.

Just write `from . import _sys_paths  # noqa: F401` at the top of any
orva_api module that imports from the project root or whatsapp_bot/.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WA_BOT_DIR = PROJECT_ROOT / "whatsapp_bot"


def _ensure(paths: list[Path]) -> None:
    for p in paths:
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure([PROJECT_ROOT, WA_BOT_DIR])
