# Audit: p5.js (runtime for generative_art "p5" mode)

- Source: https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.11.3/p5.min.js
- Version: 1.11.3 (2025-01-22), unmodified minified build
- SHA-256: af51e6211e061b5ae463fbc5c3c1c272e5ca67fa560ed3513fde17325d837506
- SRI (sha512) matches the value cdnjs publishes for this file
- Licence: LGPL-2.1 (redistributed unmodified; see https://github.com/processing/p5.js/blob/main/license.txt)
- Use: loaded from disk by tools/graphics/generative_art.py so a sketch renders offline in headless
  Chromium. It never loads from a CDN at render time.

## Verdict: ENABLE
A widely used library, pinned and integrity-checked. It runs only inside the headless render page.
