<!-- SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

> **Mirror:** This repo is a read-only mirror of [gitlab.com/vauchi/themes](https://gitlab.com/vauchi/themes). Please open issues and merge requests there.

[![Pipeline](https://img.shields.io/endpoint?url=https://vauchi.gitlab.io/themes/badges/pipeline.json&label=pipeline)](https://gitlab.com/vauchi/themes/-/pipelines)
[![REUSE](https://api.reuse.software/badge/gitlab.com/vauchi/themes)](https://api.reuse.software/info/gitlab.com/vauchi/themes)

# Vauchi Themes

Theme definitions for [Vauchi](https://vauchi.com) — privacy-focused updatable contact cards.

## Themes

| ID | Name | Mode |
|----|------|------|
| `default-dark` | Vauchi Dark | Dark |
| `default-light` | Vauchi Light | Light |
| `catppuccin-mocha` | Catppuccin Mocha | Dark |
| `catppuccin-latte` | Catppuccin Latte | Light |
| `catppuccin-frappe` | Catppuccin Frappé | Dark |
| `catppuccin-macchiato` | Catppuccin Macchiato | Dark |
| `dracula` | Dracula | Dark |
| `nord` | Nord | Dark |
| `solarized-dark` | Solarized Dark | Dark |
| `solarized-light` | Solarized Light | Light |
| `gruvbox-dark` | Gruvbox Dark | Dark |
| `gruvbox-light` | Gruvbox Light | Light |

## Contributing Themes

We welcome community themes! To contribute:

1. Fork this repo
2. Add a new theme object to `themes.json`
3. Run validation: `python3 scripts/validate.py --strict`
4. Submit a merge request

### Theme Structure

Each theme is a JSON object with these fields:

```json
{
  "id": "my-theme",
  "name": "My Theme",
  "version": "1.0.0",
  "author": "Your Name",
  "license": "MIT",
  "source": "https://example.com/my-theme",
  "mode": "dark",
  "colors": {
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
    "border": "#333333"
  }
}
```

### Color Tokens

| Token | Purpose |
|-------|---------|
| `bg-primary` | Main background |
| `bg-secondary` | Card/surface background |
| `bg-tertiary` | Elevated surface / input background |
| `text-primary` | Main text |
| `text-secondary` | Muted/secondary text |
| `accent` | Primary accent (buttons, links) |
| `accent-dark` | Secondary accent |
| `success` | Success state |
| `error` | Error state |
| `warning` | Warning state |
| `border` | Border/divider |

### Requirements

- **ID**: Unique, lowercase, kebab-case (e.g., `my-cool-theme`)
- **Colors**: All 11 tokens required, 6-digit hex format (`#rrggbb`)
- **Mode**: Must be `"dark"` or `"light"`
- **WCAG AA**: `text-primary` on `bg-primary` must have >= 4.5:1 contrast ratio
- **Strict mode**: `text-secondary` >= 4.5:1 contrast, `accent` >= 3:1 visibility

## License

GPL-3.0-or-later
