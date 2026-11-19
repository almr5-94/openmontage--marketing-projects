# Audit: collage-layout-expert

- Layer: 5 - Collage
- Source: https://github.com/curiositech/some_claude_skills (.claude/skills/collage-layout-expert; erichowens/some_claude_skills redirects here)
- Pinned commit: `d47e2e5ded912f448b36da6c391be724d3e50496`
- Licence: MIT
- In scope: The skill folder only (SKILL.md, CHANGELOG, plugin.json, 9 references) plus LICENSE. Sparse checkout of a 578 MB repo.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE AS GUIDANCE ONLY (frontmatter neutralised)

## Findings

1. Confirmed guidance-only: 0 scripts. The compositor (collage tool family) is built by me, as the prompt expected.
2. Likely source of the Snyk warning: frontmatter allowed-tools grants mcp__stability-ai__stability-ai-generate-image (a paid generator), firecrawl search and WebFetch. That would let a paid call skip Rule Zero.
3. The description tells the agent to "use Stability AI" for new images. That conflicts with the election flow.
4. No injection text or hidden instructions found in the 9 references.

## Conditions before enabling

- When converted to a Layer 3 skill, strip allowed-tools and replace the Stability AI routing line with "new images come only from the Runway MCP (owner order 2026-11-19: no pay-per-use image tools at all)".
