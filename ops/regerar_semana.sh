#!/usr/bin/env bash
# Refaz a semana de UM atleta com o código atual do coach (ver ops/regerar_semana.py). Roda na VM;
# a saída vem na TELA — nada é gravado neste computador (dado de atleta fica na nuvem).
#   bash ops/regerar_semana.sh renato2            # dry-run: mostra o plano guardado, sem IA, sem enviar
#   bash ops/regerar_semana.sh renato2 --apply    # backup → gera (IA paga, ~R$0,40) → salva → relógio → envia
#   opções extras: --week AAAA-MM-DD   --no-send
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PROFILE="${1:?uso: regerar_semana.sh <atleta> [--apply] [--week AAAA-MM-DD] [--no-send]}"
shift

[[ "$PROFILE" =~ ^[a-z0-9_]+$ ]] || { echo "atleta inválido: $PROFILE" >&2; exit 1; }

scp -q -i "$KEY" "$ROOT/ops/regerar_semana.py" "$VM:/tmp/regerar_semana.py"

QUOTED=""; [ $# -eq 0 ] || QUOTED=$(printf '%q ' "$@")

ssh -i "$KEY" "$VM" "cd ~/runmind/backend && timeout 900 .venv/bin/python /tmp/regerar_semana.py --profile $PROFILE $QUOTED 2>&1 | grep -v -E '^\[token|AFC|DeprecationWarning'"
