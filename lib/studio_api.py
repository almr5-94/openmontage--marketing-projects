"""The studio's single source of truth.

The MCP server (``mcp_server/openmontage_mcp.py``) and the ``om`` CLI (``cli/om.py``) are thin
wrappers: every action they expose is one function here, so a stage run from Claude Desktop, from
Claude Code or from a terminal produces the same files and a decision-log entry of the same shape.
Only ``actor`` differs (claude, human, local_model).

Rules enforced here, not in the wrappers:
  * a paid action needs an approved election ID (``lib/election.py``) -- no election, no call;
  * images and video are generated only through the Runway MCP connector, which this process
    cannot call: ``prepare_runway_call`` quotes it and returns the exact call for the agent to
    make once the human has elected it;
  * export of a Maison project requires a passing ``quality_gate``;
  * nothing is deleted: tools move superseded media to ``components/``.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from lib import decision_log, election
from lib.paths import REPO_ROOT

HOUSES = REPO_ROOT / "maison" / "houses"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
PRINT_PIPELINES = ("image-studio", "magazine", "editorial-magazine", "maison-issue", "maison-drawing-series",
                   "maison-campaign")
NEW_FAMILIES = ("image_crop", "generative_art", "collage", "editorial_layout")


class StudioError(ValueError):
    """A request the studio refuses, with the reason in plain words."""


# ---------------------------------------------------------------- projects
def projects_dir() -> Path:
    return Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (REPO_ROOT / "projects"))


def project_dir(project_id: str) -> Path:
    pd = projects_dir() / project_id
    if not (pd / "project.json").exists():
        raise StudioError(f"no project {project_id!r} in {projects_dir()} (create it with init_project)")
    return pd


def _marker(project_id: str) -> dict[str, Any]:
    return json.loads((project_dir(project_id) / "project.json").read_text(encoding="utf-8"))


def _registry():
    from tools.tool_registry import registry

    registry.ensure_discovered()
    return registry


def list_capabilities(families_only: bool = False) -> dict[str, Any]:
    """Tool families, their tools and status, plus the pipelines. Read-only."""
    from lib.pipeline_loader import list_pipelines

    reg = _registry()
    cat = reg.capability_catalog()
    fams = {cap: [{"name": t["name"], "provider": t["provider"], "status": t.get("status"),
                   "stability": t.get("stability")} for t in tools] for cap, tools in cat.items()}
    if families_only:
        fams = {k: v for k, v in fams.items() if k in NEW_FAMILIES}
    return {"families": fams, "tool_count": sum(len(v) for v in cat.values()),
            "pipelines": list_pipelines(), "print_pipelines": list(PRINT_PIPELINES),
            "new_families": {k: k in cat for k in NEW_FAMILIES},
            "image_generation": "Runway MCP connector only, after an election (see prepare_runway_call)"}


def init_project(project_id: str, pipeline: str, title: str, *, actor: str = "claude",
                 extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    from lib.checkpoint import init_project as _init
    from lib.pipeline_loader import load_pipeline

    load_pipeline(pipeline)  # raises on an unknown pipeline
    pd = _init(project_id, title=title, pipeline_type=pipeline, pipeline_dir=projects_dir())
    if extra:
        m = json.loads((pd / "project.json").read_text(encoding="utf-8"))
        m.update(extra)
        (pd / "project.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    if not any(d["category"] == "pipeline_selection" for d in decision_log.load(pd)["decisions"]):
        decision_log.record(pd, stage="init", category="pipeline_selection", subject=f"pipeline for {title}",
                            options=[{"option_id": pipeline, "label": pipeline, "score": 1, "reason": "requested"}],
                            selected=pipeline, reason="pipeline named when the project was created", actor=actor)
    return {"project_id": project_id, "project_dir": str(pd), "pipeline": pipeline,
            "stages": _stages(pipeline)}


def _stages(pipeline: str) -> list[str]:
    from lib.checkpoint import get_pipeline_stages

    return get_pipeline_stages(pipeline)


def get_project_status(project_id: str) -> dict[str, Any]:
    pd = project_dir(project_id)
    m = _marker(project_id)
    stages = _stages(m["pipeline_type"])
    done: dict[str, str] = {}
    for s in stages:
        cp = pd / f"checkpoint_{s}.json"
        if cp.exists():
            done[s] = json.loads(cp.read_text(encoding="utf-8")).get("status", "?")
    nxt = next((s for s in stages if done.get(s) != "completed"), None)
    qa = {}
    for name in ("anti_ai_tells.json", "maison_critique.json", "quality_gate.json"):
        f = pd / "qa" / name
        if f.exists():
            qa[name.split(".")[0]] = json.loads(f.read_text(encoding="utf-8")).get("pass")
    return {"project_id": project_id, "title": m.get("title"), "pipeline": m["pipeline_type"],
            "house": m.get("house"), "theme": m.get("theme"), "stages": stages, "stage_status": done,
            "next_stage": nxt, "gates": qa, "decisions": len(decision_log.load(pd)["decisions"])}


def list_assets(project_id: str) -> dict[str, Any]:
    from lib import provenance

    pd = project_dir(project_id)
    recs = {a["path"]: a for a in provenance.load(pd)["assets"]}
    out = []
    for p in sorted(pd.rglob("*")):
        if p.suffix.lower() in IMG_EXT and "components" not in p.parts and "qa" not in p.relative_to(pd).parts:
            rp = str(p.relative_to(pd))
            r = recs.get(rp, {})
            out.append({"path": rp, "kind": r.get("kind"), "licence": r.get("licence"), "source": r.get("source_url")
                        or r.get("source"), "has_provenance": bool(r)})
    return {"project_id": project_id, "count": len(out), "assets": out}


def get_decision_log(project_id: str) -> dict[str, Any]:
    return decision_log.load(project_dir(project_id))


# ---------------------------------------------------------------- stages
def _stage_def(pipeline: str, stage: str) -> dict[str, Any]:
    from lib.pipeline_loader import load_pipeline

    for s in load_pipeline(pipeline)["stages"]:
        if s["name"] == stage:
            return s
    raise StudioError(f"stage {stage!r} is not in pipeline {pipeline!r}: {_stages(pipeline)}")


def run_stage(project_id: str, stage: str, *, tool: Optional[str] = None, inputs: Optional[dict[str, Any]] = None,
              artifacts: Optional[dict[str, Any]] = None, status: str = "completed", reason: str = "",
              actor: str = "claude", election_id: Optional[str] = None, human_approved: bool = False) -> dict[str, Any]:
    """Run one stage step: optionally execute one of the stage's tools, log the decision, and
    write the stage checkpoint when artifacts are given."""
    pd = project_dir(project_id)
    pipeline = _marker(project_id)["pipeline_type"]
    sd = _stage_def(pipeline, stage)
    result: dict[str, Any] | None = None
    cost = 0.0
    if tool:
        if tool not in sd.get("tools_available", []):
            raise StudioError(f"tool {tool!r} is not available in stage {stage!r}; allowed: {sd.get('tools_available')}")
        t = _registry().get(tool)
        if t is None:
            raise StudioError(f"tool {tool!r} is not registered")
        inputs = dict(inputs or {})
        if "project_dir" in (t.input_schema.get("properties") or {}) and "project_dir" not in inputs:
            inputs["project_dir"] = str(pd)
        cost = float(t.estimate_cost(inputs) or 0.0)
        if cost > 0:
            election.require(pd, election_id)
        r = t.execute(inputs)
        result = {"success": r.success, "data": r.data, "artifacts": r.artifacts, "error": r.error,
                  "cost_usd": r.cost_usd}
    entry = decision_log.record(
        pd, stage=stage, category="stage_run", subject=f"{stage}: {tool or 'artifacts'}",
        options=[{"option_id": tool or "artifacts", "label": tool or "write stage artifacts", "score": 1,
                  "reason": f"estimated cost {cost:.2f} USD"}],
        selected=tool or "artifacts", reason=reason or f"run {stage}", actor=actor,
        user_approved=bool(human_approved), election_id=election_id)
    cp = None
    if artifacts is not None:
        from lib.checkpoint import write_checkpoint

        cp = str(write_checkpoint(projects_dir(), project_id, stage, status, artifacts, pipeline_type=pipeline,
                                  human_approval_required=bool(sd.get("human_approval_default")),
                                  human_approved=human_approved))
    return {"project_id": project_id, "stage": stage, "tool": tool, "result": result, "decision": entry,
            "checkpoint": cp}


def record_election(project_id: str, *, stage: str, subject: str, model: str = "gen4_image", count: int = 1,
                    resolution: str = "1080p", seconds: float = 0, reason: str, actor: str = "human") -> dict[str, Any]:
    q = election.quote_runway(model, count, resolution, seconds)
    return election.record_election(project_dir(project_id), stage=stage, subject=subject, quote=q, reason=reason,
                                    actor=actor)


def prepare_runway_call(project_id: str, *, stage: str, prompt: str, model: str = "gen4_image", count: int = 1,
                        ratio: str = "1080:1350", resolution: str = "1080p",
                        reference_images: Optional[list[str]] = None) -> dict[str, Any]:
    """Quote a Runway generation and lint its prompt. Spends nothing and records nothing:
    the human elects it (record_election), then the agent makes the call on the Runway MCP."""
    from maison.critique.brand_lint import scan_text

    project_dir(project_id)
    hits = [h for h in scan_text(prompt, "prompt", set()) if h["severity"] == "block"]
    if hits:
        raise StudioError("the prompt names a protected brand or artist: " + ", ".join(h["term"] for h in hits))
    q = election.quote_runway(model, count, resolution)
    return {"quote": q, "status": "awaiting_election",
            "connector_call": {"server": "Runway MCP", "model": model, "prompt": prompt, "ratio": ratio,
                               "count": count, "reference_images": reference_images or []},
            "after_generation": ["save into assets/generated/ with provenance kind 'generated'",
                                 "run_face_gate on every image that shows a person"],
            "ask_human": f"Generate {count} image(s) with {model} on Runway for {q['credits']} credits "
                         f"(about ${q['usd']})?"}


def search_free_images(project_id: str, query: str, source: str = "pexels", count: int = 5,
                       orientation: Optional[str] = None) -> dict[str, Any]:
    """Pexels / Pixabay search and download (free; needs the free API key in .env)."""
    name = {"pexels": "pexels_image", "pixabay": "pixabay_image"}[source]
    t = _registry().get(name)
    pd = project_dir(project_id)
    slug = "".join(c if c.isalnum() else "-" for c in query.lower()).strip("-")[:40]
    inp: dict[str, Any] = {"query": query, "per_page": max(3, count),
                           "output_path": str(pd / "assets" / "images" / source / f"{slug}.jpg")}
    if orientation:
        inp["orientation"] = orientation
    if source == "pexels":
        inp["download_size"] = "original"  # print needs the full file, not the 1300 px web size
    r = t.execute(inp)
    out = r.data.get("output") or r.data.get("output_path") or (r.artifacts or [None])[0]
    if r.success and out and Path(out).exists():
        from lib import provenance

        provenance.record(pd, out, kind="stock", source=source, licence=f"{source}-license",
                          source_url=r.data.get("pexels_url") or r.data.get("pageURL") or r.data.get("page_url"),
                          creator=r.data.get("photographer") or r.data.get("user"), title=r.data.get("alt"),
                          tool=name)
    return {"success": r.success, "data": r.data, "artifacts": r.artifacts, "error": r.error}


# ---------------------------------------------------------------- gates
def run_face_gate(image: str, mode: str = "auto") -> dict[str, Any]:
    from lib.face_gate import run_face_gate as _fg

    return _fg(image, mode=mode)


def face_gate_project(project_id: str, images: Optional[list[str]] = None, mode: str = "auto") -> dict[str, Any]:
    pd = project_dir(project_id)
    paths = [pd / i for i in images] if images else [pd / a["path"] for a in list_assets(project_id)["assets"]]
    res = [run_face_gate(str(p), mode) for p in paths]
    failed = [r["image"] for r in res if not r["pass"]]
    return {"pass": not failed, "checked": len(res), "people": sum(1 for r in res if r.get("person")),
            "failed": failed, "results": res}


def _latest(pd: Path, pattern: str) -> Optional[Path]:
    c = sorted((pd / "layout" / "out").glob(pattern), key=lambda p: p.stat().st_mtime) if (pd / "layout" / "out").exists() else []
    return c[-1] if c else None


def qa_anti_ai_tells(project_id: str, pdf: Optional[str] = None, html: Optional[str] = None, vision: bool = True,
                     offline: bool = False, critics: bool = True) -> dict[str, Any]:
    from qa.anti_ai_tells import run_gate

    pd = project_dir(project_id)
    pdf_p = Path(pdf) if pdf else _latest(pd, "*-screen.pdf")
    if pdf_p is None:
        raise StudioError("no screen PDF yet: run the layout stage first")
    html_p = Path(html) if html else pd / "layout" / (pdf_p.name.replace("-screen.pdf", ".screen.html"))
    res = run_gate(pdf_p, pd, html_p if html_p.exists() else None, vision=vision, offline=offline, critics=critics)
    return {k: v for k, v in res.items() if k in ("pass", "codes", "failed_pages", "report", "pages")}


def brand_lint(project_id: str) -> dict[str, Any]:
    from maison.critique.brand_lint import lint

    return lint([project_dir(project_id)])


def issue_images(issue: Any) -> list[str]:
    out: list[str] = []
    if isinstance(issue, dict):
        for v in issue.values():
            out += issue_images(v)
    elif isinstance(issue, list):
        for v in issue:
            out += issue_images(v)
    elif isinstance(issue, str) and issue.lower().endswith(IMG_EXT):
        out.append(issue)
    return list(dict.fromkeys(out))


def quality_gate(project_id: str, issue_json: Optional[str] = None, face_mode: str = "auto",
                 face_results: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Assemble the blocking quality_gate from the gates' own outputs and write qa/quality_gate.json."""
    from lib import provenance
    from schemas.artifacts import validate_artifact

    pd = project_dir(project_id)
    ij = Path(issue_json) if issue_json else _latest_issue(pd)
    issue = json.loads(ij.read_text(encoding="utf-8"))
    used = issue_images(issue)
    ai_f = pd / "qa" / "anti_ai_tells.json"
    if not ai_f.exists():
        raise StudioError("run qa_anti_ai_tells first")
    ai = json.loads(ai_f.read_text(encoding="utf-8"))
    fg = face_results or face_gate_project(project_id, used, face_mode)
    prov = provenance.check_complete(pd, [pd / u for u in used])
    bl = brand_lint(project_id)
    mc = pd / "qa" / "maison_critique.json"
    gate = {"version": "1.0", "pdf": str(ai.get("pdf") or _latest(pd, "*-screen.pdf") or ""),
            "anti_ai_tells": {"pass": bool(ai["pass"]), "report": str(pd / "qa" / "anti_ai_tells.md"),
                              "codes": sorted(ai.get("codes", [])), "failed_pages": ai.get("failed_pages", [])},
            "face_gate": {"pass": fg["pass"], "checked": fg["checked"], "people": fg["people"], "failed": fg["failed"]},
            "provenance": prov,
            "brand_lint": {"pass": bl["pass"], "notes": f"{len(bl['findings'])} block, {len(bl['review'])} review"},
            "pass": False}
    ok = ai["pass"] and fg["pass"] and prov["pass"] and bl["pass"]
    if _marker(project_id)["pipeline_type"].startswith("maison-"):
        gate["maison_critique_ref"] = str(mc)
        ok = ok and mc.exists() and json.loads(mc.read_text(encoding="utf-8"))["pass"]
    gate["pass"] = bool(ok)
    validate_artifact("quality_gate", gate)
    (pd / "qa").mkdir(exist_ok=True)
    (pd / "qa" / "quality_gate.json").write_text(json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")
    return gate


def _latest_issue(pd: Path) -> Path:
    c = sorted((pd / "layout").glob("*.issue.json"), key=lambda p: p.stat().st_mtime) if (pd / "layout").exists() else []
    if not c:
        raise StudioError("no issue JSON in layout/: run the layout stage first")
    return c[-1]


# ---------------------------------------------------------------- export
def export_pdf(project_id: str, issue: dict[str, Any] | str, name: str = "issue",
               outputs: Optional[list[str]] = None, proof_stock: Optional[str] = None) -> dict[str, Any]:
    from tools.graphics.editorial_layout import EditorialLayout

    pd = project_dir(project_id)
    if isinstance(issue, str):
        issue = json.loads(Path(issue).read_text(encoding="utf-8"))
    inp: dict[str, Any] = {"issue": issue, "project_dir": str(pd), "name": name,
                           "outputs": outputs or ["print_pdf", "screen_pdf", "pngs"]}
    if proof_stock:
        inp["proof_stock"] = proof_stock
    r = EditorialLayout().execute(inp)
    if not r.success:
        raise StudioError(r.error or "layout failed")
    return {"data": r.data, "artifacts": r.artifacts}


# ---------------------------------------------------------------- maison
def house_layout(project_id_or_house: str) -> dict[str, Any]:
    """The Maison grid preset for editorial_layout, read from a house file: tokens, masthead, trim, bleed."""
    snap = projects_dir() / project_id_or_house / "house.yaml"
    hp = snap if snap.exists() else _house_path(project_id_or_house)
    h = yaml.safe_load(hp.read_text(encoding="utf-8"))
    pal, typ, grid = h.get("palette", {}), h.get("type", {}), h.get("grid", {})
    m = grid.get("margins_mm", {})
    tokens = {"paper": pal.get("paper"), "ink": pal.get("ink"), "ink_soft": pal.get("ink_soft"), "accent": pal.get("accent"),
              "rule": pal.get("rule"), "font_display": typ.get("latin_display"), "font_text": typ.get("latin_text"),
              "baseline_pt": grid.get("baseline_pt", 13)}
    tokens.update({f"margin_{k}": v for k, v in m.items()})
    prod = h.get("production", {})
    return {"tokens": {k: v for k, v in tokens.items() if v is not None}, "masthead": h.get("masthead"),
            "trim": prod.get("trim", "a4"), "bleed_mm": prod.get("bleed_mm", 3), "house": h.get("name")}


def maison_list_houses() -> list[dict[str, Any]]:
    out = []
    for f in sorted(HOUSES.glob("*/house.yaml")):
        h = yaml.safe_load(f.read_text(encoding="utf-8"))
        out.append({"id": f.parent.name, "name": h.get("name"), "brand_owner": h.get("brand_owner"),
                    "languages": h.get("languages"), "path": str(f)})
    return out


def maison_new_house(house_id: str, name: str, *, brand_owner: str = "invented", languages: Optional[list[str]] = None,
                     based_on: str = "maison-example") -> dict[str, Any]:
    from maison.critique.brand_lint import lint

    if brand_owner not in ("self", "client", "invented"):
        raise StudioError("brand_owner must be self, client or invented")
    dst = HOUSES / house_id / "house.yaml"
    if dst.exists():
        raise StudioError(f"house {house_id!r} already exists at {dst}")
    h = yaml.safe_load((HOUSES / based_on / "house.yaml").read_text(encoding="utf-8"))
    h.update({"id": house_id, "name": name, "brand_owner": brand_owner})
    if languages:
        h["languages"] = languages
    dst.parent.mkdir(parents=True)
    dst.write_text(f"# House file, started from {based_on}; edit every field to the real house.\n"
                   + yaml.safe_dump(h, sort_keys=False, allow_unicode=True), encoding="utf-8")
    bl = lint([dst])
    return {"id": house_id, "path": str(dst), "brand_lint": {"pass": bl["pass"], "findings": bl["findings"]}}


def _house_path(house: str) -> Path:
    p = HOUSES / house / "house.yaml"
    if not p.exists():
        raise StudioError(f"no house {house!r}; known: {[h['id'] for h in maison_list_houses()]}")
    return p


def maison_new(kind: str, project_id: str, house: str, theme: str, title: Optional[str] = None,
               actor: str = "claude") -> dict[str, Any]:
    """kind: issue | series | campaign."""
    pipeline = {"issue": "maison-issue", "series": "maison-drawing-series", "campaign": "maison-campaign"}[kind]
    hp = _house_path(house)
    res = init_project(project_id, pipeline, title or f"{house}: {theme}", actor=actor,
                       extra={"house": house, "theme": theme})
    pd = Path(res["project_dir"])
    shutil.copy2(hp, pd / "house.yaml")  # the house as it was when this project started
    return {**res, "house": house, "theme": theme, "house_snapshot": str(pd / "house.yaml")}


def _require_maison(project_id: str) -> None:
    if not _marker(project_id)["pipeline_type"].startswith("maison-"):
        raise StudioError(f"{project_id!r} is not a Maison project")


def maison_run_stage(project_id: str, stage: str, **kw: Any) -> dict[str, Any]:
    _require_maison(project_id)
    return run_stage(project_id, stage, **kw)


def maison_critique(project_id: str, *, pdf: Optional[str] = None, claude_scores: Optional[dict[str, Any] | str] = None,
                    offline: bool = False, local: bool = True) -> dict[str, Any]:
    from maison.critique.critique import run_critique

    _require_maison(project_id)
    pd = project_dir(project_id)
    pdf_p = Path(pdf) if pdf else _latest(pd, "*-screen.pdf")
    if pdf_p is None:
        raise StudioError("no screen PDF yet: run the layout stage first")
    if isinstance(claude_scores, str):
        claude_scores = json.loads(Path(claude_scores).read_text(encoding="utf-8"))
    pngs = None
    pages = pdf_p.parent / (pdf_p.name.replace("-screen.pdf", "") + "-pages")
    if pages.exists():
        pngs = sorted(pages.glob("*.png"))
    res = run_critique(pd, pdf_p, pd / "house.yaml", claude_scores=claude_scores, offline=offline, local=local,
                       pngs=pngs)
    return res


def approve_critique(project_id: str, *, criterion: str, critic: str = "local", reason: str,
                     pdf: Optional[str] = None, actor: str = "human") -> dict[str, Any]:
    """Record the HUMAN's approval of a critic's low score on one criterion, for the PDF last
    critiqued (or ``pdf``). Only the score it saw is covered; a re-render needs a new approval.
    Re-run maison_critique and quality_gate afterwards."""
    import hashlib

    from lib import decision_log

    _require_maison(project_id)
    pd = project_dir(project_id)
    mc = pd / "qa" / "maison_critique.json"
    if not mc.exists():
        raise StudioError("run maison_critique first: there is no send-back to approve")
    res = json.loads(mc.read_text(encoding="utf-8"))
    pdf_p = Path(pdf) if pdf else Path(res["target"])
    if str(pdf_p.resolve()) != str(Path(res["target"]).resolve()):
        raise StudioError(f"the last critique was of {res['target']}, not {pdf_p}: critique it first")
    score = None
    for c in res["critics"]:
        if c["critic"] == critic:
            score = (c["scores"].get(criterion) or {}).get("score")
    if score is None or score >= 4:
        raise StudioError(f"{critic} has no score below 4 on {criterion!r} in the last critique: nothing to approve")
    sha = hashlib.sha256(pdf_p.read_bytes()).hexdigest()
    d = decision_log.record_critique_override(pd, criterion=criterion, critic=critic, score=int(score),
                                              pdf_sha256=sha, reason=reason, actor=actor)
    return {"decision_id": d["decision_id"], "criterion": criterion, "critic": critic, "score": score,
            "pdf": str(pdf_p), "pdf_sha256": sha}


def maison_export(project_id: str, issue: Optional[dict[str, Any] | str] = None, name: Optional[str] = None,
                  proof_stock: Optional[str] = None) -> dict[str, Any]:
    _require_maison(project_id)
    pd = project_dir(project_id)
    qg = pd / "qa" / "quality_gate.json"
    if not qg.exists() or not json.loads(qg.read_text(encoding="utf-8"))["pass"]:
        raise StudioError("export is blocked: qa/quality_gate.json is missing or failing (run the critique stage)")
    ij = Path(issue) if isinstance(issue, str) else None
    if issue is None:
        ij = _latest_issue(pd)
    nm = name or (ij.name.replace(".issue.json", "") if ij else "issue")
    # the export never overwrites the PDF that was reviewed and gated: its hash is what the verdicts certify
    if not nm.endswith("-final"):
        nm += "-final"
    house = yaml.safe_load((pd / "house.yaml").read_text(encoding="utf-8"))
    stock = proof_stock or (house.get("production") or {}).get("paper_stock", "uncoated_offwhite")
    return export_pdf(project_id, str(ij) if ij else issue, nm, ["print_pdf", "screen_pdf", "pngs", "proofs"], stock)
