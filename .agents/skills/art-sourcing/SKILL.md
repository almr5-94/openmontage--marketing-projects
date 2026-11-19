---
name: art-sourcing
description: Find and fetch public-domain (CC0) museum art for editorial pages through the art_source tools (met_art, cleveland_art, rijks_art, aic_art). Use before any page that needs real artwork, engravings, objects or textures; the free first step of the editorial art stack.
---

# Art sourcing (Layer 1)

Real museum objects beat invented ones: they carry texture, age and detail no generator fakes.
Everything here is free and runs locally against open museum APIs.

## Tools
| Tool | Collection | Licence check |
|---|---|---|
| `met_art` | The Met, Open Access | `isPublicDomain == true` |
| `cleveland_art` | Cleveland Museum of Art | `share_license_status == "CC0"` |
| `rijks_art` | Rijksmuseum (Linked Art) | licence label "Public Domain" |
| `aic_art` | Art Institute of Chicago | `is_public_domain` (image host often blocks bots: search works, fetch may 403) |

Operations: `search` (query, limit) then `fetch` (object_id, project_dir).
`fetch` re-checks the licence on the object itself and **refuses** anything not public domain —
nothing is written. Files land in `projects/<id>/assets/art/<museum>-<id>.jpg` and are recorded in
`assets/PROVENANCE.json` (source, licence, object id, title, creator, image URL, sha256).

The vendored Met MCP (`vendor/met-museum-mcp-server`, Node 24) is an optional second route for an
MCP client; the Python tools are the source of truth for projects.

## How to search well
- Search by **object and material**, not by mood: "astrolabe brass", "celadon vase", "botanical engraving",
  "lacquer box", "manuscript border", "silk textile", "marble relief".
- Prefer objects photographed on a plain ground — they crop into clean fragments (`image-forge`).
- Fetch 3–6 candidates, review a contact sheet (`image_crop` montage), keep the best 1–2.
- Check resolution: a full-bleed A4 page at 300 dpi needs ~2480×3508 px. Smaller sources go to
  fragments, insets or textures — never upscale a museum image to full bleed (AP-6).

## Rules
- Only these licences enter a project: CC0, public-domain, pexels-license, pixabay-license,
  user-supplied, generated-in-session, derived. `lib/provenance.check_complete` fails anything else.
- **Reference images are never downloaded into a project.** Mood references are described in words.
- Credit line on the colophon page: object title, maker, date, museum, "Public domain / CC0".
