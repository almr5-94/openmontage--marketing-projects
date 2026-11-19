# Audit: mono-color-skill

- Layer: 6 - Editorial language
- Source: https://github.com/yanliudesign/mono-color-skill
- Pinned commit: `c8ff70597ddedcd65f21a0b528f6a70c35690b0a`
- Licence: MIT (code) + ASSET-LICENSE (art, all rights reserved)
- In scope: Everything except examples/ and reference-* images (excluded by sparse rules because ASSET-LICENSE forbids copying them). 39 files kept: SKILL.md, design-system JSON, swatches SVG, 4 scripts.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (with path override)

## Findings

1. 4 scripts: 2 validators (pure Python), 2 board/poster builders that call rsvg-convert with argument lists. No network.
2. SKILL.md says to save outputs under ~/Desktop/Claude skills/mono-color/. Overridden: outputs go to projects/<id>/.
3. SKILL.md already forbids "in the style of" and artist names, which fits the Maison doctrine.
4. rsvg-convert is not installed on abood (only the board builders need it).

## Conditions before enabling

- Override the output path in the converted skill.
