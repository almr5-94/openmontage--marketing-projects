#!/usr/bin/env bash
# Install the three hand-drawn family skills from this repo into the running
# machine's Claude skill folder. The repo copy is the source of truth; the
# installed SKILL.md must stay byte-identical to it.
#
#   bash skills/install_handdrawn_skills.sh          # install/refresh
#   bash skills/install_handdrawn_skills.sh --check  # verify, change nothing
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
check=0
[ "${1:-}" = "--check" ] && check=1
rc=0
for fam in paperfolk incise biotext; do
  src="$repo/skills/creative/handdrawn-$fam.md"
  out="$dest/handdrawn-$fam/SKILL.md"
  if [ ! -f "$src" ]; then echo "MISSING SOURCE $src"; rc=1; continue; fi
  if [ "$check" = 1 ]; then
    if [ -f "$out" ] && cmp -s "$src" "$out"; then
      echo "ok        handdrawn-$fam -> $out"
    else
      echo "DRIFTED   handdrawn-$fam -> ${out} (run without --check)"; rc=1
    fi
  else
    mkdir -p "$(dirname "$out")"
    cp "$src" "$out"
    echo "installed handdrawn-$fam -> $out"
  fi
done
exit $rc
