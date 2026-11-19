"""brand_lint: block real luxury-house names, their trademarks and living artists in production files.

Maison studies the great houses for principles only. Work it makes must never name, imitate or
be mistakable for a real house, and generation prompts must describe qualities, never names.

The situation this guards (owner rule: a word rule is about the situation, never a blanket ban):
  * generation prompts      briefs/, *.prompt.txt, shots-*.json, any "prompt" field
  * published copy          the issue/layout JSON, captions, copy files
  * filenames               every file under the project
  * house.yaml              a house's own identity
It never scans maison/references/ (study notes are allowed to name what they study), vendor/,
or the user's own brand declared in house.yaml (``brand_owner: self`` + ``name``).

Unambiguous names block wherever they appear in those surfaces. Words that are also ordinary
English or names (Omega, Tudor, Celine, Kelly, Speedy, Graff, Daytona, ...) block only next to a
product word (watch, bag, ring ...) or after "style of". Living artists block in prompts only. Any other "style of <Name>" in a prompt is a review note
(old masters are fine; a living artist the list misses must be described, not named).

Usage:  python maison/critique/brand_lint.py <project_or_file> [...]   (exit 1 when blocked)
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

HOUSES = [
    "Hermès", "Hermes Paris", "Louis Vuitton", "Patek Philippe", "Rolex", "Acne Studios", "Acne Paper", "Chanel",
    "Christian Dior", "Dior", "Gucci", "Prada", "Cartier", "Bvlgari", "Bulgari", "Tiffany & Co", "Van Cleef",
    "Audemars Piguet", "Vacheron Constantin", "Jaeger-LeCoultre", "Loewe", "Saint Laurent", "Yves Saint Laurent",
    "Balenciaga", "Bottega Veneta", "Fendi", "Givenchy", "Valentino Garavani", "Burberry", "Moncler", "Goyard",
    "Chopard", "Piaget", "Breguet", "Richard Mille", "A. Lange & Söhne", "Lange & Söhne", "Berluti",
    "Brunello Cucinelli", "Loro Piana", "Ermenegildo Zegna", "Dolce & Gabbana", "Dolce&Gabbana", "Versace",
    "Giorgio Armani", "Miu Miu", "Jil Sander", "Maison Margiela", "Martin Margiela", "Chloé", "Lanvin",
    "Boucheron", "Harry Winston", "Montblanc", "TAG Heuer", "Hublot", "Panerai", "Breitling", "Lane & Associates",
    "Le Monde d'Hermès", "La Lanterne", "Hermes",
    # Arabic spellings
    "هيرمس", "هيرميس", "إرميس", "لويس فيتون", "باتيك فيليب", "رولكس", "شانيل", "ديور", "غوتشي", "برادا",
    "كارتييه", "بولغري", "فان كليف",
]
TRADEMARKS = [
    "Birkin", "Kelly bag", "Neverfull", "Speedy bag", "Keepall", "Monogram canvas", "LV monogram", "Damier canvas",
    "Nautilus", "Aquanaut", "Calatrava", "Submariner", "Oyster Perpetual", "Royal Oak", "Cosmograph", "Jumbo bag",
    "2.55 bag", "Lady Dior", "Saddle bag", "Jackie bag", "Trinity ring", "Love bracelet", "Juste un Clou",
    "Alhambra", "Serpenti", "Hermès orange", "orange box", "Tiffany blue", "carriage motif", "Calèche", "H buckle",
]
# Ordinary words or names that are ALSO houses or marks: block only beside a product word / "style of".
AMBIGUOUS = ["Omega", "Tudor", "Celine", "Céline", "Kelly", "Speedy", "Graff", "Daytona", "Oyster", "IWC",
             "Valentino", "Armani", "Kenzo", "Tiffany", "LV", "YSL", "Zegna", "Lange"]
PRODUCT = r"(watch|watches|bag|handbag|tote|purse|wallet|ring|bracelet|necklace|perfume|fragrance|scarf|carré|" \
          r"canvas|monogram|logo|boutique|campaign|ad|advert|collection|shoe|sneaker|jewel\w*|timepiece|chronograph)"
# Living photographers, illustrators and artists commonly named in fashion prompts (prompts only).
LIVING_ARTISTS = [
    "Tim Walker", "Annie Leibovitz", "Paolo Roversi", "Steven Meisel", "Juergen Teller", "Nick Knight",
    "Mario Testino", "Craig McDean", "Inez and Vinoodh", "Inez & Vinoodh", "Mert and Marcus", "Mert & Marcus",
    "Viviane Sassen", "Tyler Mitchell", "Ryan McGinley", "Wolfgang Tillmans", "Cindy Sherman", "David Hockney",
    "Hockney", "Jeff Koons", "Yayoi Kusama", "Kusama", "Takashi Murakami", "Gerhard Richter", "Anish Kapoor",
    "Olafur Eliasson", "Christopher Wool", "Julie Verhoeven", "Jean-Philippe Delhomme", "Marcel Dzama",
    "Gray Malin", "Erik Madigan Heck", "Petra Collins", "Harley Weir", "Rankin", "Ellen von Unwerth",
    "Nadia Lee Cohen", "Charlotte Wales", "Jamie Hawkesworth", "Zoë Ghertner", "Glen Luchford", "Alasdair McLellan",
]
PROMPT_STYLE = re.compile(r"\b(in the style of|style of|à la|inspired by|after the manner of|like a photo by|shot by)\s+"
                          r"([A-Z][\w'’.-]+(?:\s+(?:&|and|de|van|von|la|le)?\s*[A-Z][\w'’.-]+){0,3})")

SKIP_DIRS = {"references", "vendor", "node_modules", ".git", "components", "__pycache__", ".venv"}
TEXT_EXT = {".txt", ".md", ".json", ".yaml", ".yml", ".html", ".csv"}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).casefold()


def _term_re(term: str) -> re.Pattern[str]:
    t = re.escape(_fold(term))
    return re.compile(rf"(?<![\w]){t}(?![\w])" if term.isascii() else t)


_HOUSE_RE = [(t, _term_re(t)) for t in HOUSES]
_TM_RE = [(t, _term_re(t)) for t in TRADEMARKS]
_AMB_RE = [(t, re.compile(rf"(?<![\w]){re.escape(t)}(?![\w])")) for t in AMBIGUOUS]  # case-sensitive
_ART_RE = [(t, _term_re(t)) for t in LIVING_ARTISTS]


def surface_of(path: Path) -> str:
    n = path.name.lower()
    parts = {p.lower() for p in path.parts}
    if n.endswith(".prompt.txt") or n.startswith("shots-") or "briefs" in parts or "prompts" in parts:
        return "prompt"
    if n == "house.yaml":
        return "house"
    return "copy"


def scan_text(text: str, surface: str, allow: Iterable[str] = ()) -> list[dict[str, Any]]:
    allowed = {_fold(a) for a in allow}
    found = []
    for lineno, line in enumerate(text.splitlines(), 1):
        fl = _fold(line)
        hits: list[tuple[str, str]] = []
        for term, rx in _HOUSE_RE:
            if rx.search(fl):
                hits.append((term, "house"))
        for term, rx in _TM_RE:
            if rx.search(fl):
                hits.append((term, "trademark"))
        for term, rx in _AMB_RE:
            for m in rx.finditer(line):
                window = line[max(0, m.start() - 40): m.end() + 40]
                if re.search(PRODUCT, window, re.I) or re.search(r"style of\s+" + re.escape(term), window, re.I):
                    hits.append((term, "house_in_context"))
                    break
        if surface == "prompt":
            for term, rx in _ART_RE:
                if rx.search(fl):
                    hits.append((term, "living_artist"))
            for m in PROMPT_STYLE.finditer(line):
                hits.append((m.group(2), "named_style"))
        for term, kind in hits:
            if _fold(term) in allowed:
                continue
            sev = "review" if kind == "named_style" else "block"
            found.append({"line": lineno, "term": term, "kind": kind, "severity": sev, "context": line.strip()[:160]})
    # one finding per (line, term); a blocking kind wins over a review note for the same term
    uniq: dict[tuple[int, str], dict[str, Any]] = {}
    for f in found:
        k = (f["line"], _fold(f["term"]))
        if k not in uniq or (uniq[k]["severity"] == "review" and f["severity"] == "block"):
            uniq[k] = f
    return list(uniq.values())


def own_brand(project: Path) -> list[str]:
    """Names the user owns (house.yaml: brand_owner self|client + name) are not blocked."""
    import yaml

    names = []
    for hy in project.rglob("house.yaml"):
        try:
            h = yaml.safe_load(hy.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if h.get("brand_owner") in ("self", "client") and h.get("name"):
            names.append(str(h["name"]))
    return names


def lint(paths: Iterable[str | Path]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    scanned = 0
    for root in map(Path, paths):
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()
                                               and not (SKIP_DIRS & {x.lower() for x in p.relative_to(root).parts[:-1]})]
        allow = own_brand(root if root.is_dir() else root.parent)
        for f in files:
            scanned += 1
            for hit in scan_text(f.stem.replace("-", " ").replace("_", " "), "copy", allow):
                findings.append({"file": str(f), "surface": "filename", **hit})
            if f.suffix.lower() not in TEXT_EXT:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            surface = surface_of(f)
            if f.suffix.lower() == ".json" and surface == "copy":
                # a "prompt" field inside JSON is a prompt surface
                try:
                    data = json.loads(text)
                    prompts = list(_prompt_fields(data))
                    for ptxt in prompts:
                        for hit in scan_text(ptxt, "prompt", allow):
                            findings.append({"file": str(f), "surface": "prompt", **hit})
                except ValueError:
                    pass
            for hit in scan_text(text, surface, allow):
                findings.append({"file": str(f), "surface": surface, **hit})
    uniq = {(x["file"], x["surface"], x["line"], _fold(x["term"])): x for x in findings}
    out = list(uniq.values())
    blocks = [x for x in out if x["severity"] == "block"]
    return {"pass": not blocks, "blocked": bool(blocks), "scanned_files": scanned, "findings": blocks,
            "review": [x for x in out if x["severity"] == "review"]}


def _prompt_fields(data: Any) -> Iterable[str]:
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and "prompt" in k.lower():
                yield v
            else:
                yield from _prompt_fields(v)
    elif isinstance(data, list):
        for v in data:
            yield from _prompt_fields(v)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    r = lint(argv)
    for f in r["review"]:
        print(f"REVIEW {f['kind']:<15} {f['term']!r:<24} {f['surface']:<8} {f['file']}:{f['line']}  "
              "(named style: allowed only for artists who are not living)")
    for f in r["findings"]:
        print(f"BLOCK {f['kind']:<16} {f['term']!r:<24} {f['surface']:<8} {f['file']}:{f['line']}  {f['context']}")
    print(f"brand_lint: {'PASS' if r['pass'] else 'BLOCKED'} ({r['scanned_files']} files, {len(r['findings'])} finding(s))")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
