#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the schema backward-compatibility gate.

themes.schema.json is an array schema, so the contract this gate
protects lives under "items" rather than at the root. Both directions
are asserted: a breaking change must be reported, and a relaxation must
not be.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scriptloader import REPO_ROOT, load

compat = load("check-schema-compat.py")


def object_schema(properties=None, required=None, **extra) -> dict:
    schema = {"type": "object", "properties": properties or {}}
    if required is not None:
        schema["required"] = required
    schema.update(extra)
    return schema


class NewlyRequiredFields(unittest.TestCase):
    def test_adding_a_required_field_is_breaking(self):
        breaking, warnings = compat.check_compat(
            object_schema({"a": {"type": "string"}}, required=["a"]),
            object_schema(
                {"a": {"type": "string"}, "b": {"type": "string"}}, required=["a", "b"]
            ),
        )

        self.assertEqual(
            breaking,
            [
                "BREAKING: Field 'b' added to required "
                "(existing data may lack it)"
            ],
        )
        self.assertEqual(warnings, [])

    def test_dropping_a_required_field_is_a_relaxation_not_a_break(self):
        breaking, warnings = compat.check_compat(
            object_schema({"a": {"type": "string"}}, required=["a"]),
            object_schema({"a": {"type": "string"}}, required=[]),
        )

        self.assertEqual(breaking, [])
        self.assertEqual(
            warnings, ["INFO: Field 'a' no longer required (relaxation)"]
        )

    def test_several_added_required_fields_are_reported_in_sorted_order(self):
        breaking, _ = compat.check_compat(
            object_schema(required=[]),
            object_schema(required=["zeta", "alpha"]),
        )

        self.assertEqual(
            [line.split("'")[1] for line in breaking], ["alpha", "zeta"]
        )


class PropertyChanges(unittest.TestCase):
    def test_removing_a_property_is_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema({"kept": {"type": "string"}, "gone": {"type": "string"}}),
            object_schema({"kept": {"type": "string"}}),
        )

        self.assertEqual(breaking, ["BREAKING: Property 'gone' removed"])

    def test_changing_a_property_type_is_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema({"is_rtl": {"type": "boolean"}}),
            object_schema({"is_rtl": {"type": "string"}}),
        )

        self.assertEqual(
            breaking,
            ["BREAKING: Property 'is_rtl' type changed: boolean -> string"],
        )

    def test_adding_an_optional_property_is_not_breaking(self):
        breaking, warnings = compat.check_compat(
            object_schema({"a": {"type": "string"}}, required=["a"]),
            object_schema(
                {"a": {"type": "string"}, "b": {"type": "string"}}, required=["a"]
            ),
        )

        self.assertEqual(breaking, [])
        self.assertEqual(warnings, ["INFO: New optional property 'b' added"])

    def test_an_untyped_side_is_not_reported_as_a_type_change(self):
        breaking, _ = compat.check_compat(
            object_schema({"a": {"description": "no type declared"}}),
            object_schema({"a": {"type": "string"}}),
        )

        self.assertEqual(breaking, [])

    def test_a_nested_property_removal_is_reported_with_a_dotted_path(self):
        old_meta = {"type": "object", "properties": {"locale": {"type": "string"}}}
        new_meta = {"type": "object", "properties": {}}

        breaking, _ = compat.check_compat(
            object_schema({"_meta": old_meta}),
            object_schema({"_meta": new_meta}),
        )

        self.assertEqual(breaking, ["BREAKING: Property '_meta.locale' removed"])

    def test_a_nested_required_addition_is_breaking(self):
        old_meta = {
            "type": "object",
            "properties": {"locale": {"type": "string"}},
            "required": [],
        }
        new_meta = {
            "type": "object",
            "properties": {"locale": {"type": "string"}},
            "required": ["locale"],
        }

        breaking, _ = compat.check_compat(
            object_schema({"_meta": old_meta}),
            object_schema({"_meta": new_meta}),
        )

        self.assertEqual(
            breaking,
            [
                "BREAKING: Field 'locale' added to required "
                "(existing data may lack it)"
            ],
        )


class AdditionalProperties(unittest.TestCase):
    def test_closing_an_open_schema_is_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema(),
            object_schema(additionalProperties=False),
        )

        self.assertEqual(
            breaking,
            [
                "BREAKING: 'additionalProperties' changed from permissive to "
                "false (existing data with extra fields will fail)"
            ],
        )

    def test_opening_a_closed_schema_is_not_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema(additionalProperties=False),
            object_schema(additionalProperties=True),
        )

        self.assertEqual(breaking, [])

    def test_a_schema_that_was_already_closed_reports_nothing(self):
        breaking, _ = compat.check_compat(
            object_schema(additionalProperties=False),
            object_schema(additionalProperties=False),
        )

        self.assertEqual(breaking, [])

    def test_closing_a_nested_object_is_breaking_with_a_dotted_path(self):
        breaking, _ = compat.check_compat(
            object_schema({"_meta": {"type": "object", "properties": {}}}),
            object_schema(
                {
                    "_meta": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    }
                }
            ),
        )

        self.assertEqual(
            breaking,
            [
                "BREAKING: '_meta.additionalProperties' changed from permissive "
                "to false (existing data with extra fields will fail)"
            ],
        )


class PatternProperties(unittest.TestCase):
    def test_removing_a_pattern_property_is_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema(patternProperties={"^a\\.": {"type": "string"}}),
            object_schema(patternProperties={}),
        )

        self.assertEqual(
            breaking, ["BREAKING: patternProperty '^a\\.' removed"]
        )

    def test_changing_a_pattern_property_type_is_breaking(self):
        breaking, _ = compat.check_compat(
            object_schema(patternProperties={"^a\\.": {"type": "string"}}),
            object_schema(patternProperties={"^a\\.": {"type": "object"}}),
        )

        self.assertEqual(
            breaking,
            [
                "BREAKING: patternProperty '^a\\.' type changed: "
                "string -> object"
            ],
        )

    def test_adding_a_pattern_property_is_not_breaking(self):
        breaking, warnings = compat.check_compat(
            object_schema(patternProperties={}),
            object_schema(patternProperties={"^a\\.": {"type": "string"}}),
        )

        self.assertEqual(breaking, [])
        self.assertEqual(warnings, [])


class ArrayOfItemsSchemas(unittest.TestCase):
    """themes.schema.json is an array; the contract lives under `items`."""

    def test_a_break_inside_items_is_detected(self):
        old = {
            "type": "array",
            "items": object_schema({"id": {"type": "string"}}, required=["id"]),
        }
        new = {
            "type": "array",
            "items": object_schema(
                {"id": {"type": "string"}, "mode": {"type": "string"}},
                required=["id", "mode"],
            ),
        }

        breaking, _ = compat.check_compat(old, new)

        self.assertEqual(
            breaking,
            [
                "BREAKING: Field 'mode' added to required "
                "(existing data may lack it)"
            ],
        )

    def test_extract_item_schema_unwraps_only_arrays_with_items(self):
        items = object_schema({"id": {"type": "string"}})
        flat = object_schema({"id": {"type": "string"}})

        self.assertEqual(
            compat.extract_item_schema({"type": "array", "items": items}), items
        )
        self.assertEqual(compat.extract_item_schema(flat), flat)
        self.assertEqual(
            compat.extract_item_schema({"type": "array"}), {"type": "array"}
        )


class UnchangedAndEmptySchemas(unittest.TestCase):
    def test_an_unchanged_schema_reports_nothing(self):
        schema = object_schema(
            {"a": {"type": "string"}},
            required=["a"],
            patternProperties={"^x\\.": {"type": "string"}},
            additionalProperties=False,
        )

        self.assertEqual(compat.check_compat(schema, json.loads(json.dumps(schema))), ([], []))

    def test_two_empty_schemas_report_nothing(self):
        self.assertEqual(compat.check_compat({}, {}), ([], []))

    def test_the_real_committed_schema_is_compatible_with_itself(self):
        schema_path = REPO_ROOT / "themes.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(compat.check_compat(schema, json.loads(json.dumps(schema))), ([], []))

    def test_the_real_committed_schema_is_the_array_shape_this_gate_unwraps(self):
        """If it ever became a flat object, every check below would move."""
        schema = json.loads(
            (REPO_ROOT / "themes.schema.json").read_text(encoding="utf-8")
        )

        self.assertEqual(schema["type"], "array")
        self.assertEqual(compat.extract_item_schema(schema), schema["items"])

    def test_a_new_required_theme_field_is_reported_against_the_real_schema(self):
        schema = json.loads(
            (REPO_ROOT / "themes.schema.json").read_text(encoding="utf-8")
        )
        tightened = json.loads(json.dumps(schema))
        tightened["items"]["required"].append("author")

        breaking, _ = compat.check_compat(schema, tightened)

        self.assertEqual(
            breaking,
            [
                "BREAKING: Field 'author' added to required "
                "(existing data may lack it)"
            ],
        )


class SchemaAutoDetection(unittest.TestCase):
    def test_exactly_one_schema_file_is_detected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "themes.schema.json").write_text("{}", encoding="utf-8")
            (root / "themes.json").write_text("[]", encoding="utf-8")

            self.assertEqual(
                compat.auto_detect_schema(root), "themes.schema.json"
            )

    def test_no_schema_file_is_not_detected(self):
        with tempfile.TemporaryDirectory() as raw:
            self.assertIsNone(compat.auto_detect_schema(Path(raw)))

    def test_an_ambiguous_pair_of_schema_files_is_not_detected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "a.schema.json").write_text("{}", encoding="utf-8")
            (root / "b.schema.json").write_text("{}", encoding="utf-8")

            self.assertIsNone(compat.auto_detect_schema(root))


class BaselineLookup(unittest.TestCase):
    """`get_baseline_schema` shells out to git; drive a real repository."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self._git("init", "--initial-branch=main")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")
        (self.repo / "x.schema.json").write_text(
            json.dumps({"type": "object", "required": ["a"]}), encoding="utf-8"
        )
        self._git("add", "x.schema.json")
        self._git("commit", "-m", "add schema")

        self._cwd = Path.cwd()
        import os

        os.chdir(self.repo)
        self.addCleanup(os.chdir, self._cwd)

    def _git(self, *args):
        subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_a_committed_schema_is_read_back_from_the_branch(self):
        self.assertEqual(
            compat.get_baseline_schema("main", "x.schema.json"),
            {"type": "object", "required": ["a"]},
        )

    def test_an_unknown_branch_yields_no_baseline(self):
        self.assertIsNone(
            compat.get_baseline_schema("no-such-branch", "x.schema.json")
        )

    def test_a_path_absent_from_the_branch_yields_no_baseline(self):
        self.assertIsNone(compat.get_baseline_schema("main", "absent.json"))

    def test_a_non_json_blob_yields_no_baseline(self):
        (self.repo / "broken.schema.json").write_text("not json", encoding="utf-8")
        self._git("add", "broken.schema.json")
        self._git("commit", "-m", "add broken")

        self.assertIsNone(
            compat.get_baseline_schema("main", "broken.schema.json")
        )


if __name__ == "__main__":
    unittest.main()
