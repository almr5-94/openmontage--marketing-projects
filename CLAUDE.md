# OpenMontage

**MANDATORY: Read [`AGENT_GUIDE.md`](AGENT_GUIDE.md) before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## Quick map (pointers only — the rules are in AGENT_GUIDE.md)

- Print studio and Maison: `AGENT_GUIDE.md` → "Print Studio" and "Editorial art stack and Maison"; `maison/README.md`.
- Controls: MCP server `openmontage` (`.mcp.json`) and the `om` CLI (`bin/om`) both call `lib/studio_api.py`.
- Images and video: free sources first, then the Runway MCP connector only, after the user elects the call.
- Gates before export: anti-AI-tells (`om qa`), face gate, Maison critique, brand_lint.
- New here? `START_HERE.md`.
