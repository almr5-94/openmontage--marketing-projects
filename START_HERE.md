# Start here

OpenMontage makes videos, and — with the print studio — still images, art magazines, drawing
series and luxury campaigns. You can drive it two ways, and both do exactly the same thing:

| Way | Best for | How |
|---|---|---|
| **Claude** (Claude Code in this folder, or Claude Desktop) | talking it through: "make a 12-page issue about water" | the `openmontage` MCP server starts by itself from `.mcp.json` |
| **The `om` command** | doing one step yourself in a terminal | `bin/om --help` |

## 1. One-time setup (on the machine that holds this folder)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m playwright install chromium
```

- **Local models** (free; used for planning hints, the face gate and the second critic): install
  [Ollama](https://ollama.com) and pull a vision and a planning model, for example
  `ollama pull qwen2.5vl:7b`. The choice lives in `config/local_models.yaml` (LM Studio works too).
- **Free picture search:** put free keys in `.env` — `PEXELS_API_KEY`, `PIXABAY_API_KEY` (see `.env.example`).
- **Met Museum server** (optional, free): needs Node 24 in `~/.local/node24`; `scripts/met_mcp.sh` starts it.
- **Image and video generation:** only through the **Runway** connector in Claude. There is no
  Runway key in this folder and no other paid image service.
- **Claude Desktop:** copy the entries you need from
  `integrations/claude-desktop/claude_desktop_config.snippet.json` into Desktop's own config by hand.

## 2. Your first magazine (free)

```bash
bin/om new spring --pipeline editorial-magazine --title "Spring"
```

```bash
bin/om plan spring
```

```bash
bin/om source spring --from met --query "lantern"
```

Then lay out the pages (`bin/om layout spring issue.json`), check them (`bin/om qa spring`) and
export (`bin/om export spring`). Every choice is written to `projects/spring/decision_log.json`.

## 3. A Maison issue for a house

```bash
bin/om maison house new my-house --name "My House" --owner self --lang en --lang ar
```

```bash
bin/om maison issue new spring-issue --house my-house --theme Water
```

Then the stages run in order (`bin/om status spring-issue` shows the next one). Before export,
four gates must pass: anti-AI-tells, the face gate, the Maison critique (Claude and the local
models score it; anything under 4 out of 5 goes back) and brand_lint. `maison/README.md` explains
the house file, the doctrine and the critique.

## 4. When something costs money

Only Runway generation costs credits. `bin/om generate <project> --prompt "..."` shows the model,
the number of images and the credits, and asks you. Nothing is spent or recorded until you say
yes; then Claude makes the call through the Runway connector.

## 5. Where things are

| What | Where |
|---|---|
| Rules for Claude | `AGENT_GUIDE.md` |
| Pipelines | `pipeline_defs/*.yaml`, stage guides in `skills/pipelines/` |
| Maison | `maison/` |
| Your projects | `projects/<name>/` (pages, PDFs, `qa/` reports, `decision_log.json`, `PROVENANCE.json`) |
| Rejected or superseded pictures | `components/` folders beside the work — nothing is deleted |
