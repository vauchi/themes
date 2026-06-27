#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Design token generator: resolves theme refs and emits platform outputs.

Reads tokens.json (layout/spacing tokens) and themes.json (color themes with
primitives + semantic references), resolves {ref} references, and emits:

  generated/themes.json          — resolved flat format (backward-compatible v1)
  generated/tokens.css           — CSS custom properties
  generated/tokens_ansi.json     — TUI ANSI color mapping
  generated/Tokens.swift         — Swift constants (iOS/macOS)
  generated/Tokens.kt            — Kotlin constants (Android)
  generated/Tokens.h             — C++ constexpr (linux-qt)
  generated/Tokens.cs            — C# static class (windows)
  generated/tokens_defaults.rs   — Rust DesignTokens Default impl (core)

Usage:
    python3 scripts/generate.py
    python3 scripts/generate.py --out-dir custom/output
"""

import argparse
import json
import re
import sys
from pathlib import Path

REF_PATTERN = re.compile(r"^\{([a-zA-Z][a-zA-Z0-9-]*)\}$")

# Semantic color → closest ANSI 256 mapping strategy:
# We map semantic roles to ANSI color indices for TUI rendering.
ANSI_ROLE_MAP = {
    "bg-primary": "0",      # background
    "bg-secondary": "0",    # background variant
    "bg-tertiary": "8",     # bright black (gray)
    "text-primary": "15",   # bright white
    "text-secondary": "7",  # white (dim)
    "accent": "12",         # bright blue
    "accent-dark": "4",     # blue
    "success": "10",        # bright green
    "error": "9",           # bright red
    "warning": "11",        # bright yellow
    "border": "8",          # bright black (gray)
}


def resolve_theme(theme: dict) -> dict[str, str]:
    """Resolve all semantic {ref} references to hex values via primitives.

    Returns a flat dict of semantic-key -> hex-value.
    Raises ValueError on missing or invalid references.
    """
    primitives = theme["primitives"]
    semantic = theme["semantic"]
    resolved = {}

    for key, ref in semantic.items():
        m = REF_PATTERN.match(ref)
        if not m:
            raise ValueError(
                f"Theme '{theme['id']}': semantic.{key} has invalid "
                f"reference format '{ref}' (expected {{name}})"
            )
        prim_name = m.group(1)
        if prim_name not in primitives:
            raise ValueError(
                f"Theme '{theme['id']}': semantic.{key} references "
                f"missing primitive '{prim_name}'"
            )
        resolved[key] = primitives[prim_name]

    return resolved


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def find_closest_ansi256(hex_color: str) -> int:
    """Find the closest ANSI 256 color index for a hex color.

    Uses the 6x6x6 color cube (indices 16-231) plus grayscale ramp (232-255).
    """
    r, g, b = hex_to_rgb(hex_color)

    # Check 6x6x6 cube (indices 16-231)
    # Each axis: 0, 95, 135, 175, 215, 255 → steps 0-5
    cube_steps = [0, 95, 135, 175, 215, 255]

    def nearest_cube(val: int) -> int:
        best = 0
        best_dist = abs(val - cube_steps[0])
        for i, step in enumerate(cube_steps[1:], 1):
            dist = abs(val - step)
            if dist < best_dist:
                best = i
                best_dist = dist
        return best

    ri, gi, bi = nearest_cube(r), nearest_cube(g), nearest_cube(b)
    cube_idx = 16 + 36 * ri + 6 * gi + bi
    cube_r, cube_g, cube_b = cube_steps[ri], cube_steps[gi], cube_steps[bi]
    cube_dist = (r - cube_r) ** 2 + (g - cube_g) ** 2 + (b - cube_b) ** 2

    # Check grayscale ramp (indices 232-255): 8, 18, 28, ..., 238
    gray_val = (r + g + b) // 3
    gray_idx = max(0, min(23, (gray_val - 8 + 5) // 10))
    gray_level = 8 + 10 * gray_idx
    gray_dist = (r - gray_level) ** 2 + (g - gray_level) ** 2 + (b - gray_level) ** 2

    if gray_dist < cube_dist:
        return 232 + gray_idx
    return cube_idx


def generate_flat_themes(themes: list[dict], tokens: dict) -> list[dict]:
    """Generate flat themes with embedded design tokens.

    Tokens are identical across all themes (universal layout values).
    Embedding per-theme preserves the array schema (no breaking change).
    """
    # Build tokens section (exclude metadata keys)
    token_section = {
        k: v for k, v in tokens.items() if k not in ("_spdx", "version")
    }
    token_section["token_version"] = 1

    flat = []
    for theme in themes:
        resolved = resolve_theme(theme)
        entry = {
            "id": theme["id"],
            "name": theme["name"],
            "version": theme["version"],
            "mode": theme["mode"],
        }
        if "author" in theme:
            entry["author"] = theme["author"]
        if "license" in theme:
            entry["license"] = theme["license"]
        if "source" in theme:
            entry["source"] = theme["source"]
        entry["colors"] = resolved
        entry["tokens"] = token_section
        flat.append(entry)
    return flat


def generate_css(tokens: dict, themes: list[dict]) -> str:
    """Generate CSS custom properties for tokens and themes."""
    lines = [
        "/* Auto-generated by scripts/generate.py — do not edit */",
        # REUSE-IgnoreStart
        "/* SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> */",
        "/* SPDX-License-Identifier: GPL-3.0-or-later */",
        # REUSE-IgnoreEnd
        "",
        "/* === Layout tokens === */",
        ":root {",
    ]

    # Spacing tokens
    if "spacing" in tokens:
        for key, val in tokens["spacing"].items():
            lines.append(f"  --spacing-{key}: {val}px;")

    if "spacing_direction" in tokens:
        for key, val in tokens["spacing_direction"].items():
            css_key = key.replace("_", "-")
            lines.append(f"  --spacing-{css_key}: {val}px;")

    # Typography
    if "typography" in tokens:
        for key, val in tokens["typography"].items():
            css_key = key.replace("_", "-")
            lines.append(f"  --{css_key}: {val}px;")

    # Border radius
    if "border_radius" in tokens:
        for key, val in tokens["border_radius"].items():
            lines.append(f"  --radius-{key}: {val}px;")

    # Touch target
    if "touch_target" in tokens:
        for key, val in tokens["touch_target"].items():
            lines.append(f"  --touch-target-{key}: {val}px;")

    # Motion
    if "motion" in tokens:
        for key, val in tokens["motion"].items():
            css_key = key.replace("_", "-").replace("-ms", "")
            lines.append(f"  --motion-{css_key}: {val}ms;")

    if "font_family" in tokens:
        for key, val in tokens["font_family"].items():
            lines.append(f'  --font-family-{key}: "{val}";')

    if "font_weight" in tokens:
        for key, val in tokens["font_weight"].items():
            lines.append(f"  --font-weight-{key}: {val};")

    if "focus" in tokens:
        for key, val in tokens["focus"].items():
            css_key = key.replace("_", "-")
            lines.append(f"  --focus-{css_key}: {val}px;")

    lines.append("}")
    lines.append("")

    # Theme color classes
    lines.append("/* === Theme colors === */")
    for theme in themes:
        resolved = resolve_theme(theme)
        selector = f'[data-theme="{theme["id"]}"]'
        lines.append(f"{selector} {{")
        for key, val in resolved.items():
            lines.append(f"  --color-{key}: {val};")
        lines.append("}")
        lines.append("")

    return "\n".join(lines)


def generate_ansi(themes: list[dict]) -> list[dict]:
    """Generate ANSI 256 color mapping for TUI rendering."""
    ansi_themes = []
    for theme in themes:
        resolved = resolve_theme(theme)
        ansi_colors = {}
        for key, hex_val in resolved.items():
            ansi_colors[key] = {
                "hex": hex_val,
                "ansi256": find_closest_ansi256(hex_val),
                "ansi_base": ANSI_ROLE_MAP.get(key, "7"),
            }
        ansi_themes.append({
            "id": theme["id"],
            "name": theme["name"],
            "mode": theme["mode"],
            "colors": ansi_colors,
        })
    return ansi_themes


def generate_swift(tokens: dict) -> str:
    """Generate Swift constants for design tokens."""
    lines = [
        "// Auto-generated by scripts/generate.py — do not edit",
        # REUSE-IgnoreStart
        "// SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>",
        "// SPDX-License-Identifier: GPL-3.0-or-later",
        # REUSE-IgnoreEnd
        "",
        "import CoreGraphics",
        "",
        "/// Design tokens generated from tokens.json.",
        "/// Source of truth: themes/tokens.json",
        "enum Tokens {",
    ]

    if "spacing" in tokens:
        lines.append("    enum Spacing {")
        for key, val in tokens["spacing"].items():
            lines.append(f"        static let {key}: CGFloat = {val}")
        lines.append("    }")

    if "spacing_direction" in tokens:
        lines.append("    enum SpacingDirection {")
        for key, val in tokens["spacing_direction"].items():
            swift_key = _to_camel_case(key)
            lines.append(f"        static let {swift_key}: CGFloat = {val}")
        lines.append("    }")

    if "typography" in tokens:
        lines.append("    enum Typography {")
        for key, val in tokens["typography"].items():
            swift_key = _to_camel_case(key)
            lines.append(f"        static let {swift_key}: CGFloat = {val}")
        lines.append("    }")

    if "border_radius" in tokens:
        lines.append("    enum BorderRadius {")
        for key, val in tokens["border_radius"].items():
            swift_key = _to_camel_case(key)
            lines.append(f"        static let {swift_key}: CGFloat = {val}")
        lines.append("    }")

    if "touch_target" in tokens:
        lines.append("    enum TouchTarget {")
        for key, val in tokens["touch_target"].items():
            lines.append(f"        static let {key}: CGFloat = {val}")
        lines.append("    }")

    if "motion" in tokens:
        lines.append("    enum Motion {")
        for key, val in tokens["motion"].items():
            swift_key = _to_camel_case(key)
            # Convert ms to seconds for Swift animations
            sec = val / 1000.0
            lines.append(
                f"        static let {swift_key}: Double = {sec}"
            )
        lines.append("    }")

    if "font_family" in tokens:
        lines.append("    enum FontFamily {")
        for key, val in tokens["font_family"].items():
            swift_key = _to_camel_case(key)
            lines.append(f'        static let {swift_key}: String = "{val}"')
        lines.append("    }")

    if "font_weight" in tokens:
        lines.append("    enum FontWeight {")
        for key, val in tokens["font_weight"].items():
            swift_key = _to_camel_case(key)
            lines.append(f"        static let {swift_key}: Int = {val}")
        lines.append("    }")

    if "focus" in tokens:
        lines.append("    enum Focus {")
        for key, val in tokens["focus"].items():
            swift_key = _to_camel_case(key)
            lines.append(f"        static let {swift_key}: CGFloat = {val}")
        lines.append("    }")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def generate_kotlin(tokens: dict) -> str:
    """Generate Kotlin constants for design tokens."""
    lines = [
        "// Auto-generated by scripts/generate.py — do not edit",
        # REUSE-IgnoreStart
        "// SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>",
        "// SPDX-License-Identifier: GPL-3.0-or-later",
        # REUSE-IgnoreEnd
        "",
        "package app.vauchi.ui.theme",
        "",
        "import androidx.compose.ui.unit.dp",
        "import androidx.compose.ui.unit.sp",
        "",
        "/** Design tokens generated from tokens.json. */",
        "object Tokens {",
    ]

    if "spacing" in tokens:
        lines.append("    object Spacing {")
        for key, val in tokens["spacing"].items():
            kt_key = key.upper()
            lines.append(f"        val {kt_key} = {val}.dp")
        lines.append("    }")

    if "spacing_direction" in tokens:
        lines.append("    object SpacingDirection {")
        for key, val in tokens["spacing_direction"].items():
            kt_key = _to_camel_case(key)
            lines.append(f"        val {kt_key} = {val}.dp")
        lines.append("    }")

    if "typography" in tokens:
        lines.append("    object Typography {")
        for key, val in tokens["typography"].items():
            kt_key = _to_camel_case(key)
            lines.append(f"        val {kt_key} = {val}.sp")
        lines.append("    }")

    if "border_radius" in tokens:
        lines.append("    object BorderRadius {")
        for key, val in tokens["border_radius"].items():
            kt_key = key.upper()
            lines.append(f"        val {kt_key} = {val}.dp")
        lines.append("    }")

    if "touch_target" in tokens:
        lines.append("    object TouchTarget {")
        for key, val in tokens["touch_target"].items():
            kt_key = _to_camel_case(key)
            lines.append(f"        val {kt_key} = {val}.dp")
        lines.append("    }")

    if "motion" in tokens:
        lines.append("    object Motion {")
        for key, val in tokens["motion"].items():
            kt_key = _to_camel_case(key)
            lines.append(f"        const val {kt_key}: Int = {val}")
        lines.append("    }")

    if "font_family" in tokens:
        lines.append("    object FontFamily {")
        for key, val in tokens["font_family"].items():
            kt_key = key.upper()
            lines.append(f'        const val {kt_key} = "{val}"')
        lines.append("    }")

    if "font_weight" in tokens:
        lines.append("    object FontWeight {")
        for key, val in tokens["font_weight"].items():
            kt_key = key.upper()
            lines.append(f"        const val {kt_key} = {val}")
        lines.append("    }")

    if "focus" in tokens:
        lines.append("    object Focus {")
        for key, val in tokens["focus"].items():
            kt_key = _to_camel_case(key)
            lines.append(f"        val {kt_key} = {val}.dp")
        lines.append("    }")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def generate_cpp(tokens: dict) -> str:
    """Generate C++ constexpr constants for design tokens (linux-qt)."""
    lines = [
        "// Auto-generated by scripts/generate.py — do not edit",
        # REUSE-IgnoreStart
        "// SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>",
        "// SPDX-License-Identifier: GPL-3.0-or-later",
        # REUSE-IgnoreEnd
        "",
        "#pragma once",
        "",
        "/// Design tokens generated from tokens.json.",
        "namespace Tokens {",
    ]

    for category, values in tokens.items():
        if category in ("_spdx", "version"):
            continue
        if not isinstance(values, dict):
            continue
        ns = _to_pascal_case(category)
        lines.append(f"namespace {ns} {{")
        for key, val in values.items():
            cpp_key = key.upper()
            if isinstance(val, str):
                lines.append(f'    constexpr const char* {cpp_key} = "{val}";')
            else:
                lines.append(f"    constexpr int {cpp_key} = {val};")
        lines.append(f"}} // namespace {ns}")

    lines.append("} // namespace Tokens")
    lines.append("")
    return "\n".join(lines)


def generate_csharp(tokens: dict) -> str:
    """Generate C# static constants for design tokens (windows)."""
    lines = [
        "// Auto-generated by scripts/generate.py — do not edit",
        # REUSE-IgnoreStart
        "// SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>",
        "// SPDX-License-Identifier: GPL-3.0-or-later",
        # REUSE-IgnoreEnd
        "",
        "namespace Vauchi.UI;",
        "",
        "/// <summary>Design tokens generated from tokens.json.</summary>",
        "public static class Tokens",
        "{",
    ]

    for category, values in tokens.items():
        if category in ("_spdx", "version"):
            continue
        if not isinstance(values, dict):
            continue
        cls = _to_pascal_case(category)
        lines.append(f"    public static class {cls}")
        lines.append("    {")
        for key, val in values.items():
            cs_key = _to_pascal_case(key)
            if isinstance(val, str):
                lines.append(f'        public const string {cs_key} = "{val}";')
            else:
                lines.append(f"        public const double {cs_key} = {val};")
        lines.append("    }")

    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def generate_rust(tokens: dict) -> str:
    """Generate Rust Default impl for DesignTokens from tokens.json."""
    lines = [
        "// Auto-generated by themes/scripts/generate.py — do not edit",
        # REUSE-IgnoreStart
        "// SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>",
        "// SPDX-License-Identifier: GPL-3.0-or-later",
        # REUSE-IgnoreEnd
        "//",
        "// Source of truth: themes/tokens.json",
        "",
        "impl Default for DesignTokens {",
        "    fn default() -> Self {",
        "        Self {",
    ]

    spacing = tokens.get("spacing", {})
    lines.append("            spacing: SpacingTokens {")
    for key, val in spacing.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    spacing_dir = tokens.get("spacing_direction", {})
    lines.append("            spacing_direction: SpacingDirectionTokens {")
    for key, val in spacing_dir.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    typography = tokens.get("typography", {})
    lines.append("            typography: TypographyTokens {")
    for key, val in typography.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    border_radius = tokens.get("border_radius", {})
    lines.append("            border_radius: BorderRadiusTokens {")
    for key, val in border_radius.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    touch_target = tokens.get("touch_target", {})
    lines.append("            touch_target: TouchTargetTokens {")
    for key, val in touch_target.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    motion = tokens.get("motion", {})
    lines.append("            motion: MotionTokens {")
    for key, val in motion.items():
        lines.append(f"                {key}: {val},")
    lines.append("            },")

    font_family = tokens.get("font_family", {})
    if font_family:
        lines.append("            font_family: FontFamilyTokens {")
        for key, val in font_family.items():
            lines.append(f'                {key}: "{val}".to_string(),')
        lines.append("            },")

    font_weight = tokens.get("font_weight", {})
    if font_weight:
        lines.append("            font_weight: FontWeightTokens {")
        for key, val in font_weight.items():
            lines.append(f"                {key}: {val},")
        lines.append("            },")

    focus = tokens.get("focus", {})
    if focus:
        lines.append("            focus: FocusTokens {")
        for key, val in focus.items():
            lines.append(f"                {key}: {val},")
        lines.append("            },")

    lines.append("        }")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _to_pascal_case(snake: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(p.capitalize() for p in snake.split("_"))


def _to_camel_case(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate design token outputs")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: generated/ in repo root)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    out_dir = args.out_dir or (repo_root / "generated")

    tokens_path = repo_root / "tokens.json"
    themes_path = repo_root / "themes.json"

    # Load inputs
    if not tokens_path.exists():
        print(f"ERROR: {tokens_path} not found")
        return 1
    if not themes_path.exists():
        print(f"ERROR: {themes_path} not found")
        return 1

    with open(tokens_path) as f:
        tokens = json.load(f)
    with open(themes_path) as f:
        themes = json.load(f)

    print(f"Loaded {len(themes)} themes, tokens v{tokens.get('version', '?')}")

    # Validate all refs resolve before generating anything
    for theme in themes:
        try:
            resolve_theme(theme)
        except ValueError as e:
            print(f"ERROR: {e}")
            return 1

    # Create output directory
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate flat themes (backward-compatible)
    flat_themes = generate_flat_themes(themes, tokens)
    flat_path = out_dir / "themes.json"
    with open(flat_path, "w") as f:
        json.dump(flat_themes, f, indent=2)
        f.write("\n")
    print(f"  -> {flat_path} ({len(flat_themes)} themes)")

    # Generate CSS
    css_content = generate_css(tokens, themes)
    css_path = out_dir / "tokens.css"
    with open(css_path, "w") as f:
        f.write(css_content)
    print(f"  -> {css_path}")

    # Generate ANSI mapping
    ansi_themes = generate_ansi(themes)
    ansi_path = out_dir / "tokens_ansi.json"
    with open(ansi_path, "w") as f:
        json.dump(ansi_themes, f, indent=2)
        f.write("\n")
    print(f"  -> {ansi_path} ({len(ansi_themes)} themes)")

    # Generate Swift tokens
    swift_content = generate_swift(tokens)
    swift_path = out_dir / "Tokens.swift"
    with open(swift_path, "w") as f:
        f.write(swift_content)
    print(f"  -> {swift_path}")

    # Generate Kotlin tokens
    kotlin_content = generate_kotlin(tokens)
    kotlin_path = out_dir / "Tokens.kt"
    with open(kotlin_path, "w") as f:
        f.write(kotlin_content)
    print(f"  -> {kotlin_path}")

    # Generate C++ tokens
    cpp_content = generate_cpp(tokens)
    cpp_path = out_dir / "Tokens.h"
    with open(cpp_path, "w") as f:
        f.write(cpp_content)
    print(f"  -> {cpp_path}")

    # Generate C# tokens
    cs_content = generate_csharp(tokens)
    cs_path = out_dir / "Tokens.cs"
    with open(cs_path, "w") as f:
        f.write(cs_content)
    print(f"  -> {cs_path}")

    # Generate Rust Default impl
    rust_content = generate_rust(tokens)
    rust_path = out_dir / "tokens_defaults.rs"
    with open(rust_path, "w") as f:
        f.write(rust_content)
    # Run rustfmt if available (keeps generated code consistent with project style)
    import subprocess
    try:
        subprocess.run(["rustfmt", str(rust_path)], check=True, capture_output=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass  # rustfmt optional — CI will catch formatting issues
    print(f"  -> {rust_path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
