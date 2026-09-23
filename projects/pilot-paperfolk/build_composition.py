"""Assemble the pilot's HyperFrames composition from its script, timings and stills.

Scene lengths come from the narration itself (timing.json), so picture and voice
cannot drift apart. Every held scene gets the handdrawn-alive layer, which carries
the measured family A motion: stepped on twos, slow drift on some shots, a fixed
paper grain, and secondary props rather than a moving subject. Captions are
typeset here, in HTML, because the image generator is told to leave label areas
blank - a drawn model cannot spell.
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


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    script = json.loads((PROJECT / "script.json").read_text(encoding="utf-8"))
    timing = json.loads((PROJECT / "timing.json").read_text(encoding="utf-8"))
    playbook = yaml.safe_load(PLAYBOOK.read_text(encoding="utf-8"))
    palette = playbook["visual_language"]["color_palette"]

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "assets").mkdir(exist_ok=True)
    for name in ("alive.js",):
        shutil.copy2(LAYER / name, WORKSPACE / name)
    shutil.copy2(LAYER / "profile-a.js", WORKSPACE / "profile.js")
    shutil.copy2(PROJECT / "narration.mp3", WORKSPACE / "assets" / "narration.mp3")
    for scene in script["scenes"]:
        src = PROJECT / "scenes" / f'{scene["id"]}.png'
        shutil.copy2(src, WORKSPACE / "assets" / src.name)

    by_id = {t["id"]: t for t in timing["scenes"]}
    total = round(timing["total"] + 1.2, 3)  # a beat of quiet at the end

    clips = []
    for i, scene in enumerate(script["scenes"]):
        t = by_id[scene["id"]]
        caption = ""
        if scene.get("caption"):
            big = len(scene["caption"]) <= 4
            caption = (
                f'<div class="caption {"stat" if big else "line"}">'
                f'<span>{esc(scene["caption"])}</span></div>')
        drift = "on" if i % 3 == 0 else "off"   # measured: about a third of shots move
        clips.append(f"""      <section class="clip" data-start="{t['start']}" data-duration="{t['duration']}">
        <div class="alive-hold" data-drift="{drift}">
          <img class="plate" src="assets/{scene['id']}.png" alt="" />
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
      /* captions sit in the quiet part of the frame, on a paper chip, so they
         never land on the figure - the plate itself is drawn with a blank label */
      .caption {{ position: absolute; text-align: center; color: {palette['text']}; }}
      .caption.line {{ left: 0; right: 0; bottom: 72px; }}
      .caption.stat {{ left: 0; right: 0; top: 96px; }}
      .caption.line span {{ font: 600 56px/1.3 serif; background: {playbook['overlays']['key_term']['bg']};
                            border-radius: 10px; padding: 14px 34px; }}
      .caption.stat span {{ font: 700 150px/1.05 serif; background: {playbook['overlays']['stat_card']['bg']};
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
        const clip = el.closest(".clip");
        const start = parseFloat(clip.getAttribute("data-start"));
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
    print(f"composition: {WORKSPACE / 'index.html'} — {len(clips)} scenes, {total}s")


if __name__ == "__main__":
    main()
