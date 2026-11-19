# Audit: genart-ops

- Layer: 4 - Generative art
- Source: https://github.com/0xDarkMatter/claude-mods (skills/genart-ops)
- Pinned commit: `47dcf8db55674f98d5e43aeb122efad016f150c3`
- Licence: MIT
- In scope: skills/genart-ops/ (SKILL.md + 6 references) plus LICENSE. Sparse checkout.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (as a Layer 3 skill)

## Findings

1. No code. allowed-tools "Read Write Bash" is advisory and dropped when converted.
2. Suggests `npm install` of p5, three, simplex-noise and d3-delaunay. Our renderer pins exact versions and loads them locally.
3. One relative link to a threejs-ops skill that is not vendored. Harmless.
