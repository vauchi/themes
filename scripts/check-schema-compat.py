#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check JSON Schema backward compatibility between two versions.

Detects breaking changes by comparing the current schema against a baseline.
Breaking changes:
  - Adding a field to "required" array (existing data missing it will fail)
  - Removing a field from "properties" (existing data with that field is fine,
    but producers can no longer include it if additionalProperties=false)
  - Changing a property's "type" (existing data may not match new type)
  - Adding additionalProperties=false when it was previously true/absent

Non-breaking (safe) changes:
  - Adding optional properties
  - Relaxing constraints (minLength decrease, pattern removal)
  - Adding new enum values

Usage:
    python3 scripts/check-schema-compat.py <old-schema> <new-schema>
    python3 scripts/check-schema-compat.py --baseline main
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_baseline_schema(branch: str, schema_path: str) -> dict | None:
    """Fetch schema from a git branch."""
    try:
        result = subprocess.run(
            ["git", "show", f"{branch}:{schema_path}"],
            capture_output=True, text=True, check=True,
        )
        return json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def extract_item_schema(schema: dict) -> dict:
    """Extract the items schema from an array schema."""
    if schema.get("type") == "array" and "items" in schema:
        return schema["items"]
    return schema


def compare_required(old_req: list, new_req: list) -> list[str]:
    """Detect newly required fields."""
    errors = []
    added = set(new_req) - set(old_req)
    for field in sorted(added):
        errors.append(f"BREAKING: Field '{field}' added to required (existing data may lack it)")
    return errors


def compare_properties(old_props: dict, new_props: dict, path: str = "") -> list[str]:
    """Detect removed or type-changed properties."""
    errors = []

    # Check for removed properties
    for name in sorted(set(old_props) - set(new_props)):
        errors.append(f"BREAKING: Property '{path}{name}' removed")

    # Check for type changes in shared properties
    for name in sorted(set(old_props) & set(new_props)):
        old_type = old_props[name].get("type")
        new_type = new_props[name].get("type")
        if old_type and new_type and old_type != new_type:
            errors.append(
                f"BREAKING: Property '{path}{name}' type changed: {old_type} -> {new_type}"
            )

        # Recurse into nested objects
        if old_props[name].get("type") == "object" and new_props[name].get("type") == "object":
            old_nested = old_props[name].get("properties", {})
            new_nested = new_props[name].get("properties", {})
            errors.extend(compare_properties(old_nested, new_nested, f"{path}{name}."))

            old_nested_req = old_props[name].get("required", [])
            new_nested_req = new_props[name].get("required", [])
            errors.extend(compare_required(old_nested_req, new_nested_req))

    return errors


def compare_additional_properties(old_schema: dict, new_schema: dict, path: str = "") -> list[str]:
    """Detect additionalProperties becoming more restrictive."""
    errors = []
    old_ap = old_schema.get("additionalProperties", True)
    new_ap = new_schema.get("additionalProperties", True)

    if old_ap is not False and new_ap is False:
        errors.append(
            f"BREAKING: '{path}additionalProperties' changed from permissive to false "
            f"(existing data with extra fields will fail)"
        )
    return errors


def check_compat(old_schema: dict, new_schema: dict) -> tuple[list[str], list[str]]:
    """Compare two schemas and return (breaking_changes, warnings)."""
    breaking = []
    warnings = []

    old_items = extract_item_schema(old_schema)
    new_items = extract_item_schema(new_schema)

    # Compare required fields
    old_req = old_items.get("required", [])
    new_req = new_items.get("required", [])
    breaking.extend(compare_required(old_req, new_req))

    # Compare properties
    old_props = old_items.get("properties", {})
    new_props = new_items.get("properties", {})
    breaking.extend(compare_properties(old_props, new_props))

    # Check additionalProperties
    breaking.extend(compare_additional_properties(old_items, new_items))

    # Check nested objects (e.g., colors)
    for name in set(old_props) & set(new_props):
        if old_props[name].get("type") == "object":
            breaking.extend(
                compare_additional_properties(old_props[name], new_props[name], f"{name}.")
            )

    # Non-breaking: new optional properties
    new_optional = set(new_props) - set(old_props)
    new_required = set(new_req)
    for field in sorted(new_optional - new_required):
        warnings.append(f"INFO: New optional property '{field}' added")

    # Removed from required (relaxation — non-breaking)
    removed_req = set(old_req) - set(new_req)
    for field in sorted(removed_req):
        warnings.append(f"INFO: Field '{field}' no longer required (relaxation)")

    return breaking, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check JSON Schema backward compatibility")
    parser.add_argument("old_schema", nargs="?", help="Path to old (baseline) schema")
    parser.add_argument("new_schema", nargs="?", help="Path to new schema")
    parser.add_argument("--baseline", default=None, help="Git branch to use as baseline (e.g., 'main')")
    args = parser.parse_args()

    repo_root = Path(__file__).parent.parent
    schema_rel = "themes.schema.json"
    new_schema_path = repo_root / schema_rel

    if args.baseline:
        old_schema = get_baseline_schema(f"origin/{args.baseline}", schema_rel)
        if old_schema is None:
            old_schema = get_baseline_schema(args.baseline, schema_rel)
        if old_schema is None:
            print(f"No baseline schema found on branch '{args.baseline}' — skipping compat check")
            return 0
        new_schema = load_json(str(new_schema_path))
    elif args.old_schema and args.new_schema:
        old_schema = load_json(args.old_schema)
        new_schema = load_json(args.new_schema)
    else:
        parser.error("Provide either --baseline or two schema paths")
        return 1

    breaking, warnings = check_compat(old_schema, new_schema)

    for w in warnings:
        print(f"  {w}")

    if breaking:
        print(f"\nBREAKING CHANGES DETECTED ({len(breaking)}):")
        for b in breaking:
            print(f"  {b}")
        print("\nThese changes will break existing content consumers.")
        print("If intentional, update min_app_version in manifest and coordinate with core.")
        return 1

    print(f"\nSchema is backward compatible. ({len(warnings)} info note(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
