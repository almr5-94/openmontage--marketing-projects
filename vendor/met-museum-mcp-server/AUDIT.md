# Audit: met-museum-mcp-server

- Layer: 1 - Real art sourcing
- Source: https://github.com/cyanheads/met-museum-mcp-server
- Pinned commit: `ae0754c77f9939d78b4073d4db22b269d3ee6bdb`
- Licence: Apache-2.0
- In scope: Whole repo (163 files). Runtime build = npm package @cyanheads/met-museum-mcp-server@0.10.1 (matches the pinned source version).
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (local stdio, Node 24)

## Findings

1. Runtime code (src/) contacts only collectionapi.metmuseum.org and images.metmuseum.org. The one other URL, evil.example, is inside a comment about link sanitising.
2. No child_process, eval or Function in src/. Shell use is limited to dev scripts in scripts/ (build, release, devcheck), and the server never runs them.
3. Published package installed with --ignore-scripts: 37 packages, 0 with preinstall/install/postinstall hooks, npm audit 0 vulnerabilities.
4. framework-skills/ and skills/ hold SKILL.md files for developing the server itself. They contain words like "bypass" (auth-bypass flags for dev). These are NOT loaded as OpenMontage skills.
5. Requires Node >= 24. abood has Node 22.23.2, so the server refuses to start. Verified against the official Node v24.22.3 tarball (SHA-256 checked against nodejs.org SHASUMS256).
6. Start-up check (stdio, no key): serverInfo met-museum-mcp-server 0.10.1. Tools: met_list_departments, met_search_collections, met_list_objects, met_get_object.
7. Low adoption (4 stars). Keep pinned to 0.10.1; never use `npx -y` without a version.

## Conditions before enabling

- DONE 2026-11-19: Node v24.22.3 (official tarball, SHA-256 verified against nodejs.org) installed at ~/.local/node24, linked as ~/.local/bin/node24. The system Node 22 is untouched.
- Pin @cyanheads/met-museum-mcp-server@0.10.1, installed with --ignore-scripts into vendor/met-museum-mcp-server/.runtime (git-ignored).
- Every download goes through our art_source CC0 check, even though the server already filters.
