#!/usr/bin/env bash
# Banco de cenários do coach — roda o código LOCAL (candidato) contra os dados
# REAIS da VM, em memória, sem gravar plano nem mandar mensagem. É a validação
# obrigatória de toda mudança no coach ANTES do deploy (ver docs/coach_rollback.md).
#   bash ops/coach_lab.sh <saida.txt> [args do lab]        # candidato: tudo de backend/app que difere do HEAD
#   bash ops/coach_lab.sh --no-overlay <saida.txt> [args]  # o que está NO AR (o "antes")
# custo: --context-only é grátis; sem ele é PAGO e exige --profiles a,b (ou --todos)
# args do lab: --profiles renato2,fernanda  --only dossier,chat,analysis,conduct,review,plan
# catálogo do cérebro: --braineval 0 --repeats 1 (pago); com --context-only monta os contextos sem IA
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

OVERLAY=1
if [ "${1:-}" = "--no-overlay" ]; then OVERLAY=0; shift; fi

OUT="${1:?uso: coach_lab.sh [--no-overlay] <saida.txt> [args]}"; shift

cd "$ROOT/backend"

REMOTE_ARGS=("$@")

# TRAVA DE CUSTO: sem --context-only o lab chama a IA de verdade (o plano no Pro, ~R$0,33 por
# atleta). Pago só com os atletas escolhidos (--profiles a,b); todos de uma vez só com --todos.
# (30 dias até 16/11: R$12,41 de lab contra R$14,61 dos planos reais.)
ARGS=" $* "
if [[ "$ARGS" != *" --context-only "* && "$ARGS" != *" --profiles "* && "$ARGS" != *" --braineval "* ]]; then
  if [[ "$ARGS" == *" --todos "* ]]; then
    REMOTE_ARGS=()
    for a in "$@"; do [ "$a" = "--todos" ] || REMOTE_ARGS+=("$a"); done
    echo "==> AVISO: lab PAGO com TODOS os atletas (--todos)"
  else
    echo "ABORTADO: lab sem --context-only chama a IA paga. Use --context-only (grátis)," >&2
    echo "          --profiles a,b (pago, só esses) ou --todos (pago, todos)." >&2
    exit 1
  fi
fi
[[ "$ARGS" == *" --context-only "* ]] || echo "==> lab PAGO (IA de verdade; gasto marcado como \"lab\" no medidor)"

if [ "$OVERLAY" = 1 ]; then
  mapfile -t FILES < <(
    { git diff --name-only --relative HEAD -- app; git ls-files --others --exclude-standard app; } \
      | sort -u | while read -r f; do [ -f "$f" ] && echo "$f"; done
  )
  [ ${#FILES[@]} -gt 0 ] || { echo "nada difere do HEAD — use --no-overlay"; exit 1; }
  echo "==> candidato (${#FILES[@]} arquivos):"; printf '    %s\n' "${FILES[@]}"
  tar -czf /tmp/coach_next.tgz "${FILES[@]}"
  scp -q -i "$KEY" /tmp/coach_next.tgz "$VM:/tmp/coach_next.tgz"
  ssh -i "$KEY" "$VM" 'rm -rf /tmp/coach_next && mkdir -p /tmp/coach_next && tar -xzf /tmp/coach_next.tgz -C /tmp/coach_next'
  REMOTE_ARGS=(--overlay /tmp/coach_next "${REMOTE_ARGS[@]}")
fi

scp -q -i "$KEY" "$ROOT/ops/coach_lab.py" "$VM:/tmp/coach_lab.py"

echo "==> rodando na VM (pode levar alguns minutos)"
QUOTED=""; [ ${#REMOTE_ARGS[@]} -eq 0 ] || QUOTED=$(printf '%q ' "${REMOTE_ARGS[@]}")
ssh -i "$KEY" "$VM" "cd ~/runmind/backend && timeout 1800 .venv/bin/python /tmp/coach_lab.py $QUOTED 2>&1 | grep -v -E '^\[token|AFC|DeprecationWarning' " > "$OUT"

echo "==> relatório: $OUT ($(wc -l < "$OUT") linhas)"
