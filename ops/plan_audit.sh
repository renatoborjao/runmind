#!/usr/bin/env bash
# Auditoria de planos + custo de IA (SÓ LEITURA, zero chamada de IA) — ver ops/plan_audit.py.
# Dado de atleta fica na NUVEM: sem arquivo de saída, o relatório vem na TELA e nada é gravado aqui.
# (O relatório diário já é gerado na VM por ops/daily_report.sh — leia com ops/relatorio_vm.sh.)
#   bash ops/plan_audit.sh [--day 2026-11-06]                 # na tela
#   bash ops/plan_audit.sh <saida.md> [--day 2026-11-06]      # grava arquivo (evite: dado de atleta)
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

OUT=""
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then OUT="$1"; shift; fi

scp -q -i "$KEY" "$ROOT/ops/plan_audit.py" "$VM:/tmp/plan_audit.py"

QUOTED=""; [ $# -eq 0 ] || QUOTED=$(printf '%q ' "$@")

if [ -z "$OUT" ]; then
  ssh -i "$KEY" "$VM" "cd ~/runmind/backend && .venv/bin/python /tmp/plan_audit.py $QUOTED 2>&1"
else
  ssh -i "$KEY" "$VM" "cd ~/runmind/backend && .venv/bin/python /tmp/plan_audit.py $QUOTED 2>&1" > "$OUT"
  echo "==> relatório: $OUT ($(wc -l < "$OUT") linhas)"
fi
