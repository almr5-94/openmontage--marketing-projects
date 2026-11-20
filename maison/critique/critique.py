"""Maison critique gate: rubric scores 1-5 from Claude and from the local models; below 4 goes back.

    from maison.critique.critique import run_critique
    run_critique(project_dir, pngs, house_yaml, claude_scores=None | dict, offline=False)

* The local critic asks the vision model one narrow numeric question per criterion and page (a
  7B model is reliable on narrow questions), takes the median over pages, and has the reasoning
  model judge the copy (voice) and the Arabic edition.
* Claude's scores come from the agent (MCP ``maison_critique`` / ``om maison critique --claude-scores``).
* The gate takes the LOWER of the two critics per criterion. Without Claude's scores the gate is
  blocked, unless ``offline`` was chosen (then it is recorded as local-only).
Writes ``projects/<id>/qa/maison_critique.json`` (a schema-valid ``maison_critique``) and ``.md``.
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib import local_models as lm  # noqa: E402
from schemas.artifacts import validate_artifact  # noqa: E402

CRITERIA = ["restraint", "one_idea", "craft", "cohesion", "archive_dialogue", "voice", "typography",
            "originality", "arabic_edition"]
SEND_BACK = {"restraint": "layout", "one_idea": "inventory", "craft": "assets", "cohesion": "assets",
             "archive_dialogue": "inventory", "voice": "writing", "typography": "layout",
             "originality": "layout", "arabic_edition": "writing"}
PAGE_Q = {
    "restraint": "Rate the calm empty space on this page from 1 (crowded, every surface filled) to 5 "
                 "(generous quiet space around one subject). Answer with one number.",
    "one_idea": "Rate how clearly this page shows ONE subject or idea, from 1 (many things competing) to 5 "
                "(one clear subject). Answer with one number.",
    "craft": "Rate the quality of the imagery on this page from 1 (cheap clip-art, diagrams or simple shapes "
             "drawn in code) to 5 (museum-quality art or fine photography). Answer with one number.",
    "typography": "Rate the typography from 1 (many fonts, boxes, badges, shouting) to 5 (one refined serif, "
                  "quiet hierarchy, generous spacing). Answer with one number.",
}
SET_Q = {
    "cohesion": "These are the pages of one magazine. Rate how cohesive they look as one set (same light, palette, "
                "paper and hand) from 1 (unrelated pictures) to 5 (one commissioned body of work). Answer with one number.",
    "archive_dialogue": "Rate how much these pages pair old historical artworks or objects with contemporary work, "
                        "from 1 (no old material) to 5 (old and new deliberately paired on facing pages). Answer with one number.",
}
ORIGINALITY_Q = ("Does this page imitate a famous luxury brand's logo, monogram, signature pattern, packaging colour "
                 "or magazine masthead? Answer yes or no.")


def _num(s: str) -> Optional[int]:
    m = re.search(r"[1-5]", s)
    return int(m.group(0)) if m else None


def contact_sheet(pngs: list[Path], out: Path) -> Path:
    from tools.graphics.image_crop import ImageCrop

    r = ImageCrop().execute({"operation": "montage", "input_paths": [str(p) for p in pngs], "cols": min(4, len(pngs)),
                             "thumb": "420x594", "label": False, "output_path": str(out)})
    return Path(r.data["path"])


# A page question is only asked where it can apply: imagery questions on pages that carry a picture,
# typography on pages that carry type. A colophon has no image to judge for craft; a text-free ad has no type.
APPLIES = {"restraint": "any", "one_idea": "image", "craft": "image", "typography": "text"}


def page_kinds(pdf: Path) -> list[dict[str, bool]]:
    import pdfplumber

    if not Path(pdf).exists():  # no PDF to read: every question applies to every page
        return []
    with pdfplumber.open(str(pdf)) as d:
        # a picture is a raster image or drawn vector art (code-drawn shapes are exactly what craft must judge);
        # a few hairline rules on a contents page are not a picture
        return [{"image": bool(pg.images) or (len(pg.curves) + len(pg.rects)) > 8,
                 "text": bool((pg.extract_text() or "").strip())} for pg in d.pages]


def local_scores(pngs: list[Path], house: dict[str, Any], copy_text: str, arabic_text: str, work: Path,
                 kinds: Optional[list[dict[str, bool]]] = None) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    kinds = kinds or [{"image": True, "text": True} for _ in pngs]
    for crit, q in PAGE_Q.items():
        want = APPLIES[crit]
        idx = [i for i in range(len(pngs)) if want == "any" or (i < len(kinds) and kinds[i][want])]
        if not idx:
            scores[crit] = {"not_applicable": f"no page in this target carries {want}"}
            continue
        got = [(i + 1, _num(lm.see(pngs[i], q, max_tokens=6))) for i in idx]
        got = [(pg, v) for pg, v in got if v]
        if got:
            vals = [v for _, v in got]
            med = int(statistics.median_low(vals))
            worst = min(got, key=lambda t: t[1])[0]
            scores[crit] = {"score": med, "evidence": f"vision model, pages {[pg for pg, _ in got]} scored {vals} "
                                                      f"(median {med}; weakest p{worst})",
                            "send_back_to": SEND_BACK[crit]}
    if len(pngs) < 2:
        for crit in SET_Q:  # a set question on one page is not a set; the Claude critic judges it
            scores[crit] = {"not_applicable": "single-page target: set criteria need two or more pages"}
        return _rest(scores, pngs, house, copy_text, arabic_text)
    sheet = contact_sheet(pngs, work / "critic-sheet.jpg")
    for crit, q in SET_Q.items():
        v = _num(lm.see(sheet, q, max_tokens=6))
        if v:
            scores[crit] = {"score": v, "evidence": f"vision model on the contact sheet of {len(pngs)} pages: {v}",
                            "send_back_to": SEND_BACK[crit]}
    return _rest(scores, pngs, house, copy_text, arabic_text)


def _rest(scores: dict[str, Any], pngs: list[Path], house: dict[str, Any], copy_text: str,
          arabic_text: str) -> dict[str, Any]:
    flagged = [i + 1 for i, p in enumerate(pngs) if lm.yes(lm.see(p, ORIGINALITY_Q, max_tokens=4))]
    scores["originality"] = {"score": 2 if flagged else 5,
                             "evidence": (f"vision model sees real-house trade dress on p{flagged}" if flagged
                                          else "vision model sees no real-house trade dress on any page; brand_lint runs separately"),
                             "send_back_to": "layout"}
    voice_rules = json.dumps(house.get("voice", {}), ensure_ascii=False)
    a = lm.chat(f"House voice rules: {voice_rules}\n\nCopy from the pages:\n{copy_text[:6000]}\n\n"
                "Rate the copy from 1 (salesy, operational, superlatives) to 5 (specific, sensory, craft-literate). "
                "Reply exactly as: SCORE: <n> | EVIDENCE: <one sentence quoting a phrase>", max_tokens=200, temperature=0)
    v = _num(a.split("SCORE:")[-1][:4]) if "SCORE" in a else _num(a)
    if v:
        scores["voice"] = {"score": v, "evidence": "reasoning model: " + a.split("EVIDENCE:")[-1].strip()[:200],
                           "send_back_to": "writing"}
    if arabic_text.strip():
        a = lm.chat("Arabic copy from a magazine page:\n" + arabic_text[:4000] + "\n\nRate it from 1 (stiff, machine-"
                    "translated feel) to 5 (native literary Arabic prose). Reply exactly as: SCORE: <n> | EVIDENCE: <one "
                    "sentence in English>", max_tokens=200, temperature=0)
        v = _num(a.split("SCORE:")[-1][:4]) if "SCORE" in a else _num(a)
        if v:
            scores["arabic_edition"] = {"score": v, "evidence": "reasoning model: " + a.split("EVIDENCE:")[-1].strip()[:200],
                                        "send_back_to": "writing"}
    else:
        scores["arabic_edition"] = {"not_applicable": "no Arabic text in this target"}
    return scores


def pdf_text(pdf: Path) -> tuple[str, str]:
    import pdfplumber

    with pdfplumber.open(str(pdf)) as d:
        text = "\n".join((p.extract_text() or "") for p in d.pages)
    ar = " ".join(re.findall(r"[؀-ۿ][؀-ۿ\s،.؛]+", text))
    return text, ar


def merge(target: str, critics: list[dict[str, Any]], offline: bool, has_arabic_edition: bool,
          overrides: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    send_backs, ok, overridden = [], True, []
    if not any(c["critic"] == "claude" for c in critics) and not offline:
        ok = False
        send_backs.append({"criterion": "all", "stage": "critique", "notes": "Claude critic has not scored this yet"})
    for crit in CRITERIA:
        vals = [(c["critic"], c["scores"].get(crit)) for c in critics]
        scored = [(who, s) for who, s in vals if s and "score" in s]
        if not scored:
            if crit == "arabic_edition" and not has_arabic_edition:
                continue
            if any(s and "not_applicable" in s for _, s in vals) and crit == "arabic_edition":
                continue
            ok = False
            send_backs.append({"criterion": crit, "stage": SEND_BACK[crit], "notes": "no critic scored this criterion"})
            continue
        who, low = min(scored, key=lambda t: t[1]["score"])
        lows = [(w, sc) for w, sc in scored if sc["score"] < 4]
        approved = {w: d for w, sc in lows for d in (overrides or [])
                    if d.get("criterion") == crit and d.get("critic") == w and sc["score"] >= d.get("max_score", 6)}
        if lows and all(w in approved for w, _ in lows):
            for w, sc in lows:
                overridden.append({"criterion": crit, "critic": w, "score": sc["score"],
                                   "decision_id": approved[w]["decision_id"], "reason": approved[w]["reason"]})
            continue
        if low["score"] < 4:
            ok = False
            send_backs.append({"criterion": crit, "stage": low.get("send_back_to") or SEND_BACK[crit],
                               "notes": f"{who} scored {low['score']}: {low['evidence']}"})
    for c in critics:
        nums = [s["score"] for s in c["scores"].values() if s and "score" in s]
        c["min_score"] = min(nums) if nums else 0
    res = {"version": "1.0", "target": target, "critics": critics, "send_backs": send_backs, "pass": ok}
    if overridden:
        res["overridden"] = overridden
    return res


def run_critique(project_dir: str | Path, pdf: str | Path, house_yaml: str | Path,
                 claude_scores: Optional[dict[str, Any]] = None, offline: bool = False, local: bool = True,
                 pngs: Optional[list[Path]] = None) -> dict[str, Any]:
    pd, pdf = Path(project_dir), Path(pdf)
    house = yaml.safe_load(Path(house_yaml).read_text(encoding="utf-8"))
    work = pd / "qa" / "critic"
    work.mkdir(parents=True, exist_ok=True)
    if pngs is None:
        import subprocess

        pdir = pd / "qa" / "pages"
        pdir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-r", "100", "-png", str(pdf), str(pdir / "page")], capture_output=True, check=False)
        pngs = sorted(pdir.glob("page-*.png"))
    critics: list[dict[str, Any]] = []
    if claude_scores:
        critics.append({"critic": "claude", "model": claude_scores.get("model", "claude"), "scores": claude_scores["scores"]})
    if local:
        text, ar = pdf_text(pdf)
        ls = local_scores(pngs, house, text, ar, work, kinds=page_kinds(pdf))
        for crit in CRITERIA:  # a 7B answer that would not parse is no score, not a crash; the other critic still rules
            if not ls.get(crit):
                ls[crit] = {"not_applicable": "local model gave no usable score for this criterion"}
        critics.append({"critic": "local", "model": f"{lm.detect().get('vision')} + {lm.detect().get('planner')}",
                        "scores": ls})
    import hashlib

    from lib import decision_log

    ovr = decision_log.critique_overrides(pd, hashlib.sha256(pdf.read_bytes()).hexdigest()) if pdf.exists() else []
    res = merge(str(pdf), critics, offline, "ar" in (house.get("languages") or []), overrides=ovr)
    validate_artifact("maison_critique", res)
    out = pd / "qa" / "maison_critique.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [f"# Maison critique: {'PASS' if res['pass'] else 'SEND BACK'}", "", f"Target: `{pdf}`", "",
          "| Criterion | " + " | ".join(c["critic"] for c in critics) + " |", "|---|" + "---|" * len(critics)]
    for crit in CRITERIA:
        row = []
        for c in critics:
            s = c["scores"].get(crit) or {}
            row.append(str(s.get("score", "n/a")) + (f" — {s['evidence'][:90]}" if s.get("evidence") else ""))
        md.append(f"| {crit} | " + " | ".join(r.replace("|", "/") for r in row) + " |")
    if res.get("overridden"):
        md += ["", "## Approved over the critic by the human", ""] + [
            f"- **{o['criterion']}**: {o['critic']} scored {o['score']}; approved in `{o['decision_id']}`: {o['reason']}"
            for o in res["overridden"]]
    if res["send_backs"]:
        md += ["", "## Send back", ""] + [f"- **{s['criterion']}** → `{s['stage']}`: {s['notes']}" for s in res["send_backs"]]
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    res["report"] = str(out.with_suffix(".md"))
    return res
