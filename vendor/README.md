# vendor/: audited third-party skills and servers

Each folder is a pinned, audited copy of an outside project. Read its `AUDIT.md` before using it.
The folders are reference material and runtimes for OpenMontage tool families. Nothing in here is
auto-loaded as an agent skill: the repo's own wrappers and skills decide what is used and how.

| Folder | Upstream | Pinned | Used by |
|---|---|---|---|
| met-museum-mcp-server | cyanheads/met-museum-mcp-server | ae0754c7 (npm 0.10.1) | `.mcp.json` (Node 24), `art_source` |
| image-forge | tdimino/claude-code-minoan | 634a7057 | `image_crop` (ImageMagick 7 path) |
| genart-skill | camilleroux/genart-skill | 36bb7f1f | `skills/creative/generative-art.md` |
| genart-ops | 0xDarkMatter/claude-mods | 47dcf8db | `skills/creative/generative-art.md` |
| collage-layout-expert | curiositech/some_claude_skills | d47e2e5d | `skills/creative/collage.md` (tool grants stripped) |
| mono-color-skill | yanliudesign/mono-color-skill | c8ff7059 | `skills/creative/editorial-design.md` (example art excluded: ASSET-LICENSE) |
| open-design | nexu-io/open-design | 07258801 | `skills/creative/editorial-design.md` |
| awesome-design-skills | bergside/awesome-design-skills | f631a09b | `skills/creative/editorial-design.md` |
| fashion-campaign | claudskills.com copy (upstream deleted) | SHA-256 df089e82 | `skills/creative/fashion-direction.md` |

Refused: `zhongweili/nanobanana-mcp-server` (owner order 2026-11-19: no pay-per-use image tools;
Runway MCP only). Its audit is kept outside the repo.
