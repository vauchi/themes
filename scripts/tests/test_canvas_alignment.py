#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""The default themes and tokens.json carry the Vauchi Shells canvas values.

The canvas is the design reference; these pins record the values the
maintainer chose to adopt from it (vauchi/private#411): Material 3's
error red, and the spacing and radius steps the canvas uses routinely.
"""

import json
import unittest

from scriptloader import REPO_ROOT, load

generate = load("generate.py")

CANVAS_ERROR_RED = {"default-light": "#b3261e", "default-dark": "#f2b8b5"}

CANVAS_SPACING = {
    "xxs": 2,
    "xs": 4,
    "xs_sm": 6,
    "sm": 8,
    "sm_smd": 10,
    "sm_md": 12,
    "smd_md": 14,
    "md": 16,
    "md_lg": 20,
    "lg": 24,
    "xl": 32,
}

CANVAS_RADIUS = {"xs": 2, "pill": 999}


def load_json(name):
    with open(REPO_ROOT / name, encoding="utf-8") as f:
        return json.load(f)


class DefaultThemesUseTheCanvasErrorRed(unittest.TestCase):
    def test_error_and_error_text_are_the_canvas_red(self):
        themes = {t["id"]: t for t in load_json("themes.json")}
        for theme_id, red in CANVAS_ERROR_RED.items():
            resolved = generate.resolve_theme(themes[theme_id])
            for role in ("error", "status-text-error"):
                with self.subTest(theme=theme_id, role=role):
                    self.assertEqual(resolved[role].lower(), red)


class TokensCarryTheCanvasScale(unittest.TestCase):
    def test_spacing_is_the_canvas_scale(self):
        self.assertEqual(load_json("tokens.json")["spacing"], CANVAS_SPACING)

    def test_radius_has_the_canvas_hairline_and_pill(self):
        radius = load_json("tokens.json")["border_radius"]
        for name, value in CANVAS_RADIUS.items():
            with self.subTest(radius=name):
                self.assertEqual(radius.get(name), value)


if __name__ == "__main__":
    unittest.main()
