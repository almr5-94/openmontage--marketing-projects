# Audit: image-forge

- Layer: 2 - Cropping and processing
- Source: https://github.com/tdimino/claude-code-minoan (skills/design-media/image-forge)
- Pinned commit: `634a7057c0776806115f91a418bdc3862cc8d53c`
- Licence: MIT
- In scope: skills/design-media/image-forge/ only (5 scripts, 3 references, SKILL.md, README) plus LICENSE. Sparse checkout: the other 1,831 repo files were never fetched.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (scripts called from vendor path)

## Findings

1. All 5 scripts call ImageMagick through subprocess.run with argument lists (never shell=True). No network calls, no env reads.
2. SKILL.md tells the agent to run scripts from ~/.claude/skills/image-forge/ and uses /tmp scratch files. Our wrapper calls the vendored copy and writes only under projects/<id>/assets/fragments/.
3. SKILL.md routes "semantic edits" to Gemini nano-banana-pro (paid). Inside OpenMontage that route is removed. Semantic edits go to the Runway MCP only (owner order 2026-11-19: no pay-per-use image tools).
4. Install hints use `uv pip install --system` (rembg, transparent-background). Not followed: dependencies go into the repo .venv only.
5. Needs ImageMagick 7 (`magick`). abood has neither `magick` nor `convert`, so the scripts cannot run yet. The geometric-mask crops (circle, triangle, hexagon, arc, stripe, polygon) will be Pillow-only and do not need it.

## Conditions before enabling

- DONE 2026-11-19: ImageMagick 7.1.2-36 (official portable build, GitHub release SHA-256 72c8dd02...0c91 verified) installed at ~/.local/imagemagick7, linked as ~/.local/bin/magick. smart_crop.py tested: 1200x800 to 800x800 OK.
