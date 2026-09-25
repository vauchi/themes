#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the core contract gate.

This gate encodes what core's serde parser expects. Its strictness is
the point: core deserializes into fixed structs, so a token in neither
contract tier is silently dropped on load rather than reaching
consumers (ADR-038 Amendment 1). Tests therefore assert rejection as
carefully as acceptance.
"""

import io
import json
import unittest
from contextlib import redirect_stdout

from scriptloader import REPO_ROOT, load

contract = load("check-core-contract.py")


def flat_theme(tid="t", **overrides) -> dict:
    theme = {
        "id": tid,
        "name": tid,
        "version": "1.0.0",
        "mode": "dark",
        "colors": {token: "#112233" for token in contract.REQUIRED_COLOR_TOKENS},
    }
    theme.update(overrides)
    return theme


def quietly(fn, *args, **kwargs):
    """Run a checker, discarding the warnings it prints."""
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def warnings_from(fn, *args, **kwargs) -> str:
    output = io.StringIO()
    with redirect_stdout(output):
        fn(*args, **kwargs)
    return output.getvalue()


class ThemeShape(unittest.TestCase):
    def test_a_conforming_theme_produces_no_errors(self):
        self.assertEqual(quietly(contract.validate_contract, [flat_theme()]), [])

    def test_a_non_list_document_is_rejected_outright(self):
        self.assertEqual(
            contract.validate_contract({"id": "t"}),
            ["themes.json must be a JSON array"],
        )

    def test_each_missing_required_field_is_reported(self):
        incomplete = flat_theme()
        del incomplete["version"]
        del incomplete["name"]

        errors = quietly(contract.validate_contract, [incomplete])

        self.assertEqual(
            sorted(errors),
            sorted(
                ["[t] Missing required field: version", "[t] Missing required field: name"]
            ),
        )

    def test_a_theme_without_an_id_is_named_by_its_index(self):
        errors = quietly(contract.validate_contract, [{}])

        self.assertTrue(all(e.startswith("[<index 0>]") for e in errors), errors)

    def test_an_unknown_mode_is_rejected(self):
        errors = quietly(contract.validate_contract, [flat_theme(mode="sepia")])

        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid mode 'sepia'", errors[0])

    def test_both_documented_modes_are_accepted(self):
        for mode in ("dark", "light"):
            with self.subTest(mode=mode):
                self.assertEqual(
                    quietly(contract.validate_contract, [flat_theme(mode=mode)]), []
                )

    def test_an_unknown_theme_field_warns_but_does_not_fail(self):
        """serde ignores unknown fields, so this is not a violation."""
        odd = flat_theme(nickname="spooky")

        self.assertEqual(quietly(contract.validate_contract, [odd]), [])
        self.assertIn(
            "Unknown fields", warnings_from(contract.validate_contract, [odd])
        )

    def test_the_documented_optional_fields_do_not_warn(self):
        rich = flat_theme(author="a", license="GPL-3.0-or-later", source="x")

        self.assertEqual(
            warnings_from(contract.validate_contract, [rich]), ""
        )

    def test_every_theme_in_the_list_is_checked(self):
        errors = quietly(
            contract.validate_contract,
            [flat_theme("a", mode="sepia"), flat_theme("b", mode="mauve")],
        )

        self.assertEqual(len(errors), 2)


class ColorTokens(unittest.TestCase):
    def test_a_missing_required_token_is_reported(self):
        theme = flat_theme()
        del theme["colors"]["accent"]

        errors = quietly(contract.validate_contract, [theme])

        self.assertEqual(errors, ["[t] Missing color token: accent"])

    def test_a_six_digit_hex_colour_is_accepted(self):
        theme = flat_theme()
        theme["colors"]["accent"] = "#AbCdEf"

        self.assertEqual(quietly(contract.validate_contract, [theme]), [])

    def test_an_eight_digit_hex_colour_is_accepted_for_alpha_tokens(self):
        theme = flat_theme()
        theme["colors"]["scrim"] = "#11223344"

        self.assertEqual(quietly(contract.validate_contract, [theme]), [])

    def test_a_malformed_colour_is_reported(self):
        for bad in ("#12345", "#1234567", "112233", "red", "#gggggg", ""):
            with self.subTest(value=bad):
                theme = flat_theme()
                theme["colors"]["accent"] = bad

                errors = quietly(contract.validate_contract, [theme])

                self.assertEqual(len(errors), 1)
                self.assertIn(f"Invalid hex color for accent: {bad}", errors[0])

    def test_a_known_optional_token_is_accepted(self):
        theme = flat_theme()
        theme["colors"]["text-on-accent"] = "#ffffff"

        self.assertEqual(quietly(contract.validate_contract, [theme]), [])

    def test_a_token_in_neither_tier_is_rejected_not_merely_warned(self):
        """Core would silently drop it, so the allow-list is the real gate."""
        theme = flat_theme()
        theme["colors"]["bg-quaternary"] = "#112233"

        errors = quietly(contract.validate_contract, [theme])

        self.assertEqual(len(errors), 1)
        self.assertIn("Color tokens outside the contract", errors[0])
        self.assertIn("bg-quaternary", errors[0])

    def test_a_typo_of_a_real_token_is_rejected(self):
        theme = flat_theme()
        theme["colors"]["bg-primry"] = "#112233"

        errors = quietly(contract.validate_contract, [theme])

        self.assertEqual(len(errors), 1)
        self.assertIn("bg-primry", errors[0])

    def test_a_non_dict_colors_block_is_skipped_rather_than_crashing(self):
        self.assertEqual(
            quietly(contract.validate_contract, [flat_theme(colors="oops")]), []
        )


class TokenContract(unittest.TestCase):
    def conforming_tokens(self) -> dict:
        return {
            category: dict(values)
            for category, values in contract.RUST_DESIGN_TOKEN_DEFAULTS.items()
        }

    def test_tokens_matching_the_rust_defaults_produce_no_errors(self):
        self.assertEqual(
            quietly(contract.validate_token_contract, self.conforming_tokens()), []
        )

    def test_a_missing_category_is_reported(self):
        tokens = self.conforming_tokens()
        del tokens["motion"]

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(errors, ["[tokens] Missing category: motion"])

    def test_a_non_object_category_is_reported_with_its_type(self):
        tokens = self.conforming_tokens()
        tokens["spacing"] = [1, 2, 3]

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(
            errors, ["[tokens] spacing must be an object, got list"]
        )

    def test_a_missing_key_names_the_rust_default_it_should_have_had(self):
        tokens = self.conforming_tokens()
        del tokens["touch_target"]["minimum"]

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(
            errors, ["[tokens] touch_target.minimum missing (Rust default: 48)"]
        )

    def test_a_divergent_value_is_reported_with_both_sides(self):
        tokens = self.conforming_tokens()
        tokens["touch_target"]["minimum"] = 44

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(len(errors), 1)
        self.assertIn("touch_target.minimum = 44", errors[0])
        self.assertIn("DesignTokens::default() = 48", errors[0])

    def test_a_string_token_is_compared_by_value_too(self):
        tokens = self.conforming_tokens()
        tokens["font_family"]["mono"] = "Courier"

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(len(errors), 1)
        self.assertIn("font_family.mono = Courier", errors[0])

    def test_an_unknown_category_is_reported(self):
        tokens = self.conforming_tokens()
        tokens["elevation"] = {"low": 1}

        errors = quietly(contract.validate_token_contract, tokens)

        self.assertEqual(len(errors), 1)
        self.assertIn("Unknown categories", errors[0])
        self.assertIn("elevation", errors[0])

    def test_metadata_keys_are_not_treated_as_categories(self):
        tokens = self.conforming_tokens()
        tokens["_spdx"] = "GPL-3.0-or-later"
        tokens["version"] = "2.0.0"

        self.assertEqual(quietly(contract.validate_token_contract, tokens), [])

    def test_an_extra_key_inside_a_category_warns_but_does_not_fail(self):
        """Core ignores it, so it is a note rather than a violation."""
        tokens = self.conforming_tokens()
        tokens["spacing"]["xxl"] = 64

        self.assertEqual(quietly(contract.validate_token_contract, tokens), [])

        warning = warnings_from(contract.validate_token_contract, tokens)
        self.assertIn("WARNING: [tokens] spacing has keys", warning)
        self.assertIn("xxl", warning)
        self.assertIn("will be ignored by core", warning)


class V2Resolution(unittest.TestCase):
    def test_a_hierarchical_theme_is_flattened_to_colors(self):
        resolved = contract.resolve_v2_themes(
            [
                {
                    "id": "t",
                    "primitives": {"base": "#112233"},
                    "semantic": {"bg-primary": "{base}"},
                }
            ]
        )

        self.assertEqual(resolved, [{"id": "t", "colors": {"bg-primary": "#112233"}}])

    def test_the_hierarchical_keys_do_not_survive_flattening(self):
        resolved = contract.resolve_v2_themes(
            [{"id": "t", "primitives": {"b": "#112233"}, "semantic": {"x.y": "{b}"}}]
        )

        self.assertNotIn("primitives", resolved[0])
        self.assertNotIn("semantic", resolved[0])

    def test_an_already_flat_theme_passes_through_untouched(self):
        flat = flat_theme()

        self.assertEqual(contract.resolve_v2_themes([flat]), [flat])

    def test_a_reference_to_a_missing_primitive_is_dropped(self):
        resolved = contract.resolve_v2_themes(
            [{"id": "t", "primitives": {}, "semantic": {"bg-primary": "{gone}"}}]
        )

        self.assertEqual(resolved[0]["colors"], {})

    def test_a_malformed_reference_is_dropped(self):
        resolved = contract.resolve_v2_themes(
            [
                {
                    "id": "t",
                    "primitives": {"base": "#112233"},
                    "semantic": {"ok": "{base}", "bad": "#112233"},
                }
            ]
        )

        self.assertEqual(resolved[0]["colors"], {"ok": "#112233"})

    def test_other_theme_fields_are_carried_over(self):
        resolved = contract.resolve_v2_themes(
            [
                {
                    "id": "t",
                    "name": "T",
                    "mode": "light",
                    "primitives": {"b": "#112233"},
                    "semantic": {"bg-primary": "{b}"},
                }
            ]
        )

        self.assertEqual(resolved[0]["name"], "T")
        self.assertEqual(resolved[0]["mode"], "light")


class ShippedData(unittest.TestCase):
    def test_the_shipped_themes_satisfy_the_core_contract(self):
        raw = json.loads((REPO_ROOT / "themes.json").read_text(encoding="utf-8"))

        errors = quietly(
            contract.validate_contract, contract.resolve_v2_themes(raw)
        )

        self.assertEqual(errors, [])

    def test_the_shipped_tokens_match_the_rust_defaults(self):
        tokens = json.loads((REPO_ROOT / "tokens.json").read_text(encoding="utf-8"))

        self.assertEqual(quietly(contract.validate_token_contract, tokens), [])

    def test_every_shipped_theme_resolves_all_its_required_tokens(self):
        raw = json.loads((REPO_ROOT / "themes.json").read_text(encoding="utf-8"))

        for theme in contract.resolve_v2_themes(raw):
            with self.subTest(theme=theme["id"]):
                self.assertEqual(
                    contract.REQUIRED_COLOR_TOKENS - set(theme["colors"]), set()
                )

    def test_the_two_contract_tiers_do_not_overlap(self):
        self.assertEqual(
            contract.REQUIRED_COLOR_TOKENS & contract.KNOWN_OPTIONAL_COLOR_TOKENS,
            set(),
        )

    # The onboarding welcome artboard draws the Vauchi mark at 88 x 88 on a
    # 390-wide phone frame; Core sizes the Image node from this token
    # (private problems/2026-09-13-device-walk-diverges-from-canvas).
    def test_the_shipped_tokens_size_a_hero_image_as_the_welcome_artboard_does(self):
        tokens = json.loads((REPO_ROOT / "tokens.json").read_text(encoding="utf-8"))

        self.assertEqual(tokens["image"], {"hero_size": 88})


if __name__ == "__main__":
    unittest.main()

