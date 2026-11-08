#!/usr/bin/env bash
# Auditoria de planos + custo de IA (SÓ LEITURA, zero chamada de IA) — ver
# ops/plan_audit.py. Traz o relatório pro arquivo local.
#   bash ops/plan_audit.sh <saida.md> [--day 2026-11-06]
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

OUT="${1:?uso: plan_audit.sh <saida.md> [--day AAAA-MM-DD]}"; shift

scp -q -i "$KEY" "$ROOT/ops/plan_audit.py" "$VM:/tmp/plan_audit.py"

QUOTED=""; [ $# -eq 0 ] || QUOTED=$(printf '%q ' "$@")
ssh -i "$KEY" "$VM" "cd ~/runmind/backend && .venv/bin/python /tmp/plan_audit.py $QUOTED 2>&1" > "$OUT"

echo "==> relatório: $OUT ($(wc -l < "$OUT") linhas)"
