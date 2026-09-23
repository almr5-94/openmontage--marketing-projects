# Acceptance criteria for the three hand-drawn style adapters

Written **before** any adapter was trained, as the study requires: "Define the exact sample
size and scoring threshold before training begins." Nothing here is a claim about results.

## The fixed evaluation set

`assets/style/handdrawn/eval-prompts.yaml` holds five cases per family, taken from the study's
validation list. They stay fixed across checkpoints so two runs can be compared.

- Seeds: 7, 101, 202, 303, 404 for the comparable pass, plus five free seeds per case to see
  the spread. One attractive image is not evidence.
- Every case is rendered twice: with the family adapter and without it, same prompt, same seed.
- Nothing is judged from a thumbnail. Outputs are compared at matched subject size against a
  reference frame of that family.

## The five review dimensions

| Dimension | What fails it |
|---|---|
| Structural family identity | A with a black cut-out face; B with pale filled eye whites or flesh shading; C with uniform heavy black outlines |
| Content compliance | the requested action, count, prop or layout is missing or changed |
| Compositional clarity | the silhouette does not carry the action; the quiet-field target is far off |
| Surface and palette behaviour | texture louder than the subject; colours used in the wrong role |
| Contamination | any player control, progress bar, cursor, watermark or accidental interface text |

## Threshold for calling an adapter usable

1. Across the 25 comparable renders of a family (5 cases × 5 seeds), at least **15** are usable
   without retouching, and at least **3 of the 5 cases** have a usable output.
2. **Zero** contamination artefacts across all 25. One is a stop: it means the dataset still
   carries a contaminated frame, and a negative prompt does not fix that.
3. **No recurring structural failure**: the same family-identity error may not appear in more
   than 5 of the 25.
4. The with/without comparison must show a visible difference in the direction of the family.
   If the base model alone scores the same, the adapter has taught nothing.

A family that fails is reported as failing, with the failure named against the diagnosis map in
`skills/creative/handdrawn-styles.md`. Family B starts with the lowest evidence — 43 accepted
frames, most of them detail crops — so it is expected to be the weakest, and that expectation is
recorded here rather than discovered later.

## Caption ablation

Each family is trained twice where GPU time allows: captions as `minimal` (trigger plus literal
content) and as `boilerplate` (plus the family style string). Same images, same settings, same
evaluation. The ablation answers whether the boilerplate helps, instead of assuming that longer
captions are better.

## What the evaluation cannot decide

Whether a *diagram* is factually right. Style matching cannot make a wrong connection list
right — the edges are supplied by a human and checked against the render by a human.
