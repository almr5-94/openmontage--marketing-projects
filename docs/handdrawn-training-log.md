# Training log — hand-drawn family adapters

One adapter per family. A mixed adapter was started first and **stopped at 21%** once the
forensic study showed the three families contradict each other; its output was deleted rather
than kept as a tempting shortcut.

## Setup

- Base model: SDXL 1.0 (`sd_xl_base_1.0.safetensors`) plus the fp16-fix VAE, kept fixed across
  families so dataset and caption choices are what vary.
- Trainer: kohya `sd_scripts` `sdxl_train_network.py`, LoRA rank 32 / alpha 16, AdamW8bit,
  1e-4 unet / 5e-5 text encoder, cosine schedule, bf16, gradient checkpointing, cached latents.
- Hardware: one RTX 5060 Ti, 16 GB. One heavy job at a time.
- Images: 1024 px bucketed; only frames with `split = train` in `dataset-manifest.jsonl`.
- Repeats: 2 per frame, or 4 when a family has fewer than 60 training frames.

## Dataset sizes

| Family | Trigger | Accepted | Of which detail crops | Validation frames | Scenes |
|---|---|---|---|---|---|
| A paper folk | `hdx_paperfolk` | 74 | 0 | 11 | 38 |
| B incised silhouette | `hdx_incise` | 43 | see dataset-report.json | 4 | 16 |
| C bio texture | `hdx_biotext` | 128 | 0 | 12 | 54 |

Validation frames are held out **by scene group**, so a validation frame is never a neighbour of
a training frame. That is what stops a memorised hold from scoring as success.

## Runs

| Run | Family | Captions | Epochs | Result | Notes |
|---|---|---|---|---|---|
| (mixed) | A+B+C | single trigger | — | stopped at 21%, deleted | averaged three contradictory systems |
| 1 | A | boilerplate | 12 | done — 63 train frames, 756 steps | pass: 15/25 usable |
| 2 | C | boilerplate | 12 | done — 116 train frames, 1,392 steps | pass: 17/25 usable |
| 3 | B | boilerplate | 12 | done — 39 train frames, 936 steps | pass: 17/25, weak environments |

Results and their weaknesses: `docs/handdrawn-acceptance-results.md`. The caption
ablation (minimal vs boilerplate) has not been run: all three ran with the boilerplate
variant, and the comparison is the next experiment rather than a finished one.

Stopping is decided by held-out output, not by step count: whether the defining structure
improves, whether new content stays controllable, and whether source-specific objects start
appearing unrequested. Rank and learning rate are only worth tuning after the dataset is clean.
