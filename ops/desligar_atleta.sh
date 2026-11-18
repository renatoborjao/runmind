#!/usr/bin/env bash
# Desliga UM atleta da base (ver ops/desligar_atleta.py). Roda na VM; nada fica neste PC.
#   bash ops/desligar_atleta.sh fulano                 # dry-run: mostra o que faria
#   bash ops/desligar_atleta.sh fulano --apply         # bloqueia + backup + tira os arquivos dele do storage
#   bash ops/desligar_atleta.sh fulano --only-block --apply   # só bloqueia (arquivos já guardados)
#   bash ops/desligar_atleta.sh fulano --unblock       # tira o bloqueio (o convite no app já faz isso sozinho)
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PROFILE="${1:?uso: desligar_atleta.sh <atleta> [--apply] [--only-block] [--unblock] [--motivo "..."]}"
shift

[[ "$PROFILE" =~ ^[a-z0-9_]+$ ]] || { echo "atleta inválido: $PROFILE" >&2; exit 1; }

scp -q -i "$KEY" "$ROOT/ops/desligar_atleta.py" "$VM:/tmp/desligar_atleta.py"

QUOTED=""; [ $# -eq 0 ] || QUOTED=$(printf '%q ' "$@")

ssh -i "$KEY" "$VM" "cd ~/runmind/backend && .venv/bin/python /tmp/desligar_atleta.py --profile $PROFILE $QUOTED; rm -f /tmp/desligar_atleta.py"
