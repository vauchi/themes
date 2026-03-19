#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate generated themes against core's Theme struct contract.

This script encodes what core's serde parser expects. If core adds a
required field, this script must be updated — and that update is the
signal that themes.json needs updating too.

Validates the resolved flat output (generated/themes.json) which is
what core actually consumes. If generated/ doesn't exist, falls back
to resolving themes.json directly.

Contract version: 1 (matches core/vauchi-core/src/theme.rs)

Usage:
    python3 scripts/check-core-contract.py
"""

import json
import sys
from pathlib import Path

# === CONTRACT DEFINITION ===
# These mirror core/vauchi-core/src/theme.rs struct fields.
# Update this when core's Theme or ThemeColors struct changes.

CONTRACT_VERSION = 1

REQUIRED_THEME_FIELDS = {"id", "name", "version", "mode", "colors"}
OPTIONAL_THEME_FIELDS = {"author", "license", "source"}
VALID_MODES = {"dark", "light"}

REQUIRED_COLOR_TOKENS = {
    "bg-primary",
    "bg-secondary",
    "bg-tertiary",
    "text-primary",
    "text-secondary",
    "accent",
    "accent-dark",
    "success",
    "error",
    "warning",
    "border",
}

HEX_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"


def validate_contract(themes: list) -> list[str]:
    """Validate themes against core's expected contract."""
    import re

    errors = []

    if not isinstance(themes, list):
        return ["themes.json must be a JSON array"]

    for i, theme in enumerate(themes):
        tid = theme.get("id", f"<index {i}>")
        prefix = f"[{tid}]"

        # Check required fields
        for field in REQUIRED_THEME_FIELDS:
            if field not in theme:
                errors.append(f"{prefix} Missing required field: {field}")

        # Check unknown fields
        all_known = REQUIRED_THEME_FIELDS | OPTIONAL_THEME_FIELDS
        unknown = set(theme.keys()) - all_known
        if unknown:
            # Not an error (serde ignores unknown fields) but worth warning
            print(f"  WARNING: {prefix} Unknown fields: {unknown} (ignored by core)")

        # Check mode
        mode = theme.get("mode")
        if mode and mode not in VALID_MODES:
            errors.append(f"{prefix} Invalid mode '{mode}' (expected: {VALID_MODES})")

        # Check colors
        colors = theme.get("colors", {})
        if isinstance(colors, dict):
            # Check required tokens
            for token in REQUIRED_COLOR_TOKENS:
                if token not in colors:
                    errors.append(f"{prefix} Missing color token: {token}")

            # Check color format
            for token, value in colors.items():
                if token in REQUIRED_COLOR_TOKENS and not re.match(HEX_COLOR_PATTERN, str(value)):
                    errors.append(f"{prefix} Invalid hex color for {token}: {value}")

            # Check for unknown tokens (additionalProperties: false in schema)
            unknown_tokens = set(colors.keys()) - REQUIRED_COLOR_TOKENS
            if unknown_tokens:
                errors.append(
                    f"{prefix} Unknown color tokens: {unknown_tokens} "
                    f"(schema has additionalProperties: false)"
                )

    return errors


def resolve_v2_themes(themes: list) -> list:
    """Convert v2 hierarchical themes to v1 flat format for contract checking."""
    import re as _re

    ref_pat = _re.compile(r"^\{([a-zA-Z][a-zA-Z0-9-]*)\}$")
    flat = []
    for theme in themes:
        if "primitives" in theme and "semantic" in theme:
            colors = {}
            for key, ref in theme["semantic"].items():
                m = ref_pat.match(ref)
                if m and m.group(1) in theme["primitives"]:
                    colors[key] = theme["primitives"][m.group(1)]
            entry = {k: v for k, v in theme.items() if k not in ("primitives", "semantic")}
            entry["colors"] = colors
            flat.append(entry)
        else:
            flat.append(theme)
    return flat


def main() -> int:
    repo_root = Path(__file__).parent.parent
    generated_path = repo_root / "generated" / "themes.json"
    themes_path = repo_root / "themes.json"

    # Prefer generated flat output; fall back to resolving source
    if generated_path.exists():
        source = generated_path
        with open(generated_path) as f:
            themes = json.load(f)
    elif themes_path.exists():
        source = themes_path
        with open(themes_path) as f:
            raw = json.load(f)
        themes = resolve_v2_themes(raw)
    else:
        print("ERROR: No themes file found")
        return 1

    _ = source  # used for messaging below

    print(f"Checking {len(themes)} themes against core contract v{CONTRACT_VERSION}")
    print(f"  Required fields: {sorted(REQUIRED_THEME_FIELDS)}")
    print(f"  Required colors: {len(REQUIRED_COLOR_TOKENS)} tokens")

    errors = validate_contract(themes)

    if errors:
        print(f"\nCONTRACT VIOLATION ({len(errors)} error(s)):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"\nPASSED: All {len(themes)} themes match core contract v{CONTRACT_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
