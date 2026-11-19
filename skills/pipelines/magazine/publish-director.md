# Publish Director — Magazine Pipeline

## When to Use

The user approved the proof. Package and hand over. Produce `publish_log`.

## Steps

1. Final files in `projects/<id>/renders/`: `<id>_screen.pdf`, `<id>_print.pdf` (if ordered),
   `<id>_cover.png`, and the page previews folder.
2. Send the PDF(s) and the cover PNG to the user with the session's file-send tool.
3. For a print shop, list the specs alongside: trim, bleed, page count, binding, paper (if the
   brief set one), colour (the PDF is RGB — say so; ask the printer whether they convert).
4. `publish_log.entries[]`: one per deliverable, `status: "exported"`, `export_path`,
   `platform` (`print`, `web`, `email`, `instagram` ...), ISO 8601 `timestamp`.
