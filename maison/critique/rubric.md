# Maison critique rubric

Scored **1–5 with evidence** on each criterion, by two critics: Claude (`critic_claude.md`) and the
local vision + reasoning models (`critic_local.md`). **Any score below 4 sends the work back to its
stage** with the critic's notes. The face gate, provenance check, `brand_lint` and the
anti-AI-tells gate are blocking as well.

| Criterion (key) | 5 looks like | 3 looks like | 1 looks like | Back to stage |
|---|---|---|---|---|
| Restraint and negative space (`restraint`) | one object, a quiet field, nothing to remove | a little crowding; one element too many | every surface filled; shouting type | layout |
| One clear idea per page or ad (`one_idea`) | describable in five words | two ideas competing | no idea; decoration only | inventory / treatments |
| Craft and finish (`craft`) | print-resolution real imagery, material texture, true type | decent images, some flatness | code-drawn shapes, low resolution, fallback fonts | assets |
| Image-set cohesion (`cohesion`) | one light, palette, paper and hand across the set | mostly consistent; an outlier | unrelated pictures | assets / style_lock |
| Archive/contemporary dialogue (`archive_dialogue`) | each work changes how the other reads | paired by subject label only | no archive material | inventory |
| Voice (`voice`) | specific, sensory, craft-literate | generic but clean | salesy, operational, superlatives | writing |
| Typography discipline (`typography`) | two families per script, grid and baseline held, small-caps labels | a slip in hierarchy | many faces, chips, badges, off-grid | layout |
| Originality (`originality`) | nothing resembles a real house's trade dress | a borrowed cliché | a real house's colour, pattern, monogram or masthead | treatments / layout |
| Arabic edition (`arabic_edition`) | native literary Arabic, real Arabic display face, RTL throughout | correct but stiff | machine-translated feel, broken RTL, fallback face | writing / layout |

`arabic_edition` may be `not_applicable` only when the house or brief has no Arabic edition.

## Evidence rule
Every score cites what was seen: a page number and the thing on it ("p3: the dial sits on 60% quiet
ground"). A score without evidence is invalid and counts as 1.
