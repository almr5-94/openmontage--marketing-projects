# Export Director

Run only after `quality_gate.pass` is true.

- Every placement file with its pixel size, trim and safe area listed in `publish_log`.
- Print PDF: trim + bleed + crop marks, fonts embedded (the layout tool checks the page size).
- Paper-colour soft proof (`proofs`) so the human sees the stock before printing.
- Screen PDF (bleed cut) and page PNGs for sharing.
- Hand every file over (`SendUserFile`) with its absolute path, and write `publish_log`.
- Nothing is deleted: earlier exports move to `out/components/`.
