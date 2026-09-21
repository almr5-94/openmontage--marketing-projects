# Runbook — September Campaign Reels (build on abood pc)

**Audience:** the Claude Code session running on `abood pc`, with the campaign
reel folders on local disk.
**Status:** ready to execute. Nothing in it has been run yet.

## Why this runbook exists

The 16 reel folders and their 32 validated prompts live on `abood pc`. The
session that wrote this runbook was a cloud container with no route to that
machine — no environment targets it, and the local sessions were reporting
`computer_unreachable` at the time of writing. So the build itself could not be
run remotely; this is the executable plan instead.

**Known going in:**

- 16 reel folders exist, holding 32 prompts (2 per reel).
- Every prompt was validated under 5,000 characters.

**Not known — establish these in Step 1, do not assume:**

- where the folders live on disk,
- the file layout inside a reel folder,
- whether the two prompts per reel are image + motion, or two shots,
- whether narration, music, or captions are part of the deliverable,
- the target aspect ratio and duration per reel.

Do not start generating until Step 1 has answered them from disk and Step 2 has
put the open ones to the user.

## Step 0 — Preconditions

FFmpeg and Node are **manual prerequisites** — `make setup` does not install
them. Check them first, because a missing one surfaces much later as a compose
failure:

```bash
python --version     # 3.10+ (repo pins 3.10 in .python-version)
ffmpeg -version      # must resolve
node --version       # 18+ for Remotion, >= 22 for HyperFrames
```

Then get the branch and install:

```bash
cd <path-to>/openmontage--marketing-projects
git fetch origin && git checkout claude/build-abood-pc-8vn0q9 && git pull
make setup
```

`make setup` is the entry point, not `make install`/`install-dev`. It creates
`.venv` (or reuses an active venv/conda env), installs `requirements.txt`, runs
`npm install` in `remotion-composer/` — whose `node_modules` is gitignored, so
Remotion cannot render without it — installs `piper-tts` for zero-key narration,
warms the `npx hyperframes` cache, and copies `.env.example` to `.env` without
overwriting an existing one. Add `make install-dev` only if you need pytest.

A fresh clone is missing three things the runbook later assumes:

- **`.env` starts blank.** Every provider key is optional; the preflight in Step
  3 is what tells you which capabilities are actually configured. Fill in keys
  before preflight if you already know what this batch needs.
- **`music_library/` does not exist** (gitignored). Step 5 says to check it
  before generating music — in a fresh clone it will be empty until the user
  creates it and drops tracks in. Say so rather than silently going to generated
  music.
- **`projects/` does not exist** (gitignored). `init_project` creates it.

Read [`AGENT_GUIDE.md`](../../AGENT_GUIDE.md) before acting. Rule Zero binds this
run: every video goes through the pipeline system, and each stage's director
skill is read **before** any work in that stage. No ad-hoc scripts that call
providers directly.

## Step 1 — Inventory the reel folders (do this first)

```bash
python scripts/september_campaign_inventory.py \
  --root ~/september-campaign \
  --expect-prompts-per-reel 2 \
  --json /tmp/september-reels.json
```

Point `--root` at wherever the campaign folders actually are; the flag is
repeatable if they are split across directories. The script walks each root,
treats any directory holding prompt files as a reel folder, pulls prompts out of
`.txt`/`.md`/`.json`, and checks each against the 5,000-character ceiling.

Read the result against what is claimed above:

| Result | Meaning | Action |
|---|---|---|
| 16 reels, 32 prompts, all `PASS` | Matches the record | Continue to Step 2 |
| Fewer/more than 16 reels | The record is stale or a root is missing | Re-run with the right `--root` before continuing |
| Any `over_limit` | A prompt grew past the limit since validation | Trim it and re-run; never truncate silently at call time |
| Any `count` mismatch | A reel is missing a prompt | Surface the specific reel to the user; do not invent the missing prompt |

Prompts flagged `tight` (within 90% of the limit) pass, but any edit during the
run can push them over — re-run the inventory after editing prompts.

## Step 2 — Pipeline selection (Rule Zero)

Reels are short-form vertical. The plausible manifests in `pipeline_defs/`:

- **`animation.yaml`** — motion-graphics-first reels built from prompts. Production.
- **`cinematic.yaml`** — mood-led, footage/clip-driven cuts. Production.
- **`animated-explainer.yaml`** — a topic carried by narration. Production.
- **`clip-factory.yaml`** — only if the 16 reels are cut from one long source. Beta; say so.

The two-prompts-per-reel shape points at generated visuals rather than a single
long source, so `animation` or `cinematic` is the likely fit — but the prompts
read in Step 1 decide it, and the choice is the user's. Present the shortlist
with tradeoffs, recommend one, wait for approval.

Then read the manifest and the stage directors for the chosen pipeline.
**Path note:** `animated-explainer.yaml`'s director skills live in
`skills/pipelines/explainer/`, not `skills/pipelines/animated-explainer/`. The
other pipelines match their manifest name.

## Step 3 — Mandatory preflight

```bash
python -c "
from tools.tool_registry import registry
import json
registry.discover()
print(json.dumps(registry.provider_menu_summary(), indent=2))
"
```

Present it as a capability menu — "X of Y configured" per capability family, what
can be produced now, then the one-env-var upgrades from each tool's
`install_instructions`. Surface `runtime_warnings[]` verbatim. Check the chosen
manifest's `required_tools` against the registry and report `passed`,
`degraded`, or `blocked` before any generation.

16 reels is a batch, so preflight matters more than usual here: a provider that
is unconfigured or rate-limited costs one wasted pass per reel, not one.

## Step 4 — Runtime and authoring mode (both are hard rules)

```bash
python -c "
from tools.tool_registry import registry
registry.discover()
info = registry._tools['video_compose'].get_info()
print('Render engines:', info.get('render_engines'))
print('Remotion note:', info.get('remotion_note'))
print('HyperFrames note:', info.get('hyperframes_note'))
"
```

**Runtime.** If both Remotion and HyperFrames are available, present both to the
user before locking `render_runtime` — one sentence on what each is best at for
*these reels*, one honest tradeoff each, then a recommendation. Silently picking
a default is forbidden. Log `render_runtime_selection` in `decision_log` with the
full shortlist (both runtimes plus ffmpeg where it applies) in
`options_considered`. If only one runtime is installed, say so explicitly and
record the other as `rejected_because: "runtime not available on this machine"`.

**Authoring mode.** Templated or atelier, logged separately as
`composition_mode`. For 16 campaign reels the tension is real and belongs to the
user: templated is fast, cheap, and consistent across a batch — and is why batch
reels look alike; atelier is the default for hero work and gives each reel its
own visual language at a higher token and iteration cost. A defensible middle is
atelier for the hero reel and templated for the rest, provided the user chooses
it knowingly. For any atelier work, route through
[`skills/meta/taste-direction.md`](../../skills/meta/taste-direction.md) then
[`skills/meta/bespoke-composition.md`](../../skills/meta/bespoke-composition.md).

## Step 5 — Workspace per reel

One project workspace per reel, kebab-case id derived from the reel title:

```bash
python -c "
from lib.checkpoint import init_project
init_project('<reel-slug>', title='<Reel Title>', pipeline_type='<pipeline>')
"
python -m backlot open <reel-slug>
```

Every tool call passes an explicit `output_path` under `projects/<reel-slug>/`.
Assets written to the repo root, cwd, or a temp dir are invisible to the board
and violate the workspace contract. The board is an observer — if it fails to
open, continue the production.

Check `music_library/` before generating music; present existing tracks as
options at proposal.

## Step 6 — Build one reel first, then batch

Moving from sample to batch is a major production change and needs explicit
approval. So:

1. Run **one** reel end to end through the pipeline's stages, stage director
   read before each stage, checkpoints written per
   [`skills/meta/checkpoint-protocol.md`](../../skills/meta/checkpoint-protocol.md).
2. Self-review it against [`skills/meta/reviewer.md`](../../skills/meta/reviewer.md).
3. Show the user the render and the cost of that single reel, with the projected
   cost of the remaining 15.
4. Get approval for the batch, then run the other 15 on the approved path.

If a provider, prompt, or runtime choice changes mid-batch, **append** a new
`decision_log` entry reusing the same `category` and the exact same `subject` as
the entry it supersedes, with the old option moved into `options_considered` and
`rejected_because` noting the change. Never edit the old entry; never reword the
subject.

## Step 7 — Deliverables

Per reel: `projects/<reel-slug>/renders/final.mp4`, with artifacts and assets
under the same workspace. `projects/` is gitignored — renders stay on `abood pc`
and are regenerable from the artifacts. Confirm aspect ratio and duration
against the campaign's platform targets before batching, not after.

## Stop conditions

Stop and report, using the blocker structure in `AGENT_GUIDE.md` (what was
attempted / what failed / auth-provider-bug-or-quality / options / your
recommendation), when:

- the inventory finds something other than 16 reels × 2 passing prompts,
- a required tool is unavailable and the fallback changes the deliverable,
- the locked runtime is unavailable at compose time — never swap silently,
- a motion-led reel would have to degrade to stills,
- batch cost is materially above the projection from the sample reel.

Do not substitute a provider, model, or runtime without approval.
