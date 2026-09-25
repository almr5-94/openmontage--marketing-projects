"""Assemble the pilot: plates, animated cut-out props, typeset captions, narration.

Scene lengths come from the narration (timing.json), so picture and voice cannot
drift. Each scene is a plate plus its own cut-out props, and the props are wired
to the handdrawn-alive layer, which carries family A's measured motion: stepped
on twos, a prop event about every 0.64 s, a slow drift on some shots, a fixed
paper grain. Captions are typeset here because the plates are generated with
blank label areas - a drawn model cannot spell.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

PROJECT = Path("projects/pilot-paperfolk")
WORKSPACE = PROJECT / "hyperframes"
LAYER = Path("assets/hyperframes/handdrawn-alive")
PLAYBOOK = Path("styles/handdrawn-paperfolk.yaml")
GROUP_CLASS = {"pop": "alive-pop", "float": "alive-float", "scatter": "alive-scatter"}


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def prop_markup(scene: dict) -> str:
    """One group per motion kind, each holding its copies at spread positions."""
    groups: dict[str, list[str]] = {}
    for prop in scene["props"]:
        cls = GROUP_CLASS[prop["group"]]
        items = groups.setdefault(cls, [])
        count = prop.get("count", 1)
        # copies fan out AWAY from the frame centre, never across it: spreading
        # symmetrically around the anchor walked them over the character's face
        away = 1 if prop["x"] >= 50 else -1
        for i in range(count):
            dx = away * i * (prop["w"] * 1.05)
            dy = -i * 2.2 if prop["group"] == "float" else (i % 2) * 5.5
            items.append(
                f'<img class="prop" src="assets/{scene["id"]}-{prop["id"]}.png" alt="" '
                f'style="left:{prop["x"] + dx:.2f}%; top:{prop["y"] + dy:.2f}%; '
                f'width:{prop["w"]}%" />')
    return "\n          ".join(
        f'<div class="{cls} props">{"".join(items)}</div>' for cls, items in groups.items())


def main() -> None:
    script = json.loads((PROJECT / "script.json").read_text(encoding="utf-8"))
    timing = json.loads((PROJECT / "timing.json").read_text(encoding="utf-8"))
    playbook = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    palette = playbook["visual_language"]["color_palette"]

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    assets = WORKSPACE / "assets"
    assets.mkdir(exist_ok=True)
    for old in assets.glob("*.png"):
        old.unlink()
    shutil.copy2(LAYER / "alive.js", WORKSPACE / "alive.js")
    shutil.copy2(LAYER / "profile-a.js", WORKSPACE / "profile.js")
    shutil.copy2(PROJECT / "narration.mp3", assets / "narration.mp3")
    for scene in script["scenes"]:
        if scene.get("plate"):
            shutil.copy2(PROJECT / "plates" / f'{scene["id"]}.png', assets / f'{scene["id"]}.png')
        for prop in scene["props"]:
            name = f'{scene["id"]}-{prop["id"]}.png'
            shutil.copy2(PROJECT / "props" / name, assets / name)

    by_id = {t["id"]: t for t in timing["scenes"]}
    total = round(timing["total"] + 1.2, 3)

    clips = []
    for i, scene in enumerate(script["scenes"]):
        t = by_id[scene["id"]]
        caption = ""
        if scene.get("caption"):
            big = len(scene["caption"]) <= 4
            caption = (f'<div class="caption {"stat" if big else "line"}">'
                       f'<span>{esc(scene["caption"])}</span></div>')
        drift = "on" if i % 3 == 0 else "off"
        plate = (f'<img class="plate" src="assets/{scene["id"]}.png" alt="" />'
                 if scene.get("plate") else '<div class="plate paper"></div>')
        clips.append(f"""      <section id="{scene['id']}" class="clip" data-start="{t['start']}" data-duration="{t['duration']}">
        <div class="alive-hold" data-drift="{drift}">
          {plate}
          {prop_markup(scene)}
          {caption}
        </div>
      </section>""")

    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>{esc(script['title'])}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <script src="profile.js"></script>
    <script src="alive.js"></script>
    <style>
      body {{ margin: 0; background: {palette['background']}; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden;
               background: {palette['background']}; }}
      .clip {{ position: absolute; inset: 0; }}
      .alive-hold {{ position: absolute; inset: 0; }}
      .plate {{ position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }}
      .plate.paper {{ background: {palette['background']}; }}
      .props {{ position: absolute; inset: 0; }}
      .prop {{ position: absolute; height: auto; }}
      .caption {{ position: absolute; text-align: center; color: {palette['text']}; }}
      .caption.line {{ left: 0; right: 0; bottom: 72px; }}
      /* the stat sits in the lower-left quiet corner: centred at the top it
         landed on the character's face */
      .caption.stat {{ left: 72px; bottom: 96px; text-align: left; }}
      .caption.line span {{ font: 600 56px/1.3 serif; background: {playbook['overlays']['key_term']['bg']};
                            border-radius: 10px; padding: 14px 34px; }}
      .caption.stat span {{ font: 700 130px/1.05 serif; background: {playbook['overlays']['stat_card']['bg']};
                            border: 3px solid {palette['text']}; border-radius: 16px; padding: 10px 44px; }}
      .caption span {{ display: inline-block; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-width="1920" data-height="1080"
         data-duration="{total}" data-fps="24">
{chr(10).join(clips)}
      <audio id="vo" src="assets/narration.mp3" data-start="0"></audio>
      <div class="alive-grain"></div>
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      document.querySelectorAll(".caption span").forEach(function (el) {{
        const start = parseFloat(el.closest(".clip").getAttribute("data-start"));
        tl.fromTo(el, {{ opacity: 0, y: 18 }},
          {{ opacity: 1, y: 0, duration: 0.3,
             ease: HandDrawnAlive.onTwos("power2.out", 0.3, 12) }}, start + 0.25);
      }});
      HandDrawnAlive.apply(tl, document.getElementById("root"));
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
    (WORKSPACE / "index.html").write_text(html, encoding="utf-8")
    props = sum(len(s["props"]) for s in script["scenes"])
    print(f"composition: {WORKSPACE / 'index.html'} — {len(clips)} scenes, {props} prop types, {total}s")


if __name__ == "__main__":
    main()
