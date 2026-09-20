"""Inventory and validate the September campaign reel folders before a build run.

The reel folders and their prompts live on the operator's machine, not in this
repo. A build run that starts by guessing which folders exist, how many prompts
each holds, or whether a prompt still fits the provider limit wastes a full
generation pass to find out. This script turns that guesswork into a verified
manifest first.

It walks one or more roots, treats every directory that holds prompt files as a
reel folder, extracts the prompts, and checks each one against the provider
character limit. Output is a human summary plus an optional JSON manifest the
build run can read instead of re-walking the disk.

Usage:
    python scripts/september_campaign_inventory.py --root ~/september-campaign
    python scripts/september_campaign_inventory.py --root . --json /tmp/reels.json

Exit codes:
    0  every reel passed
    1  at least one reel failed validation
    2  no reel folders found under any root
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

# Provider prompt ceiling the campaign prompts were validated against.
DEFAULT_MAX_CHARS = 5000

# Fraction of the ceiling above which a prompt is reported as "tight" — it
# passes, but an edit during the run could push it over.
NEAR_LIMIT_RATIO = 0.9

PROMPT_SUFFIXES = (".txt", ".md", ".json", ".yaml", ".yml")
REEL_DIR_PATTERN = re.compile(r"(^|[^a-z])reel", re.IGNORECASE)
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "renders", "assets"}


def is_prompt_file(path: Path) -> bool:
    """A prompt file is named for prompts, or is a bare .txt/.md inside a reel dir."""
    if path.suffix.lower() not in PROMPT_SUFFIXES:
        return False
    if "prompt" in path.stem.lower():
        return True
    return path.suffix.lower() in (".txt", ".md") and REEL_DIR_PATTERN.search(path.parent.name) is not None


def extract_prompts(path: Path) -> list[tuple[str, str]]:
    """Return (label, text) pairs from one prompt file.

    Plain text and markdown are one prompt each. JSON is walked for any string
    under a key containing "prompt", plus lists of strings under such a key,
    so both {"prompt": "..."} and {"prompts": ["...", "..."]} are handled.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [(f"{path.name} (unreadable: {exc.__class__.__name__})", "")]

    if path.suffix.lower() != ".json":
        return [(path.name, raw.strip())]

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Malformed JSON still carries text worth measuring; flag it by label.
        return [(f"{path.name} (invalid JSON)", raw.strip())]

    found: list[tuple[str, str]] = []

    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{trail}.{key}" if trail else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]")
        elif isinstance(node, str) and "prompt" in trail.lower():
            found.append((f"{path.name}:{trail}", node.strip()))

    walk(data, "")
    return found or [(path.name, raw.strip())]


def iter_candidate_dirs(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if not path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def scan_root(root: Path, max_chars: int, expect_per_reel: int | None) -> list[dict[str, Any]]:
    reels: list[dict[str, Any]] = []
    for directory in iter_candidate_dirs(root):
        prompt_files = sorted(p for p in directory.iterdir() if p.is_file() and is_prompt_file(p))
        if not prompt_files:
            continue

        prompts: list[dict[str, Any]] = []
        for prompt_file in prompt_files:
            for label, text in extract_prompts(prompt_file):
                chars = len(text)
                if chars == 0:
                    status = "empty"
                elif chars > max_chars:
                    status = "over_limit"
                elif chars >= int(max_chars * NEAR_LIMIT_RATIO):
                    status = "tight"
                else:
                    status = "ok"
                prompts.append(
                    {
                        "label": label,
                        "file": str(prompt_file),
                        "chars": chars,
                        "status": status,
                    }
                )

        problems = [p for p in prompts if p["status"] in ("empty", "over_limit")]
        count_mismatch = expect_per_reel is not None and len(prompts) != expect_per_reel
        reels.append(
            {
                "reel": directory.name,
                "path": str(directory),
                "prompt_count": len(prompts),
                "prompts": prompts,
                "count_mismatch": count_mismatch,
                "status": "fail" if (problems or count_mismatch) else "pass",
            }
        )
    return reels


def print_summary(reels: list[dict[str, Any]], max_chars: int, expect_per_reel: int | None) -> None:
    print(f"\nSEPTEMBER CAMPAIGN — REEL INVENTORY  (limit {max_chars} chars)\n")
    name_width = max((len(r["reel"]) for r in reels), default=4)

    for reel in reels:
        mark = "PASS" if reel["status"] == "pass" else "FAIL"
        print(f"  [{mark}] {reel['reel']:<{name_width}}  {reel['prompt_count']} prompt(s)   {reel['path']}")
        for prompt in reel["prompts"]:
            if prompt["status"] != "ok":
                print(f"           {prompt['status']:<10} {prompt['chars']:>5} chars  {prompt['label']}")
        if reel["count_mismatch"]:
            print(f"           count      expected {expect_per_reel}, found {reel['prompt_count']}")

    total_prompts = sum(r["prompt_count"] for r in reels)
    failed = [r for r in reels if r["status"] == "fail"]
    tight = sum(1 for r in reels for p in r["prompts"] if p["status"] == "tight")

    print(f"\n  {len(reels)} reel folder(s), {total_prompts} prompt(s)")
    if tight:
        print(f"  {tight} prompt(s) within {int(NEAR_LIMIT_RATIO * 100)}% of the limit — safe now, fragile if edited")
    print(f"  {len(failed)} reel(s) need attention\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="Directory to scan for reel folders. Repeatable. Default: current directory.",
    )
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS, help="Provider prompt limit.")
    parser.add_argument(
        "--expect-prompts-per-reel",
        type=int,
        default=None,
        help="Flag any reel that does not hold exactly this many prompts (the campaign ran 2).",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="Write the manifest to this path.")
    args = parser.parse_args(argv)

    roots = [Path(r).expanduser().resolve() for r in (args.root or ["."])]
    reels: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            print(f"  skipped (not a directory): {root}", file=sys.stderr)
            continue
        reels.extend(scan_root(root, args.max_chars, args.expect_prompts_per_reel))

    if not reels:
        print(f"No reel folders found under: {', '.join(str(r) for r in roots)}", file=sys.stderr)
        print("Point --root at the directory holding the campaign folders.", file=sys.stderr)
        return 2

    print_summary(reels, args.max_chars, args.expect_prompts_per_reel)

    if args.json_out:
        manifest = {
            "roots": [str(r) for r in roots],
            "max_chars": args.max_chars,
            "expected_prompts_per_reel": args.expect_prompts_per_reel,
            "reels": reels,
        }
        out_path = Path(args.json_out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  manifest -> {out_path}\n")

    return 1 if any(r["status"] == "fail" for r in reels) else 0


if __name__ == "__main__":
    raise SystemExit(main())
