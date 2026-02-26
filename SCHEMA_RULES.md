<!-- SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Schema Evolution Rules — Themes

This document defines how `themes.schema.json` may be changed without breaking downstream consumers.

## Schema File

- **`themes.schema.json`** — JSON Schema (2020-12 draft) defining the contract for `themes.json`.
- **`themes.json`** — Theme definitions (source of truth), an array of theme objects.

## What Is a Breaking Change?

A **breaking change** is any schema modification that causes previously valid theme data to fail validation, or that removes data consumers depend on.

| Change | Breaking? | Why |
|--------|-----------|-----|
| Add a field to `required` | **Yes** | Existing themes missing the field will fail validation |
| Remove a property from `properties` | **Yes** | Consumers expecting the property will break |
| Change a property's `type` | **Yes** | Existing data may not match the new type |
| Add `additionalProperties: false` (was absent/true) | **Yes** | Existing data with extra fields will fail |
| Remove an `enum` value | **Yes** | Existing data using that value will fail |
| Add a new optional property | No | Existing data is unaffected |
| Remove a field from `required` | No | Relaxation — existing data still passes |
| Add a new `enum` value | No | Existing data is unaffected |
| Relax `minLength` or remove a `pattern` constraint | No | Relaxation — existing data still passes |

## Rules

### 1. Adding a New Color Token

When a new color token is needed:

1. Add the token to the `colors.properties` in `themes.schema.json`.
2. Add the token to the `colors.required` array.
3. Add the token to every theme in `themes.json`.
4. Update `REQUIRED_COLOR_TOKENS` in `scripts/check-core-contract.py`.
5. Update `core/vauchi-core/src/theme.rs` to deserialize the new token.
6. This is a **breaking change** — all themes and the core parser must be updated together.

### 2. Adding a New Theme-Level Field

When a new top-level field is needed on each theme:

1. Add the property to `themes.schema.json` under `items.properties`.
2. If required, add it to `items.required` and update all themes in `themes.json`.
3. If optional, existing themes remain valid without it.
4. Update `core/vauchi-core/src/theme.rs` if core needs to parse it.

### 3. Removing a Color Token or Field

1. Verify no consumers reference the token (search `core/`, `desktop/`, `ios/`, `android/`, `website/`).
2. Remove from `themes.schema.json` (properties + required).
3. Remove from all themes in `themes.json`.
4. Update `scripts/check-core-contract.py` to remove from `REQUIRED_COLOR_TOKENS`.
5. This triggers a `BREAKING` flag in CI — document the reason in the MR.

### 4. Adding a New Mode

Currently `mode` is restricted to `["dark", "light"]`. To add a new mode:

1. Add the value to the `enum` array in `themes.schema.json`.
2. Update `VALID_MODES` in `scripts/check-core-contract.py`.
3. Update core's `ThemeMode` enum in `theme.rs`.
4. This is a **non-breaking schema change** (enum addition), but a **consumer change** — downstream apps must handle the new mode.

## CI Enforcement

| Job | What It Checks |
|-----|---------------|
| `validate-themes` | `themes.json` passes `themes.schema.json` + WCAG contrast |
| `validate-themes-strict` | Also checks secondary text and accent visibility |
| `check-schema-compat` | No breaking changes vs `main` branch schema |
| `check-core-contract` | `themes.json` matches `core/` parser expectations |

## Versioning Strategy

The schema does not have a formal version number. Breaking changes are detected automatically by CI comparing the MR branch schema against `main`. If a breaking change is intentional:

1. Document the reason in the MR description.
2. Update all themes in `themes.json` in the same MR.
3. Coordinate with `core/` to update `min_app_version` if the change affects OTA content delivery.
4. Update `scripts/check-core-contract.py` to match the new contract.
