# Audit: fashion-campaign

- Layer: 7 - Fashion direction
- Source: https://claudskills.com/skills/fashion-campaign/SKILL.md (upstream https://github.com/fancyai-official/skills is 404, org deleted)
- Pinned commit: `n/a. File SHA-256 df089e82630c76494ba2615f5f500bf44c224696e6f65bc702ae61bfc3a22e25, fetched 2026-11-19`
- Licence: Apache-2.0 (per the listing; no LICENSE file available)
- In scope: SKILL.md only (639 lines). The supporting files it references (scripts/generate_campaign_assets.py, reference-bank.md, campaign-kit-template.md, treatment-examples.md) are unavailable: claudskills.com returns 404 for each, and a web search found no mirror.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE AS GUIDANCE ONLY (rewired)

## Findings

1. States it makes no server API calls and ships no keys. True for the file we have: there is no code.
2. Its workflow (intake, visual-intelligence report, 6 worlds, Safe/Bold/Conceptual treatments, cast sheet, shot list, per-shot prompts) is usable. It already stops for the user with AskUserQuestion before production.
3. Its prompt-export step depends on the missing generate_campaign_assets.py. I will write our own exporter that emits shots-<slug>.json and *.prompt.txt for the Runway MCP (the only image generator allowed, owner order 2026-11-19), with the face gate on every result.
4. CONFLICT: it builds treatments around named photographers, make-up artists and hair stylists (examples include living people such as Pat McGrath and Guido Palau). The Maison rule forbids living artists' names in prompts. Names are allowed in internal treatment notes only, and must be stripped from any generation prompt by brand_lint.

## Conditions before enabling

- Record provenance as URL + SHA-256 + fetch date instead of a commit SHA.
- brand_lint also scans for living-artist names in exported prompts.
