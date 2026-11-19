# Audit: genart-skill

- Layer: 4 - Generative art
- Source: https://github.com/camilleroux/genart-skill
- Pinned commit: `36bb7f1f673580c6d6cbb13a80a15062d6c00459`
- Licence: MIT
- In scope: Whole repo (30 files). Guidance only: SKILL.md plus references on determinism, resolution, features, ethics and platforms.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (as a Layer 3 skill)

## Findings

1. Zero executable code apart from GitHub CI workflows (link checker), which never run locally.
2. .claude/CLAUDE.md and AGENTS.md are instructions for developing that repo. They are not loaded into OpenMontage.
3. Platform references cover NFT/on-chain platforms (Art Blocks, fxhash-style). Irrelevant here; kept for completeness, not surfaced.
4. There is no renderer, so the seeded headless p5.js/SVG renderer (generative_art tool family) is built by me.
