#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate themes.json against schema and WCAG contrast requirements.

Usage:
    python3 scripts/validate.py           # Basic validation
    python3 scripts/validate.py --strict  # Also check secondary text + accent visibility
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None

REF_PATTERN = re.compile(r"^\{([a-zA-Z][a-zA-Z0-9-]*)\}$")


def resolve_semantic(theme: dict) -> dict[str, str]:
    """Resolve semantic refs to hex values via primitives. Returns flat color dict."""
    primitives = theme["primitives"]
    semantic = theme["semantic"]
    resolved = {}
    for key, ref in semantic.items():
        m = REF_PATTERN.match(ref)
        if not m:
            raise ValueError(f"[{theme['id']}] Invalid reference format: {ref}")
        prim_name = m.group(1)
        if prim_name not in primitives:
            raise ValueError(f"[{theme['id']}] Missing primitive '{prim_name}' referenced by semantic.{key}")
        resolved[key] = primitives[prim_name]
    return resolved


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color string to RGB tuple."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def relative_luminance(r: int, g: int, b: int) -> float:
    """Compute relative luminance per WCAG 2.1 definition."""
    def linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def contrast_ratio(color1: str, color2: str) -> float:
    """Compute WCAG contrast ratio between two hex colors."""
    l1 = relative_luminance(*hex_to_rgb(color1))
    l2 = relative_luminance(*hex_to_rgb(color2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def validate_schema(themes: list, schema: dict) -> list[str]:
    """Validate themes against JSON schema. Returns list of errors."""
    if jsonschema is None:
        print("WARNING: jsonschema not installed, skipping schema validation")
        return []

    errors = []
    try:
        jsonschema.validate(instance=themes, schema=schema)
    except jsonschema.ValidationError as e:
        errors.append(f"Schema validation error: {e.message}")
    except jsonschema.SchemaError as e:
        errors.append(f"Schema itself is invalid: {e.message}")
    return errors


def validate_unique_ids(themes: list) -> list[str]:
    """Check for duplicate theme IDs."""
    errors = []
    seen = {}
    for i, theme in enumerate(themes):
        tid = theme.get("id", f"<missing at index {i}>")
        if tid in seen:
            errors.append(f"Duplicate theme ID '{tid}' at index {i} (first seen at index {seen[tid]})")
        else:
            seen[tid] = i
    return errors


def validate_refs(themes: list) -> list[str]:
    """Validate that all semantic refs point to existing primitives."""
    errors = []
    for theme in themes:
        tid = theme["id"]
        primitives = theme.get("primitives", {})
        semantic = theme.get("semantic", {})
        for key, ref in semantic.items():
            m = REF_PATTERN.match(ref)
            if not m:
                errors.append(f"[{tid}] semantic.{key}: invalid reference format '{ref}'")
                continue
            prim_name = m.group(1)
            if prim_name not in primitives:
                errors.append(f"[{tid}] semantic.{key}: references missing primitive '{prim_name}'")
    return errors


def validate_contrast(themes: list, strict: bool = False) -> list[str]:
    """Check WCAG AA contrast requirements using resolved colors."""
    errors = []
    for theme in themes:
        tid = theme["id"]
        try:
            colors = resolve_semantic(theme)
        except ValueError as e:
            errors.append(str(e))
            continue

        bg = colors["bg-primary"]

        # WCAG AA: text-primary on bg-primary >= 4.5:1
        ratio = contrast_ratio(colors["text-primary"], bg)
        if ratio < 4.5:
            errors.append(
                f"[{tid}] text-primary ({colors['text-primary']}) on bg-primary ({bg}): "
                f"contrast {ratio:.2f}:1 < 4.5:1 (WCAG AA fail)"
            )

        if strict:
            # text-secondary on bg-primary >= 4.5:1
            ratio_sec = contrast_ratio(colors["text-secondary"], bg)
            if ratio_sec < 4.5:
                errors.append(
                    f"[{tid}] text-secondary ({colors['text-secondary']}) on bg-primary ({bg}): "
                    f"contrast {ratio_sec:.2f}:1 < 4.5:1 (WCAG AA fail)"
                )

            # accent on bg-primary >= 3:1 (large text / UI component threshold)
            ratio_acc = contrast_ratio(colors["accent"], bg)
            if ratio_acc < 3.0:
                errors.append(
                    f"[{tid}] accent ({colors['accent']}) on bg-primary ({bg}): "
                    f"contrast {ratio_acc:.2f}:1 < 3.0:1 (visibility fail)"
                )

            # ADR-038 Amendment 1 extensions (known-optional — checked on
            # bg-primary when the theme defines them). text-label is body
            # text (AA 4.5:1); text-muted is incidental, accent-bright and
            # icon-accent are UI/icon roles (3:1).
            ext_checks = [
                ("text-label", 4.5, "WCAG AA fail"),
                ("text-muted", 3.0, "UI/incidental fail"),
                ("accent-bright", 3.0, "UI fail"),
                ("icon-accent", 3.0, "UI fail"),
            ]
            for token, threshold, label in ext_checks:
                if token in colors:
                    ratio_ext = contrast_ratio(colors[token], bg)
                    if ratio_ext < threshold:
                        errors.append(
                            f"[{tid}] {token} ({colors[token]}) on bg-primary "
                            f"({bg}): contrast {ratio_ext:.2f}:1 < {threshold}:1 "
                            f"({label})"
                        )

            # ADR-038 Amendment 3 (2026-06-27): text-on-accent is the
            # foreground on an accent-FILLED control, so it is measured
            # against the accent fill, not bg-primary (AA normal text
            # 4.5:1). focus-ring refs {accent} and is already covered by
            # the accent >= 3:1 check above — no separate row until a theme
            # mints a divergent ui-focus-ring primitive.
            if "text-on-accent" in colors:
                ratio_toa = contrast_ratio(colors["text-on-accent"], colors["accent"])
                if ratio_toa < 4.5:
                    errors.append(
                        f"[{tid}] text-on-accent ({colors['text-on-accent']}) on accent "
                        f"({colors['accent']}): contrast {ratio_toa:.2f}:1 < 4.5:1 "
                        f"(WCAG AA fail)"
                    )

            # ADR-038 Amendment 4 (2026-06-28): status-text foregrounds are
            # rendered on their status TINT background (banner/card), so each
            # is measured against its tint, not bg-primary (AA normal text
            # 4.5:1; the tint is the harder reference than the card surface).
            status_text_refs = [
                ("status-text-success", "tint-green"),
                ("status-text-warning", "tint-orange"),
                ("status-text-error", "tint-danger"),
                ("status-text-info", "tint-accent"),
            ]
            for token, tint in status_text_refs:
                if token in colors and tint in colors:
                    ratio_st = contrast_ratio(colors[token], colors[tint])
                    if ratio_st < 4.5:
                        errors.append(
                            f"[{tid}] {token} ({colors[token]}) on {tint} "
                            f"({colors[tint]}): contrast {ratio_st:.2f}:1 < 4.5:1 "
                            f"(WCAG AA fail)"
                        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Vauchi themes")
    parser.add_argument("--strict", action="store_true", help="Also check secondary text and accent visibility")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    themes_path = repo_root / "themes.json"
    schema_path = repo_root / "themes.schema.json"

    if not themes_path.exists():
        print(f"ERROR: {themes_path} not found")
        return 1

    with open(themes_path) as f:
        themes = json.load(f)

    print(f"Loaded {len(themes)} themes from {themes_path}")

    all_errors: list[str] = []

    # Schema validation
    if schema_path.exists():
        with open(schema_path) as f:
            schema = json.load(f)
        all_errors.extend(validate_schema(themes, schema))
    else:
        print(f"WARNING: Schema file not found at {schema_path}, skipping schema validation")

    # Unique IDs
    all_errors.extend(validate_unique_ids(themes))

    # Reference validity
    all_errors.extend(validate_refs(themes))

    # WCAG contrast
    all_errors.extend(validate_contrast(themes, strict=args.strict))

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    mode = "strict" if args.strict else "basic"
    print(f"\nPASSED: All {len(themes)} themes valid ({mode} mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
