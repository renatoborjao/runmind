#!/usr/bin/env bash
# Auditoria SEMANAL do coach — só leitura e SEM IA (zero crédito). Roda o
# coach_audit.py sobre os últimos 7 dias e avisa o admin no Telegram SÓ se houver
# achado (linhas com ⚠️). Sem achado, fica calada.
#
# Vive na VM em ~/ops/ (junto do coach_audit.py) e roda por cron, segunda 12:00 UTC
# (09:00 em Brasília):
#   0 12 * * 1 ~/ops/coach_audit_weekly.sh >> ~/ops/coach_audit_weekly.log 2>&1
#
#   ~/ops/coach_audit_weekly.sh             # envia se houver achado
#   DRY_RUN=1 ~/ops/coach_audit_weekly.sh   # só mostra o que enviaria
set -uo pipefail

export LC_ALL=C.UTF-8

BACKEND="$HOME/runmind/backend"
OPS="$HOME/ops"
OUT="$OPS/last_coach_audit.md"

cd "$BACKEND" || exit 1

# GOOGLE_API_KEY=DISABLED: qualquer chamada de IA acidental falha de graça
GOOGLE_API_KEY=DISABLED timeout 600 .venv/bin/python "$OPS/coach_audit.py" --days 7 2>/dev/null \
  | grep -v -E '^\[token|DeprecationWarning' > "$OUT" || true

N=$(grep -c '⚠️' "$OUT" || true)

if [ "${N:-0}" -eq 0 ]; then
  echo "$(date -u '+%F %T') auditoria semanal: sem achados"
  exit 0
fi

MSG="🔍 Auditoria semanal do coach — ${N} achado(s)"$'\n\n'"$(grep '⚠️' "$OUT" | cut -c1-230 | head -14)"$'\n\n'"Relatório completo na VM: ~/ops/last_coach_audit.md (ou: bash ops/coach_audit.sh relatorio.md --days 7)"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "$MSG"
  exit 0
fi

TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" .env | cut -d= -f2- | tr -d "\r\n")
ADMIN=$(grep -E "^ADMIN_TELEGRAM_ID=" .env | cut -d= -f2- | tr -d "\r\n")

curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  -d chat_id="${ADMIN}" --data-urlencode text="${MSG}" >/dev/null

echo "$(date -u '+%F %T') auditoria semanal: ${N} achado(s) enviados ao admin"
