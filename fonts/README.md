<!-- SPDX-FileCopyrightText: 2026 Mattia Egloff <mattia.egloff@pm.me> -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Brand fonts

The font files behind `font_family` in `tokens.json`. Until this
directory existed the token named three families that no app could
load. Variable TrueType builds, taken verbatim from the Google Fonts
repository, all under the SIL Open Font License 1.1
(`LICENSES/OFL-1.1.txt`).

| Token | Family | File | Axes |
|-------|--------|------|------|
| `display` | Bricolage Grotesque | `BricolageGrotesque[opsz,wdth,wght].ttf` | opsz, wdth, wght |
| `body` | Hanken Grotesk | `HankenGrotesk[wght].ttf`, `-Italic` | wght |
| `mono` | JetBrains Mono | `JetBrainsMono[wght].ttf`, `-Italic` | wght |

The weight ramp in `tokens.json` (400–800) is served from the `wght`
axis; no static instances are shipped. Bundling the files into each app
and mapping the token to the platform font API is the consumer's job
and is tracked in the project's problem records.
