#!/bin/bash
# Relatório DIÁRIO do coach — roda na VM, SÓ LEITURA, ZERO IA (GOOGLE_API_KEY=DISABLED: qualquer
# chamada de IA acidental falha de graça). Dado de atleta fica na NUVEM: o relatório é gravado na
# própria VM (~/ops/reports/, só o dono lê) e lido de lá, na tela, por ops/relatorio_vm.sh —
# nunca vira arquivo no computador nem entra no repositório.
#
# Dois relatórios por dia:
#   planos_AAAA-MM-DD.md   plano × feito de cada atleta, semana a semana, e o gasto de IA por rótulo
#                          (ops/plan_audit.py)
#   carga_AAAA-MM-DD.txt   a leitura de carga de cada atleta: ACWR, retorno ao platô, salto de
#                          sessão, ordem alerta × carga (ops/coach_lab.py --only load)
# Guarda 30 dias; planos_latest.md / carga_latest.txt apontam o mais novo.
#
# Vive em ~/ops/ na VM e roda por cron às 10:00 UTC (07:00 em Brasília, antes da auditoria de
# sanidade das 08:30):
#   0 10 * * * ~/ops/daily_report.sh >> ~/ops/daily_report.log 2>&1
set -uo pipefail

export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8

BACKEND="$HOME/runmind/backend"
OPS="$HOME/ops"
OUT="$OPS/reports"
DAY="$(date +%F)"
YESTERDAY="$(date -d yesterday +%F)"

mkdir -p "$OUT"
chmod 700 "$OUT"
umask 077

cd "$BACKEND" || exit 1

GOOGLE_API_KEY=DISABLED timeout 600 .venv/bin/python "$OPS/plan_audit.py" --day "$YESTERDAY" \
  > "$OUT/planos_$DAY.md" 2>/dev/null

GOOGLE_API_KEY=DISABLED timeout 900 .venv/bin/python "$OPS/coach_lab.py" --only load 2>/dev/null \
  | grep -v -E '^\[token|AFC|DeprecationWarning' > "$OUT/carga_$DAY.txt"

# só promove a "latest" se o relatório do dia tem conteúdo (não troca um bom por um vazio)
[ -s "$OUT/planos_$DAY.md" ] && cp "$OUT/planos_$DAY.md" "$OUT/planos_latest.md"
[ -s "$OUT/carga_$DAY.txt" ] && cp "$OUT/carga_$DAY.txt" "$OUT/carga_latest.txt"

find "$OUT" -name 'planos_20*.md' -mtime +30 -delete
find "$OUT" -name 'carga_20*.txt' -mtime +30 -delete

echo "$(date -u '+%F %T') relatório diário: planos $(wc -l < "$OUT/planos_$DAY.md") linhas, carga $(wc -l < "$OUT/carga_$DAY.txt") linhas"
