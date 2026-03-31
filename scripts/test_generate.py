#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the design token generator."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from generate import (
    find_closest_ansi256,
    generate_ansi,
    generate_css,
    generate_flat_themes,
    hex_to_rgb,
    resolve_theme,
)

# Original v1 flat color values for migration identity verification
ORIGINAL_V1_COLORS = {
    "default-dark": {
        "bg-primary": "#1a1a2e",
        "bg-secondary": "#16213e",
        "bg-tertiary": "#0f3460",
        "text-primary": "#eeeeee",
        "text-secondary": "#a0a0a0",
        "accent": "#4fc3f7",
        "accent-dark": "#0288d1",
        "success": "#4caf50",
        "error": "#f44336",
        "warning": "#ff9800",
        "border": "#333333",
    },
    "catppuccin-mocha": {
        "bg-primary": "#1e1e2e",
        "bg-secondary": "#181825",
        "bg-tertiary": "#313244",
        "text-primary": "#cdd6f4",
        "text-secondary": "#a6adc8",
        "accent": "#89b4fa",
        "accent-dark": "#74c7ec",
        "success": "#a6e3a1",
        "error": "#f38ba8",
        "warning": "#fab387",
        "border": "#45475a",
    },
    "dracula": {
        "bg-primary": "#282a36",
        "bg-secondary": "#21222c",
        "bg-tertiary": "#44475a",
        "text-primary": "#f8f8f2",
        "text-secondary": "#8390b7",
        "accent": "#bd93f9",
        "accent-dark": "#ff79c6",
        "success": "#50fa7b",
        "error": "#ff5555",
        "warning": "#ffb86c",
        "border": "#44475a",
    },
    "nord": {
        "bg-primary": "#2e3440",
        "bg-secondary": "#3b4252",
        "bg-tertiary": "#434c5e",
        "text-primary": "#eceff4",
        "text-secondary": "#d8dee9",
        "accent": "#88c0d0",
        "accent-dark": "#81a1c1",
        "success": "#a3be8c",
        "error": "#bf616a",
        "warning": "#ebcb8b",
        "border": "#4c566a",
    },
    "high-contrast": {
        "bg-primary": "#000000",
        "bg-secondary": "#0a0a0a",
        "bg-tertiary": "#1a1a1a",
        "text-primary": "#ffffff",
        "text-secondary": "#e0e0e0",
        "accent": "#ffff00",
        "accent-dark": "#00ffff",
        "success": "#00ff00",
        "error": "#ff0000",
        "warning": "#ffff00",
        "border": "#ffffff",
    },
}

SAMPLE_THEME = {
    "id": "test-theme",
    "name": "Test",
    "version": "2.0.0",
    "mode": "dark",
    "primitives": {
        "base": "#1e1e2e",
        "surface": "#313244",
        "text": "#cdd6f4",
        "subtext": "#a6adc8",
        "blue": "#89b4fa",
        "sapphire": "#74c7ec",
        "green": "#a6e3a1",
        "red": "#f38ba8",
        "peach": "#fab387",
        "overlay": "#45475a",
    },
    "semantic": {
        "bg-primary": "{base}",
        "bg-secondary": "{surface}",
        "text-primary": "{text}",
        "text-secondary": "{subtext}",
        "accent": "{blue}",
        "accent-dark": "{sapphire}",
        "success": "{green}",
        "error": "{red}",
        "warning": "{peach}",
        "border": "{overlay}",
    },
}


class TestResolveTheme(unittest.TestCase):
    """Test reference resolution from semantic to primitives."""

    def test_resolve_produces_correct_hex(self):
        resolved = resolve_theme(SAMPLE_THEME)
        self.assertEqual(resolved["bg-primary"], "#1e1e2e")
        self.assertEqual(resolved["accent"], "#89b4fa")
        self.assertEqual(resolved["error"], "#f38ba8")

    def test_resolve_all_keys_present(self):
        resolved = resolve_theme(SAMPLE_THEME)
        for key in SAMPLE_THEME["semantic"]:
            self.assertIn(key, resolved)

    def test_missing_primitive_raises_error(self):
        bad_theme = {
            "id": "bad",
            "name": "Bad",
            "version": "2.0.0",
            "mode": "dark",
            "primitives": {"base": "#000000"},
            "semantic": {"bg-primary": "{base}", "accent": "{nonexistent}"},
        }
        with self.assertRaises(ValueError) as ctx:
            resolve_theme(bad_theme)
        self.assertIn("nonexistent", str(ctx.exception))
        self.assertIn("missing primitive", str(ctx.exception))

    def test_invalid_ref_format_raises_error(self):
        bad_theme = {
            "id": "bad-format",
            "name": "Bad Format",
            "version": "2.0.0",
            "mode": "dark",
            "primitives": {"base": "#000000"},
            "semantic": {"bg-primary": "#000000"},  # raw hex, not a ref
        }
        with self.assertRaises(ValueError) as ctx:
            resolve_theme(bad_theme)
        self.assertIn("invalid reference format", str(ctx.exception).lower())


class TestMigrationIdentity(unittest.TestCase):
    """Verify that resolved v2 themes produce IDENTICAL colors to v1."""

    def test_all_themes_match_original_values(self):
        repo_root = Path(__file__).parent.parent
        themes_path = repo_root / "themes.json"
        if not themes_path.exists():
            self.skipTest("themes.json not found")

        with open(themes_path) as f:
            themes = json.load(f)

        themes_by_id = {t["id"]: t for t in themes}

        for theme_id, expected_colors in ORIGINAL_V1_COLORS.items():
            with self.subTest(theme=theme_id):
                self.assertIn(theme_id, themes_by_id, f"Theme {theme_id} not found")
                resolved = resolve_theme(themes_by_id[theme_id])
                for color_key, expected_hex in expected_colors.items():
                    self.assertEqual(
                        resolved[color_key],
                        expected_hex,
                        f"{theme_id}.{color_key}: expected {expected_hex}, got {resolved.get(color_key)}",
                    )


class TestGenerateFlatThemes(unittest.TestCase):
    """Test backward-compatible flat theme generation."""

    def test_flat_output_has_colors_key(self):
        flat = generate_flat_themes([SAMPLE_THEME], {"version": "2.0.0"})
        self.assertEqual(len(flat), 1)
        self.assertIn("colors", flat[0])
        self.assertNotIn("primitives", flat[0])
        self.assertNotIn("semantic", flat[0])

    def test_flat_preserves_metadata(self):
        flat = generate_flat_themes([SAMPLE_THEME], {"version": "2.0.0"})
        self.assertEqual(flat[0]["id"], "test-theme")
        self.assertEqual(flat[0]["name"], "Test")
        self.assertEqual(flat[0]["mode"], "dark")

    def test_flat_colors_are_hex(self):
        flat = generate_flat_themes([SAMPLE_THEME], {"version": "2.0.0"})
        for val in flat[0]["colors"].values():
            self.assertTrue(val.startswith("#"), f"Expected hex, got {val}")
            self.assertEqual(len(val), 7, f"Expected 7-char hex, got {val}")


class TestGenerateCSS(unittest.TestCase):
    """Test CSS custom properties output."""

    def test_css_has_root_selector(self):
        tokens = {"version": "2.0.0", "spacing": {"sm": 8}}
        css = generate_css(tokens, [])
        self.assertIn(":root {", css)

    def test_css_has_spacing_vars(self):
        tokens = {"version": "2.0.0", "spacing": {"sm": 8, "md": 16}}
        css = generate_css(tokens, [])
        self.assertIn("--spacing-sm: 8px;", css)
        self.assertIn("--spacing-md: 16px;", css)

    def test_css_has_theme_selectors(self):
        tokens = {"version": "2.0.0"}
        css = generate_css(tokens, [SAMPLE_THEME])
        self.assertIn('[data-theme="test-theme"]', css)
        self.assertIn("--color-bg-primary: #1e1e2e;", css)
        self.assertIn("--color-accent: #89b4fa;", css)

    def test_css_has_spdx_header(self):
        tokens = {"version": "2.0.0"}
        css = generate_css(tokens, [])
        self.assertIn("SPDX-License-Identifier", css)


class TestGenerateANSI(unittest.TestCase):
    """Test ANSI 256 color mapping."""

    def test_ansi_has_hex_and_index(self):
        ansi = generate_ansi([SAMPLE_THEME])
        self.assertEqual(len(ansi), 1)
        colors = ansi[0]["colors"]
        self.assertIn("bg-primary", colors)
        self.assertIn("hex", colors["bg-primary"])
        self.assertIn("ansi256", colors["bg-primary"])
        self.assertEqual(colors["bg-primary"]["hex"], "#1e1e2e")

    def test_ansi256_is_integer(self):
        ansi = generate_ansi([SAMPLE_THEME])
        for color_data in ansi[0]["colors"].values():
            self.assertIsInstance(color_data["ansi256"], int)
            self.assertGreaterEqual(color_data["ansi256"], 0)
            self.assertLessEqual(color_data["ansi256"], 255)


class TestHexToRgb(unittest.TestCase):
    """Test hex color parsing."""

    def test_black(self):
        self.assertEqual(hex_to_rgb("#000000"), (0, 0, 0))

    def test_white(self):
        self.assertEqual(hex_to_rgb("#ffffff"), (255, 255, 255))

    def test_red(self):
        self.assertEqual(hex_to_rgb("#ff0000"), (255, 0, 0))


class TestAnsi256(unittest.TestCase):
    """Test ANSI 256 color approximation."""

    def test_pure_black(self):
        idx = find_closest_ansi256("#000000")
        self.assertEqual(idx, 16)  # cube 0,0,0

    def test_pure_white(self):
        idx = find_closest_ansi256("#ffffff")
        self.assertEqual(idx, 231)  # cube 5,5,5

    def test_mid_gray(self):
        idx = find_closest_ansi256("#808080")
        # Should be in grayscale ramp or cube, but must be valid
        self.assertGreaterEqual(idx, 0)
        self.assertLessEqual(idx, 255)


class TestEndToEnd(unittest.TestCase):
    """End-to-end test: generate to temp dir and verify outputs."""

    def test_generate_all_outputs(self):
        repo_root = Path(__file__).parent.parent
        tokens_path = repo_root / "tokens.json"
        themes_path = repo_root / "themes.json"
        if not tokens_path.exists() or not themes_path.exists():
            self.skipTest("Source files not found")

        with open(tokens_path) as f:
            tokens = json.load(f)
        with open(themes_path) as f:
            themes = json.load(f)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)

            # Generate flat themes
            flat = generate_flat_themes(themes, tokens)
            flat_path = out_dir / "themes.json"
            with open(flat_path, "w") as f:
                json.dump(flat, f, indent=2)
            self.assertTrue(flat_path.exists())
            self.assertEqual(len(flat), 14)

            # Generate CSS
            css = generate_css(tokens, themes)
            css_path = out_dir / "tokens.css"
            with open(css_path, "w") as f:
                f.write(css)
            self.assertTrue(css_path.exists())
            self.assertGreater(len(css), 100)

            # Generate ANSI
            ansi = generate_ansi(themes)
            ansi_path = out_dir / "tokens_ansi.json"
            with open(ansi_path, "w") as f:
                json.dump(ansi, f, indent=2)
            self.assertTrue(ansi_path.exists())
            self.assertEqual(len(ansi), 14)


if __name__ == "__main__":
    unittest.main()
