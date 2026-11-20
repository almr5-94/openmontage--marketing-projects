"""om -- the OpenMontage studio from a terminal.

Every command calls ``lib/studio_api.py``, the same functions the MCP server exposes, so a
stage run here and one run from Claude produce the same files and decision-log entries
(``actor`` is "human" here). Paid actions show their cost and ask before anything is recorded.

    om new my-issue --pipeline editorial-magazine --title "Winter"
    om status my-issue
    om plan my-issue                      # the local planner model suggests the next step, with its reasons
    om source my-issue --from met --query "lantern"
    om crop my-issue --inputs crop.json
    om compose my-issue --inputs collage.json
    om generate my-issue --stage assets --prompt "..."   # quote -> ask -> election (Runway MCP runs it)
    om layout my-issue issue.json
    om qa my-issue
    om export my-issue
    om stage my-issue <stage> [--tool X --inputs file.json] [--artifacts file.json]
    om maison house new my-house --name "My House" --owner self
    om maison issue new spring --house my-house --theme Water
    om maison critique spring --claude-scores scores.json
    om maison export spring
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import typer  # noqa: E402

from lib import studio_api as api  # noqa: E402

ACTOR = "human"
app = typer.Typer(help="OpenMontage print studio: magazines, Maison issues, drawing series, campaigns.",
                  no_args_is_help=True, add_completion=False)
maison = typer.Typer(help="Maison: house files, issues, drawing series, campaigns, critique, export.",
                     no_args_is_help=True)
app.add_typer(maison, name="maison")
house_app = typer.Typer(no_args_is_help=True, help="House files.")
issue_app = typer.Typer(no_args_is_help=True, help="Maison issues.")
series_app = typer.Typer(no_args_is_help=True, help="Maison drawing series.")
campaign_app = typer.Typer(no_args_is_help=True, help="Maison campaigns.")
maison.add_typer(house_app, name="house")
maison.add_typer(issue_app, name="issue")
maison.add_typer(series_app, name="series")
maison.add_typer(campaign_app, name="campaign")


def _out(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _json_arg(value: Optional[str]) -> Optional[dict[str, Any]]:
    if not value:
        return None
    p = Path(value)
    return json.loads(p.read_text(encoding="utf-8") if p.exists() else value)


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (api.StudioError, PermissionError, ValueError) as e:
        typer.secho(f"refused: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)


@app.command()
def capabilities(families_only: bool = typer.Option(False, "--new", help="only the editorial art families")) -> None:
    """Tool families, their status, and the pipelines."""
    _out(api.list_capabilities(families_only))


@app.command()
def new(project_id: str, pipeline: str = typer.Option(..., "--pipeline", "-p"),
        title: str = typer.Option(..., "--title", "-t")) -> None:
    """Create a project."""
    _out(_guard(api.init_project, project_id, pipeline, title, actor=ACTOR))


@app.command()
def status(project_id: str) -> None:
    """Stages done, next stage, gate results."""
    _out(_guard(api.get_project_status, project_id))


@app.command()
def plan(project_id: str) -> None:
    """Ask the local planner model what to do next; its reasoning is printed, nothing is run."""
    from lib import local_models as lm
    from lib.pipeline_loader import get_stage_review_focus, load_pipeline

    st = _guard(api.get_project_status, project_id)
    nxt = st["next_stage"]
    if not nxt:
        typer.echo("Every stage is complete.")
        return
    focus = get_stage_review_focus(load_pipeline(st["pipeline"]), nxt)
    typer.echo(f"Next stage: {nxt}\nWhat it must achieve: " + "; ".join(focus))
    try:
        info = lm.detect()
        ans = lm.chat(f"Project status: {json.dumps(st)}\nNext stage: {nxt}\nIts goals: {focus}\n"
                      "Propose the 3 concrete next actions for this stage, each with one line of reasoning. "
                      "Free sources first; any paid generation needs the human's election.",
                      system="You are a careful magazine production planner. Be brief and concrete.",
                      max_tokens=500, temperature=0.2)
        typer.echo(f"\nLocal planner ({info.get('planner')} on {info.get('runtime')}):\n{ans.strip()}")
    except Exception as e:  # noqa: BLE001 -- the plan is advice; a missing model is not an error
        typer.echo(f"\n(local planner unavailable: {e})")


@app.command()
def stage(project_id: str, stage_name: str = typer.Argument(..., metavar="STAGE"),
          tool: Optional[str] = typer.Option(None, help="one of the stage's tools"),
          inputs: Optional[str] = typer.Option(None, help="tool inputs: a JSON file or JSON text"),
          artifacts: Optional[str] = typer.Option(None, help="stage artifacts: a JSON file or JSON text"),
          status_: str = typer.Option("completed", "--status"), reason: str = "",
          election_id: Optional[str] = None, approved: bool = typer.Option(False, "--approved")) -> None:
    """Run one stage step (the same call as the MCP run_stage)."""
    _out(_guard(api.run_stage, project_id, stage_name, tool=tool, inputs=_json_arg(inputs),
                artifacts=_json_arg(artifacts), status=status_, reason=reason, actor=ACTOR,
                election_id=election_id, human_approved=approved))


MUSEUMS = {"met": "met_art", "cleveland": "cleveland_art", "rijks": "rijks_art", "aic": "aic_art"}


@app.command()
def source(project_id: str, query: str = typer.Option(..., "--query", "-q"),
           from_: str = typer.Option("met", "--from", help="met, cleveland, rijks, aic, pexels, pixabay"),
           stage_name: str = typer.Option("assets", "--stage"), count: int = 5) -> None:
    """Find free images (CC0 museums, Pexels, Pixabay)."""
    if from_ in ("pexels", "pixabay"):
        _out(_guard(api.search_free_images, project_id, query, from_, count))
    else:
        _out(_guard(api.run_stage, project_id, stage_name, tool=MUSEUMS[from_],
                    inputs={"query": query, "limit": count}, reason=f"source '{query}' from {from_}", actor=ACTOR))


@app.command()
def crop(project_id: str, inputs: str = typer.Option(..., help="image_crop inputs (JSON file or text)"),
         stage_name: str = typer.Option("fragments", "--stage")) -> None:
    """Smart crop, batch, montage or mask (image_crop)."""
    _out(_guard(api.run_stage, project_id, stage_name, tool="image_crop", inputs=_json_arg(inputs), actor=ACTOR))


@app.command()
def compose(project_id: str, inputs: str = typer.Option(..., help="collage inputs (JSON file or text)"),
            stage_name: str = typer.Option("collage", "--stage")) -> None:
    """Build a collage (grid, joiner, cutpaste, moodboard, overlay, mosaic)."""
    _out(_guard(api.run_stage, project_id, stage_name, tool="collage", inputs=_json_arg(inputs), actor=ACTOR))


@app.command()
def generate(project_id: str, prompt: str = typer.Option(...), stage_name: str = typer.Option("assets", "--stage"),
             model: str = "gen4_image", count: int = 1, ratio: str = "1080:1350", resolution: str = "1080p",
             yes: bool = typer.Option(False, "--yes", help="elect without the prompt (you are the human)")) -> None:
    """Quote a Runway generation, ask, and record the election. The Runway MCP makes the call."""
    q = _guard(api.prepare_runway_call, project_id, stage=stage_name, prompt=prompt, model=model, count=count,
               ratio=ratio, resolution=resolution)
    typer.echo(f"{q['ask_human']}\n  model {model} · {count} image(s) · {q['quote']['credits']} credits "
               f"(~${q['quote']['usd']}) · prices from {q['quote']['source']}")
    if not (yes or typer.confirm("Elect this paid call?", default=False)):
        typer.echo("Not elected. Nothing was spent or recorded.")
        raise typer.Exit(0)
    d = _guard(api.record_election, project_id, stage=stage_name, subject=f"Runway {model} x{count}", model=model,
               count=count, resolution=resolution, reason="elected by the human at the om prompt", actor=ACTOR)
    typer.echo(f"Elected: {d['election_id']}. Make the call in Claude with the Runway MCP connector:")
    _out(q["connector_call"])


@app.command()
def layout(project_id: str, issue: str = typer.Argument(..., help="issue JSON file"), name: str = "issue",
           grid: bool = typer.Option(False, "--grid", help="draw the column and baseline grid")) -> None:
    """Lay out and render: print PDF (bleed, crop marks), screen PDF, page PNGs."""
    data = _json_arg(issue)
    if grid:
        data["show_grid"] = True
    _out(_guard(api.export_pdf, project_id, data, name))


@app.command()
def qa(project_id: str, pdf: Optional[str] = None, offline: bool = False,
       no_vision: bool = typer.Option(False, "--no-vision")) -> None:
    """The anti-AI-tells gate (AP-1..AP-7); writes qa/anti_ai_tells.md."""
    r = _guard(api.qa_anti_ai_tells, project_id, pdf, vision=not no_vision, offline=offline)
    _out(r)
    raise typer.Exit(0 if r["pass"] else 1)


@app.command()
def export(project_id: str, issue: Optional[str] = None) -> None:
    """Final files. Maison projects need a passing quality gate first."""
    st = _guard(api.get_project_status, project_id)
    if st["pipeline"].startswith("maison-"):
        _out(_guard(api.maison_export, project_id, issue))
    else:
        _out(_guard(api.export_pdf, project_id, issue or str(api._latest_issue(api.project_dir(project_id))),
                    "issue", ["print_pdf", "screen_pdf", "pngs", "proofs"]))


@house_app.command("new")
def house_new(house_id: str, name: str = typer.Option(...), owner: str = typer.Option("invented", "--owner"),
              lang: list[str] = typer.Option(["en"], "--lang")) -> None:
    """Start a house file (owner: self, client, invented)."""
    _out(_guard(api.maison_new_house, house_id, name, brand_owner=owner, languages=lang))


@house_app.command("list")
def house_list() -> None:
    _out(api.maison_list_houses())


def _maison_new(kind: str):
    def cmd(project_id: str, house: str = typer.Option(...), theme: str = typer.Option(...),
            title: Optional[str] = None) -> None:
        _out(_guard(api.maison_new, kind, project_id, house, theme, title, actor=ACTOR))
    cmd.__doc__ = f"Start a Maison {kind} project."
    return cmd


issue_app.command("new")(_maison_new("issue"))
series_app.command("new")(_maison_new("series"))
campaign_app.command("new")(_maison_new("campaign"))


@maison.command("stage")
def maison_stage(project_id: str, stage_name: str = typer.Argument(..., metavar="STAGE"),
                 tool: Optional[str] = None, inputs: Optional[str] = None, artifacts: Optional[str] = None,
                 reason: str = "", election_id: Optional[str] = None,
                 approved: bool = typer.Option(False, "--approved")) -> None:
    """Run one Maison stage step."""
    _out(_guard(api.maison_run_stage, project_id, stage_name, tool=tool, inputs=_json_arg(inputs),
                artifacts=_json_arg(artifacts), reason=reason, actor=ACTOR, election_id=election_id,
                human_approved=approved))


@maison.command("critique")
def maison_critique(project_id: str, claude_scores: Optional[str] = typer.Option(None, "--claude-scores"),
                    offline: bool = False) -> None:
    """The Maison critique gate; the scores table is written to qa/maison_critique.md."""
    r = _guard(api.maison_critique, project_id, claude_scores=claude_scores, offline=offline)
    typer.echo(Path(r["report"]).read_text(encoding="utf-8"))
    raise typer.Exit(0 if r["pass"] else 1)


@maison.command("approve-critique")
def maison_approve_critique(project_id: str, criterion: str = typer.Option(...),
                            reason: str = typer.Option(..., help="your own reason, in your words"),
                            critic: str = typer.Option("local"), pdf: Optional[str] = None) -> None:
    """Approve one critic's low score for the exact PDF last critiqued (you are the human)."""
    _out(_guard(api.approve_critique, project_id, criterion=criterion, critic=critic, reason=reason, pdf=pdf,
                actor=ACTOR))


@maison.command("gate")
def maison_gate(project_id: str) -> None:
    """Assemble qa/quality_gate.json."""
    r = _guard(api.quality_gate, project_id)
    _out(r)
    raise typer.Exit(0 if r["pass"] else 1)


@maison.command("export")
def maison_export_cmd(project_id: str) -> None:
    """Final files; refused unless the quality gate passes."""
    _out(_guard(api.maison_export, project_id))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
