#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import a validator script by filename.

Several of the scripts are hyphenated CLI entry points
(`check-core-contract.py`), which is not an importable module name.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent


def load(script_filename: str) -> ModuleType:
    module_name = f"vauchi_themes_{script_filename.removesuffix('.py').replace('-', '_')}"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(
        module_name, SCRIPTS_DIR / script_filename
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script_filename} from {SCRIPTS_DIR}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
