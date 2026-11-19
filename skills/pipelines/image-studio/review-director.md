# Review Director — Image Studio Pipeline

## When to Use

Before the user sees the finished images. Produce `print_review`, then present.

## Look at every image

Open every output file (Read the PNG/JPG) and list it in `frames_viewed`. A review that did not
open an image cannot pass it.

## Checks (each `pass` / `fail` / `not_applicable` with a note)

- **technical** — every `print_render.outputs[].checks_pass` is true; sizes exact.
- **text_fit** — nothing cut, nothing crammed against an edge, safe zones clear.
- **image_quality** — no AI artefacts (hands, warped text, melted objects), no visible
  upscaling blur, faces not cut awkwardly.
- **typography** — hierarchy reads in under two seconds; contrast of text on picture is enough
  (add a shade gradient if not); no orphan single word on a headline's last line.
- **language_and_digits** — spelling checked in every language; Arabic shaped and right-to-left;
  Latin digits only.
- **brief_promise** — the purpose sentence is met; every mandatory copy line present verbatim.
- **brand** — colours, fonts and logo as the brief says.

`status: revise` sends the run back (see executive-producer). On `pass`, present the images
(send the files) and checkpoint `review` as `awaiting_human`.
