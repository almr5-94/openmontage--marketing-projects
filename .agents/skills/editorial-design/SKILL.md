---
name: editorial-design
description: Lay out print magazines, art pages and campaign pages (cover, contents, spreads, full-bleed art, pull-quote, back cover) with the editorial_layout tool on the curated OFL type library - trims, bleed, crop marks, 12-column and baseline grids, RTL Arabic, print PDF and page PNGs.
---

# Editorial design (Layer 6)

Built on `page_render` (Chromium) and `print-studio/`. Audited references:
- `vendor/mono-color-skill/SKILL.md` — single-colour systems (its output path is overridden to the
  project; it never writes to ~/Desktop; its examples are not copied).
- `vendor/open-design/design-templates/magazine-poster/`, `vendor/open-design/skills/after-hours-editorial-template/`
- `vendor/awesome-design-skills/skills/editorial/SKILL.md`

## Type
Only faces in `print-studio/fonts/FONTS.yaml`: Bodoni Moda (Display), EB Garamond, Cormorant
Garamond, Hanken Grotesk, IBM Plex Mono; Arabic: Amiri, IBM Plex Sans Arabic, Cairo, Almarai.
At most two families per script. **Fallback faces (Noto, DejaVu, Liberation, Arial, Helvetica,
system-ui) are banned — the anti-AI-tells gate fails a PDF that embeds them (AP-4).**

## Page craft
- Grid: 12 columns, baseline grid from the text leading; every text block snaps to it.
- Hierarchy from size and space, not from boxes, badges, pills or icons.
- Real images on every spread (museum art, fragments, plates, collages) at ≥300 effective dpi (AP-6).
- No diagrams pretending to be art, no decorative charts (AP-3); no fake barcodes or QR codes.
- Arabic pages: `dir="rtl"`, Arabic faces, Latin digits (`ar-KW-u-nu-latn`), page order mirrored.
- Copy: no filler ("elevate", "unlock", "seamless", "curated experience") — AP-1.

## Output
Print PDF (with bleed and crop marks), screen PDF, PNG per page, then run `qa_anti_ai_tells`
(`om qa`) and fix every finding before export.
