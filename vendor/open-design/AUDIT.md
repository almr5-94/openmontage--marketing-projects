# Audit: open-design

- Layer: 6 - Editorial language
- Source: https://github.com/nexu-io/open-design
- Pinned commit: `07258801b9e4ae80553816bb1606af7aa9a63dff`
- Licence: Apache-2.0 (repo); MIT (zhangzara template, own LICENSE)
- In scope: Only design-templates/html-ppt-zhangzara-editorial-tri-tone/, skills/after-hours-editorial-template/, design-templates/magazine-poster/, plus LICENSE. 12 files of a 3.6 GB repo.
- Audited: 2026-11-19 on abood, by reading every in-scope file plus a pattern scan (network, shell, outside paths, env, install hooks, agent-injection text)

## Verdict: ENABLE (as references)

## Findings

1. Mechanical scan found nothing. One JS file (deck-stage.js, slide navigation), with no network or eval.
2. The zhangzara example loads Google Fonts (Bricolage Grotesque). That is an allowed font CDN. Our layouts will self-host fonts so PDFs embed them.
3. The zhangzara template is a slide deck (html-ppt). Useful for its tri-tone tokens, not as a page layout.
