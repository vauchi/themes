#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the theme validator.

The contrast checks are the only thing standing between a theme and an
unreadable interface, and the thresholds they enforce come from WCAG
2.1 and ADR-038, so they are asserted against published reference
values rather than against the implementation's own arithmetic.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scriptloader import REPO_ROOT, SCRIPTS_DIR, load

validate = load("validate.py")

BLACK, WHITE = "#000000", "#ffffff"
# The darkest grey that still clears WCAG AA on white (4.54:1).
AA_GREY = "#767676"
# Clears the 3:1 UI threshold on black (3.66:1) but not AA's 4.5:1, so it
# tells the two thresholds apart.
UI_GREY = "#666666"
# The same discriminator measured against white (3.64:1), for the tokens
# whose reference is a light fill rather than a dark background.
UI_GREY_ON_WHITE = "#868686"


def theme(tid="t", mode="dark", **semantic_overrides) -> dict:
    """A theme whose primitives are named after the role that uses them."""
    semantic = {
        "bg-primary": BLACK,
        "text-primary": WHITE,
        "text-secondary": WHITE,
        "accent": WHITE,
    }
    semantic.update(semantic_overrides)
    primitives = {f"p{i}": value for i, value in enumerate(semantic.values())}
    refs = {
        key: f"{{p{i}}}" for i, key in enumerate(semantic)
    }
    return {
        "id": tid,
        "name": tid,
        "version": "1.0.0",
        "author": "test",
        "license": "GPL-3.0-or-later",
        "mode": mode,
        "primitives": primitives,
        "semantic": refs,
    }


class ColorConversion(unittest.TestCase):
    def test_a_hex_string_becomes_its_rgb_components(self):
        self.assertEqual(validate.hex_to_rgb("#4fc3f7"), (79, 195, 247))

    def test_a_leading_hash_is_optional(self):
        self.assertEqual(validate.hex_to_rgb("4fc3f7"), (79, 195, 247))

    def test_the_extremes_convert_exactly(self):
        self.assertEqual(validate.hex_to_rgb(BLACK), (0, 0, 0))
        self.assertEqual(validate.hex_to_rgb(WHITE), (255, 255, 255))


class RelativeLuminance(unittest.TestCase):
    """WCAG 2.1 defines black as 0.0 and white as 1.0 exactly."""

    def test_black_has_zero_luminance(self):
        self.assertEqual(validate.relative_luminance(0, 0, 0), 0.0)

    def test_white_has_unit_luminance(self):
        self.assertEqual(validate.relative_luminance(255, 255, 255), 1.0)

    def test_green_dominates_the_luminance_of_red_and_blue(self):
        red = validate.relative_luminance(255, 0, 0)
        green = validate.relative_luminance(0, 255, 0)
        blue = validate.relative_luminance(0, 0, 255)

        self.assertGreater(green, red)
        self.assertGreater(red, blue)
        self.assertAlmostEqual(green, 0.7152, places=4)


class ContrastRatio(unittest.TestCase):
    def test_black_on_white_is_the_maximum_of_twenty_one_to_one(self):
        self.assertAlmostEqual(validate.contrast_ratio(BLACK, WHITE), 21.0, places=6)

    def test_a_color_against_itself_is_one_to_one(self):
        self.assertAlmostEqual(validate.contrast_ratio(AA_GREY, AA_GREY), 1.0, places=6)

    def test_the_canonical_aa_grey_clears_four_and_a_half_on_white(self):
        ratio = validate.contrast_ratio(AA_GREY, WHITE)

        self.assertAlmostEqual(ratio, 4.5422, places=4)
        self.assertGreaterEqual(ratio, 4.5)

    def test_one_step_lighter_than_the_aa_grey_fails_on_white(self):
        self.assertLess(validate.contrast_ratio("#777777", WHITE), 4.5)

    def test_the_ratio_does_not_depend_on_argument_order(self):
        self.assertEqual(
            validate.contrast_ratio(AA_GREY, WHITE),
            validate.contrast_ratio(WHITE, AA_GREY),
        )


class SemanticResolution(unittest.TestCase):
    def test_each_reference_resolves_to_its_primitive_value(self):
        resolved = validate.resolve_semantic(
            {
                "id": "t",
                "primitives": {"base": "#112233"},
                "semantic": {"bg-primary": "{base}"},
            }
        )

        self.assertEqual(resolved, {"bg-primary": "#112233"})

    def test_a_reference_to_a_missing_primitive_is_rejected(self):
        with self.assertRaises(ValueError) as raised:
            validate.resolve_semantic(
                {"id": "t", "primitives": {}, "semantic": {"bg-primary": "{gone}"}}
            )

        self.assertIn("Missing primitive 'gone'", str(raised.exception))
        self.assertIn("bg-primary", str(raised.exception))

    def test_a_literal_hex_value_is_rejected_as_a_reference(self):
        with self.assertRaises(ValueError) as raised:
            validate.resolve_semantic(
                {"id": "t", "primitives": {}, "semantic": {"bg-primary": "#112233"}}
            )

        self.assertIn("Invalid reference format", str(raised.exception))

    def test_a_malformed_reference_is_rejected(self):
        for ref in ("{}", "{ base }", "base", "{base", "{1base}", "{a}{b}"):
            with self.subTest(ref=ref):
                with self.assertRaises(ValueError):
                    validate.resolve_semantic(
                        {"id": "t", "primitives": {"base": "#000000"},
                         "semantic": {"bg-primary": ref}}
                    )


class UniqueIds(unittest.TestCase):
    def test_distinct_ids_produce_no_error(self):
        self.assertEqual(
            validate.validate_unique_ids([theme("a"), theme("b")]), []
        )

    def test_a_repeated_id_is_reported_with_both_positions(self):
        errors = validate.validate_unique_ids(
            [theme("a"), theme("b"), theme("a")]
        )

        self.assertEqual(
            errors,
            ["Duplicate theme ID 'a' at index 2 (first seen at index 0)"],
        )

    def test_a_theme_without_an_id_is_named_by_its_index(self):
        errors = validate.validate_unique_ids([{}, {}])

        self.assertEqual(len(errors), 0)

    def test_two_themes_missing_an_id_are_not_conflated(self):
        """Each gets a distinct placeholder, so neither shadows the other."""
        errors = validate.validate_unique_ids([{}, {}, {}])

        self.assertEqual(errors, [])


class ReferenceValidation(unittest.TestCase):
    def test_sound_references_produce_no_error(self):
        self.assertEqual(validate.validate_refs([theme("a")]), [])

    def test_a_dangling_reference_is_reported_against_its_theme_and_key(self):
        broken = theme("a")
        broken["semantic"]["accent"] = "{nope}"

        errors = validate.validate_refs([broken])

        self.assertEqual(
            errors, ["[a] semantic.accent: references missing primitive 'nope'"]
        )

    def test_a_malformed_reference_is_reported_separately(self):
        broken = theme("a")
        broken["semantic"]["accent"] = "#ff0000"

        errors = validate.validate_refs([broken])

        self.assertEqual(
            errors, ["[a] semantic.accent: invalid reference format '#ff0000'"]
        )

    def test_every_broken_reference_is_reported_not_just_the_first(self):
        broken = theme("a")
        broken["semantic"]["accent"] = "{nope}"
        broken["semantic"]["text-secondary"] = "{also-nope}"

        self.assertEqual(len(validate.validate_refs([broken])), 2)


class ContrastGate(unittest.TestCase):
    def test_a_readable_theme_passes(self):
        self.assertEqual(validate.validate_contrast([theme("a")]), [])

    def test_unreadable_primary_text_is_reported_with_the_measured_ratio(self):
        unreadable = theme("a", **{"text-primary": "#111111"})

        errors = validate.validate_contrast([unreadable])

        self.assertEqual(len(errors), 1)
        self.assertIn("[a] text-primary (#111111) on bg-primary (#000000)", errors[0])
        self.assertIn("< 4.5:1 (WCAG AA fail)", errors[0])

    def test_primary_text_is_checked_even_outside_strict_mode(self):
        unreadable = theme("a", **{"text-primary": "#111111"})

        self.assertEqual(len(validate.validate_contrast([unreadable], strict=False)), 1)

    def test_primary_text_is_held_to_body_contrast_not_the_ui_threshold(self):
        """A colour that clears 3:1 but not 4.5:1 must still be rejected.

        Body text and UI components have different bars; a fixture that
        fails both cannot tell them apart.
        """
        ratio = validate.contrast_ratio(UI_GREY, BLACK)
        self.assertGreater(ratio, 3.0)
        self.assertLess(ratio, 4.5)

        errors = validate.validate_contrast([theme("a", **{"text-primary": UI_GREY})])

        self.assertEqual(len(errors), 1)
        self.assertIn("< 4.5:1 (WCAG AA fail)", errors[0])

    def test_secondary_text_is_held_to_body_contrast_not_the_ui_threshold(self):
        errors = validate.validate_contrast(
            [theme("a", **{"text-secondary": UI_GREY})], strict=True
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("text-secondary", errors[0])
        self.assertIn("< 4.5:1 (WCAG AA fail)", errors[0])

    def test_secondary_text_is_only_checked_under_strict(self):
        dim = theme("a", **{"text-secondary": "#111111"})

        self.assertEqual(validate.validate_contrast([dim], strict=False), [])

        errors = validate.validate_contrast([dim], strict=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("text-secondary", errors[0])

    def test_the_accent_is_held_to_the_three_to_one_ui_threshold(self):
        dim = theme("a", accent="#333333")

        errors = validate.validate_contrast([dim], strict=True)

        self.assertEqual(len(errors), 1)
        self.assertIn("< 3.0:1 (visibility fail)", errors[0])

    def test_an_accent_between_three_and_four_and_a_half_is_accepted(self):
        """The accent is a UI role, so AA body text is the wrong bar for it."""
        mid = theme("a", accent=UI_GREY)
        ratio = validate.contrast_ratio(UI_GREY, BLACK)
        self.assertGreater(ratio, 3.0)
        self.assertLess(ratio, 4.5)

        self.assertEqual(validate.validate_contrast([mid], strict=True), [])

    def test_an_unresolvable_theme_is_reported_once_and_skipped(self):
        broken = theme("a")
        broken["semantic"]["bg-primary"] = "{gone}"

        errors = validate.validate_contrast([broken], strict=True)

        self.assertEqual(len(errors), 1)
        self.assertIn("Missing primitive 'gone'", errors[0])

    def test_every_failing_theme_is_reported(self):
        errors = validate.validate_contrast(
            [
                theme("a", **{"text-primary": "#111111"}),
                theme("b", **{"text-primary": "#111111"}),
            ]
        )

        self.assertEqual(len(errors), 2)


class OptionalTokenThresholds(unittest.TestCase):
    """ADR-038 amendments: each optional token has its own reference and bar."""

    def test_an_absent_optional_token_is_not_checked(self):
        self.assertEqual(validate.validate_contrast([theme("a")], strict=True), [])

    def test_text_label_is_held_to_body_text_contrast(self):
        failing = theme("a", **{"text-label": "#111111"})

        errors = validate.validate_contrast([failing], strict=True)

        self.assertEqual(len(errors), 1)
        self.assertIn("text-label", errors[0])
        self.assertIn("< 4.5:1 (WCAG AA fail)", errors[0])

    def test_text_muted_is_held_to_the_incidental_threshold(self):
        passing = theme("a", **{"text-muted": UI_GREY})
        failing = theme("b", **{"text-muted": "#333333"})

        self.assertEqual(validate.validate_contrast([passing], strict=True), [])

        errors = validate.validate_contrast([failing], strict=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("< 3.0:1 (UI/incidental fail)", errors[0])

    def test_accent_bright_and_icon_accent_are_ui_roles(self):
        for token in ("accent-bright", "icon-accent"):
            with self.subTest(token=token):
                errors = validate.validate_contrast(
                    [theme("a", **{token: "#222222"})], strict=True
                )

                self.assertEqual(len(errors), 1)
                self.assertIn("< 3.0:1 (UI fail)", errors[0])

    def test_text_on_accent_is_measured_against_the_accent_fill_not_the_background(self):
        """Amendment 3: it is the foreground on an accent-FILLED control."""
        # A grey that clears 3:1 on the white accent fill but not 4.5:1,
        # so the bar being enforced is pinned, not merely its existence.
        # It would pass comfortably against the black background.
        failing = theme("a", accent=WHITE, **{"text-on-accent": UI_GREY_ON_WHITE})
        self.assertGreater(validate.contrast_ratio(UI_GREY_ON_WHITE, WHITE), 3.0)
        self.assertGreater(validate.contrast_ratio(UI_GREY_ON_WHITE, BLACK), 4.5)

        errors = validate.validate_contrast([failing], strict=True)

        self.assertEqual(len(errors), 1)
        self.assertIn(
            f"text-on-accent ({UI_GREY_ON_WHITE}) on accent (#ffffff)", errors[0]
        )
        self.assertIn("< 4.5:1", errors[0])

    def test_text_on_accent_passes_when_it_contrasts_with_the_fill(self):
        passing = theme("a", accent=WHITE, **{"text-on-accent": BLACK})

        self.assertEqual(validate.validate_contrast([passing], strict=True), [])

    def test_each_status_text_is_measured_against_its_own_tint(self):
        """Amendment 4: the tint is the harder reference than the card."""
        # Clears 3:1 on the tint but not 4.5:1, and would pass against
        # bg-primary — so this pins both the reference and the bar.
        failing = theme(
            "a",
            **{"status-text-success": UI_GREY_ON_WHITE, "tint-green": WHITE},
        )

        errors = validate.validate_contrast([failing], strict=True)

        self.assertEqual(len(errors), 1)
        self.assertIn(
            f"status-text-success ({UI_GREY_ON_WHITE}) on tint-green", errors[0]
        )
        self.assertIn("< 4.5:1", errors[0])

    def test_a_status_text_without_its_tint_is_not_checked(self):
        no_tint = theme("a", **{"status-text-success": "#00ff00"})

        self.assertEqual(validate.validate_contrast([no_tint], strict=True), [])


@unittest.skipIf(validate.jsonschema is None, "jsonschema is not installed")
class SchemaValidation(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (REPO_ROOT / "themes.schema.json").read_text(encoding="utf-8")
        )

    def test_the_shipped_themes_match_the_shipped_schema(self):
        themes = json.loads((REPO_ROOT / "themes.json").read_text(encoding="utf-8"))

        self.assertEqual(validate.validate_schema(themes, self.schema), [])

    def test_a_theme_missing_a_required_field_is_reported(self):
        incomplete = theme("a")
        del incomplete["mode"]

        errors = validate.validate_schema([incomplete], self.schema)

        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Schema validation error: "))

    def test_an_invalid_schema_is_reported_as_such(self):
        errors = validate.validate_schema([], {"type": "not-a-type"})

        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("Schema itself is invalid: "))


class ShippedThemes(unittest.TestCase):
    def setUp(self):
        self.themes = json.loads(
            (REPO_ROOT / "themes.json").read_text(encoding="utf-8")
        )

    def test_every_shipped_theme_has_a_unique_id(self):
        self.assertEqual(validate.validate_unique_ids(self.themes), [])

    def test_every_shipped_reference_resolves(self):
        self.assertEqual(validate.validate_refs(self.themes), [])

    def test_every_shipped_theme_passes_strict_contrast(self):
        self.assertEqual(validate.validate_contrast(self.themes, strict=True), [])

    def test_there_is_more_than_one_theme_to_check(self):
        self.assertGreater(len(self.themes), 1)


class CommandLine(unittest.TestCase):
    def _run(self, *args, env=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "scripts").mkdir()
        shutil.copy(REPO_ROOT / "themes.json", root / "themes.json")
        shutil.copy(REPO_ROOT / "themes.schema.json", root / "themes.schema.json")
        shutil.copy(SCRIPTS_DIR / "validate.py", root / "scripts" / "validate.py")
        return subprocess.run(
            [sys.executable, str(root / "scripts" / "validate.py"), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    def test_the_shipped_themes_pass_in_strict_mode(self):
        result = self._run("--strict")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASSED", result.stdout)
        self.assertIn("(strict mode)", result.stdout)

    def test_a_theme_file_is_read_under_a_non_utf8_locale(self):
        """CI containers commonly run with LC_ALL=C.

        themes.json carries an accented theme name, so a read without an
        explicit encoding dies there rather than validating anything.
        """
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("LANG", "LC_CTYPE", "PYTHONUTF8")
        }
        env["LC_ALL"] = "C"
        env["PYTHONUTF8"] = "0"
        env["PYTHONCOERCECLOCALE"] = "0"

        result = self._run("--strict", env=env)

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
