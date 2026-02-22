<!-- SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md - vauchi/themes

> **Inherits**: See root repo [CLAUDE.md](https://gitlab.com/vauchi/vauchi/-/blob/main/CLAUDE.md) for project-wide rules.

Theme definitions for Vauchi. This repo is the source of truth for all application themes.

## Rules

- Every theme must have all 11 color tokens: `bg-primary`, `bg-secondary`, `bg-tertiary`, `text-primary`, `text-secondary`, `accent`, `accent-dark`, `success`, `error`, `warning`, `border`
- All colors must be 6-digit hex format (`#rrggbb`)
- Theme IDs must be unique, lowercase, kebab-case (`^[a-z][a-z0-9-]*$`)
- WCAG AA contrast required: `text-primary` on `bg-primary` >= 4.5:1
- Strict mode also enforces: `text-secondary` contrast >= 4.5:1, `accent` visibility >= 3:1
- `themes.json` must validate against `themes.schema.json`
- `mode` must be `"dark"` or `"light"`

## Structure

```
themes.json            # Theme definitions (source of truth)
themes.schema.json     # JSON Schema for validation
scripts/validate.py    # Schema + WCAG contrast validation
```

## Commands

```bash
# Validate themes (CI runs this)
python3 scripts/validate.py

# Strict validation (blocks merge in CI)
python3 scripts/validate.py --strict
```

## Consumers

- `core/vauchi-core` — loads at runtime via `load_themes_from_json()`
- `desktop/` — bundled as Tauri resources
- iOS/Android — bundled as app resources
- CDN — published for over-the-air updates via content system
- `website/` — build-manifest.py reads `../themes/themes.json`

## Adding a Theme

1. Add a new object to `themes.json` with a unique `id`
2. Include all 11 required color tokens
3. Set `mode` to `"dark"` or `"light"`
4. Run `python3 scripts/validate.py --strict` to verify WCAG compliance
5. Submit a merge request
