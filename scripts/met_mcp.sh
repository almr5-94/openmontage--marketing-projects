#!/usr/bin/env bash
# Start the audited Met Museum MCP server (cyanheads, pinned 0.10.1) on Node 24, which it needs.
# Node 24 lives in ~/.local/node24 and is used only here; the system Node stays as it is.
set -euo pipefail
NODE24_DIR="${NODE24_DIR:-$HOME/.local/node24}"
if [ ! -x "$NODE24_DIR/bin/node" ]; then
  echo "Node 24 not found in $NODE24_DIR (see START_HERE.md)" >&2
  exit 1
fi
export PATH="$NODE24_DIR/bin:$PATH"
exec npx -y @cyanheads/met-museum-mcp-server@0.10.1
