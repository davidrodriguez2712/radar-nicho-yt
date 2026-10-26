#!/bin/sh
# Respaldo diario cifrado + poda. Lo invoca launchd; no imprime secretos (backup_mac.py no los maneja en argv).
set -eu
cd "$(dirname "$0")/../.."
LOG="$HOME/Library/Application Support/NicheRadar/backup.log"
{
  echo "== $(date -u +%Y-%m-%dT%H:%M:%SZ) backup"
  /usr/bin/env uv run python scripts/backup_mac.py backup
  echo "== prune"
  /usr/bin/env uv run python scripts/backup_mac.py prune --apply
} >>"$LOG" 2>&1
