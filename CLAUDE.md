<!-- SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md - vauchi/themes

> **Inherits**: See root [CLAUDE.md](https://gitlab.com/vauchi/vauchi/-/blob/main/CLAUDE.md).

Theme definitions. Source of truth for all application themes.

## Rules

- 11 required color tokens: `bg-primary`, `bg-secondary`, `bg-tertiary`, `text-primary`, `text-secondary`, `accent`, `accent-dark`, `success`, `error`, `warning`, `border`
- All colors 6-digit hex (`#rrggbb`), mode `"dark"` or `"light"`, IDs lowercase kebab-case
- WCAG AA contrast: `text-primary` on `bg-primary` >= 4.5:1
- Validate: `python3 scripts/validate.py --strict`
