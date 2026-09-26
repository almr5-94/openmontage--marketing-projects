#!/usr/bin/env bash
# Install (or refresh) the KLI user timers on abood. Run as abood; needs linger once: sudo loginctl enable-linger abood
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.config/systemd/user
cp "$HERE"/kli-*.service "$HERE"/kli-*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now kli-produce.timer kli-produce-retry.timer kli-publish.timer kli-metrics.timer
systemctl --user list-timers --all | grep kli
