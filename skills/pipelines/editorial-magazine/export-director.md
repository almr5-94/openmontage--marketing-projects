# Export Director — Editorial Magazine (stage `publish`)

Only after `quality_gate.pass` is true.

- Print PDF: trim + 3 mm bleed + slug with crop marks (`layout/out/<name>-print.pdf`).
- Screen PDF at trim, PNG per page (these feed the motion stage), a paper-stock proof
  (`outputs: [..., "proofs"]`, `proof_stock` from the brief).
- Hand every file to the user (not just paths) and write `publish_log`.
