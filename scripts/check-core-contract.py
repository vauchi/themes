#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate generated themes and design tokens against core's contracts.

This script encodes what core's serde parser expects. If core adds a
required field, this script must be updated — and that update is the
signal that themes.json/tokens.json needs updating too.

Validates:
  1. Themes: resolved flat output (generated/themes.json) against ThemeColors contract
  2. Tokens: tokens.json against DesignTokens::default() contract

Contract version: 2 (matches core/vauchi-app/src/theme.rs)

Usage:
    python3 scripts/check-core-contract.py
"""

import json
import sys
from pathlib import Path

# === CONTRACT DEFINITION ===
# These mirror core/vauchi-core/src/theme.rs struct fields.
# Update this when core's Theme or ThemeColors struct changes.

CONTRACT_VERSION = 2

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

# === DESIGN TOKEN CONTRACT ===
# These mirror core/vauchi-app/src/theme.rs DesignTokens::default()
# (which is generated from tokens.json by generate.py).
# This contract check is the secondary safety net — the generated
# Rust Default impl is the primary mechanism that keeps values in sync.
# Update this when new token categories are added to tokens.json.

RUST_DESIGN_TOKEN_DEFAULTS = {
    "spacing": {"xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32},
    "spacing_direction": {
        "content_start": 16,
        "content_end": 16,
        "list_item_start": 8,
        "list_item_end": 8,
        "list_item_inline_start": 12,
        "list_item_inline_end": 12,
    },
    "typography": {
        "title_size": 24,
        "subtitle_size": 18,
        "body_size": 16,
        "caption_size": 14,
    },
    "border_radius": {"sm": 4, "md": 8, "md_lg": 12, "lg": 16},
    "touch_target": {"minimum": 44},
    "motion": {
        "enter_duration_ms": 200,
        "exit_duration_ms": 150,
        "emphasis_duration_ms": 300,
    },
}

# Token categories in tokens.json that exist in CSS/ANSI but not yet in Rust.
# When added to Rust, move to RUST_DESIGN_TOKEN_DEFAULTS.
KNOWN_UNMIRRORED_CATEGORIES: set[str] = set()

# Non-token metadata keys in tokens.json (not validated as tokens).
TOKEN_METADATA_KEYS = {"_spdx", "version"}


def validate_token_contract(tokens: dict) -> list[str]:
    """Validate tokens.json values match Rust DesignTokens::default()."""
    errors = []

    # Check all Rust-mirrored categories exist and match
    for category, expected_values in RUST_DESIGN_TOKEN_DEFAULTS.items():
        if category not in tokens:
            errors.append(f"[tokens] Missing category: {category}")
            continue

        actual = tokens[category]
        if not isinstance(actual, dict):
            errors.append(f"[tokens] {category} must be an object, got {type(actual).__name__}")
            continue

        for key, expected in expected_values.items():
            if key not in actual:
                errors.append(f"[tokens] {category}.{key} missing (Rust default: {expected})")
            elif actual[key] != expected:
                errors.append(
                    f"[tokens] {category}.{key} = {actual[key]} but Rust "
                    f"DesignTokens::default() = {expected} — values must match"
                )

        # Warn about extra keys in tokens.json that Rust doesn't know about
        extra = set(actual.keys()) - set(expected_values.keys())
        if extra:
            print(
                f"  WARNING: [tokens] {category} has keys {extra} not in "
                f"Rust struct (will be ignored by core)"
            )

    # Check for unknown categories (not in Rust, not in known-unmirrored)
    all_known = set(RUST_DESIGN_TOKEN_DEFAULTS) | KNOWN_UNMIRRORED_CATEGORIES | TOKEN_METADATA_KEYS
    unknown = set(tokens.keys()) - all_known
    if unknown:
        errors.append(
            f"[tokens] Unknown categories: {unknown} — add to "
            f"RUST_DESIGN_TOKEN_DEFAULTS or KNOWN_UNMIRRORED_CATEGORIES"
        )

    return errors


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
    tokens_path = repo_root / "tokens.json"

    all_errors = []

    # --- Theme contract ---
    if generated_path.exists():
        with open(generated_path) as f:
            themes = json.load(f)
    elif themes_path.exists():
        with open(themes_path) as f:
            raw = json.load(f)
        themes = resolve_v2_themes(raw)
    else:
        print("ERROR: No themes file found")
        return 1

    print(f"Checking {len(themes)} themes against core contract v{CONTRACT_VERSION}")
    print(f"  Required fields: {sorted(REQUIRED_THEME_FIELDS)}")
    print(f"  Required colors: {len(REQUIRED_COLOR_TOKENS)} tokens")

    all_errors.extend(validate_contract(themes))

    # --- Token contract ---
    if tokens_path.exists():
        with open(tokens_path) as f:
            tokens = json.load(f)

        mirrored = len(RUST_DESIGN_TOKEN_DEFAULTS)
        unmirrored = len(KNOWN_UNMIRRORED_CATEGORIES)
        print(f"\nChecking tokens.json against Rust DesignTokens::default()")
        print(f"  Mirrored in Rust: {mirrored} categories")
        if unmirrored:
            print(f"  Not yet in Rust:  {unmirrored} categories (tracked as ADR-038 gap)")

        all_errors.extend(validate_token_contract(tokens))
    else:
        print("\nWARNING: tokens.json not found — skipping token contract check")

    # --- Result ---
    if all_errors:
        print(f"\nCONTRACT VIOLATION ({len(all_errors)} error(s)):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(f"\nPASSED: All {len(themes)} themes + tokens match core contract v{CONTRACT_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
