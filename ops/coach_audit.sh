#!/usr/bin/env bash
# Auditoria do coach (só leitura) sobre o que ele fez de verdade nos últimos N
# dias — ver ops/coach_audit.py. Traz o relatório pro arquivo local.
#   bash ops/coach_audit.sh <saida.md> [--days 7]
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

OUT="${1:?uso: coach_audit.sh <saida.md> [--days N]}"; shift

scp -q -i "$KEY" "$ROOT/ops/coach_audit.py" "$VM:/tmp/coach_audit.py"

QUOTED=$(printf '%q ' "$@")
ssh -i "$KEY" "$VM" "cd ~/runmind/backend && timeout 600 .venv/bin/python /tmp/coach_audit.py $QUOTED 2>&1 | grep -v -E '^\[token|DeprecationWarning'" > "$OUT"

echo "==> auditoria: $OUT ($(grep -c '⚠️' "$OUT" || true) achados)"
