#!/bin/bash
# Relatório DIÁRIO do coach — roda na VM, SÓ LEITURA, ZERO IA (GOOGLE_API_KEY=DISABLED: qualquer
# chamada de IA acidental falha de graça). Dado de atleta fica na NUVEM: o relatório é gravado na
# própria VM (~/ops/reports/, só o dono lê) e lido de lá, na tela, por ops/relatorio_vm.sh —
# nunca vira arquivo no computador nem entra no repositório.
#
# Três relatórios por dia:
#   planos_AAAA-MM-DD.md         plano × feito de cada atleta, semana a semana, e o gasto de IA por
#                                rótulo (ops/plan_audit.py)
#   carga_AAAA-MM-DD.txt         a leitura de carga de cada atleta: ACWR, retorno ao platô, salto de
#                                sessão, ordem alerta × carga (ops/coach_lab.py --only load)
#   armazenamento_AAAA-MM-DD.txt VIGIA DO PLANO GRATUITO: disco, Object Storage, crescimento e os
#                                maiores consumidores; avisa no Telegram do dono ANTES de estourar
# Guarda 30 dias; *_latest apontam o mais novo.
#
# Vive em ~/ops/ na VM e roda por cron às 10:00 UTC (07:00 em Brasília, antes da auditoria de
# sanidade das 08:30):
#   0 10 * * * ~/ops/daily_report.sh >> ~/ops/daily_report.log 2>&1
#
# Variáveis (só pra teste): STORAGE_WARN_PCT (70), STORAGE_CRIT_PCT (85), STORAGE_ALERT_DRY=1 (mostra o
# aviso em vez de enviar).
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

# ---------------------------------------------------------------------------------------------
# 1) planos × feito + custo de IA   2) carga
# ---------------------------------------------------------------------------------------------
GOOGLE_API_KEY=DISABLED timeout 600 .venv/bin/python "$OPS/plan_audit.py" --day "$YESTERDAY" \
  > "$OUT/planos_$DAY.md" 2>/dev/null

GOOGLE_API_KEY=DISABLED timeout 900 .venv/bin/python "$OPS/coach_lab.py" --only load 2>/dev/null \
  | grep -v -E '^\[token|AFC|DeprecationWarning' > "$OUT/carga_$DAY.txt"

# só promove a "latest" se o relatório do dia tem conteúdo (não troca um bom por um vazio)
[ -s "$OUT/planos_$DAY.md" ] && cp "$OUT/planos_$DAY.md" "$OUT/planos_latest.md"
[ -s "$OUT/carga_$DAY.txt" ] && cp "$OUT/carga_$DAY.txt" "$OUT/carga_latest.txt"

# ---------------------------------------------------------------------------------------------
# 3) ARMAZENAMENTO — Oracle Always Free: 200 GB de volumes de bloco (boot incluso) e 20 GiB de Object
# Storage. Passar disso vira cobrança: medimos todo dia e avisamos ANTES (70% aviso, 85% crítico).
# ---------------------------------------------------------------------------------------------
WARN_PCT="${STORAGE_WARN_PCT:-70}"
CRIT_PCT="${STORAGE_CRIT_PCT:-85}"
POOL_GB=200
OBJ_GIB=20
STORE="$OUT/armazenamento_$DAY.txt"
HIST="$OUT/armazenamento_historico.tsv"

used=$(df -B1 --output=used / | tail -1 | tr -d ' ')
size=$(df -B1 --output=size / | tail -1 | tr -d ' ')
pct=$(( used * 100 / size ))
boot_gb=$(( (size + 500000000) / 1000000000 ))
pool_pct=$(( boot_gb * 100 / POOL_GB ))

backups_b=$(du -sb "$HOME/runmind-backups" 2>/dev/null | cut -f1)
backups_b=${backups_b:-0}

# Object Storage: não dá pra listar o balde (o link do script é só de ENVIO). Estimativa em LIMITE
# SUPERIOR: nº de envios × tamanho do backup mais novo (os antigos eram menores).
uploads=$(grep -c '^enviado' "$OPS/backup_offsite.log" 2>/dev/null || true)
uploads=${uploads:-0}
newest_zip=$(ls -t "$HOME"/runmind-backups/*.zip 2>/dev/null | head -1)
zip_b=0
[ -n "$newest_zip" ] && zip_b=$(stat -c %s "$newest_zip")
obj_b=$(( uploads * zip_b ))
obj_pct=$(( obj_b * 100 / (OBJ_GIB * 1073741824) ))

# histórico diário (1 linha por dia; reexecutar no mesmo dia substitui)
touch "$HIST"
grep -v "^$DAY" "$HIST" > "$HIST.tmp" 2>/dev/null || true
mv "$HIST.tmp" "$HIST"
printf '%s\t%s\t%s\n' "$DAY" "$used" "$backups_b" >> "$HIST"

# crescimento médio por dia (bytes) nos últimos 8 registros; vazio sem 2 dias de histórico
growth=$(tail -8 "$HIST" | awk -F'\t' '
  NR==1 { d0=$1; u0=$2 }
  { d1=$1; u1=$2; n=NR }
  END {
    if (n < 2) { exit }
    c="date -d " d0 " +%s"; c | getline t0; close(c)
    c="date -d " d1 " +%s"; c | getline t1; close(c)
    days=(t1-t0)/86400
    if (days > 0) printf "%d", (u1-u0)/days
  }')

warn_bytes=$(( size * WARN_PCT / 100 ))
days_to_warn=""
if [ -n "$growth" ] && [ "$growth" -gt 0 ]; then
  days_to_warn=$(( (warn_bytes - used) / growth ))
fi

mb() { echo $(( $1 / 1048576 )); }

alerts=()
level=0
if [ "$pct" -ge "$CRIT_PCT" ]; then
  alerts+=("CRÍTICO: disco da VM em ${pct}% (limite crítico ${CRIT_PCT}%)"); level=2
elif [ "$pct" -ge "$WARN_PCT" ]; then
  alerts+=("AVISO: disco da VM em ${pct}% (aviso em ${WARN_PCT}%)"); level=1
fi
if [ "$obj_pct" -ge "$WARN_PCT" ]; then
  alerts+=("AVISO: Object Storage estimado em ${obj_pct}% dos ${OBJ_GIB} GiB gratuitos"); [ "$level" -lt 1 ] && level=1
fi
if [ -n "$days_to_warn" ] && [ "$days_to_warn" -lt 30 ]; then
  alerts+=("AVISO: no ritmo atual (+$(mb "$growth") MB/dia) o disco chega a ${WARN_PCT}% em ~${days_to_warn} dias"); [ "$level" -lt 1 ] && level=1
fi
if [ "$backups_b" -gt 1610612736 ]; then
  alerts+=("AVISO: pasta de backups da VM com $(mb "$backups_b") MB (a retenção deveria manter ~50 MB)"); [ "$level" -lt 1 ] && level=1
fi

{
  echo "ARMAZENAMENTO DA VM — $DAY (plano gratuito da Oracle)"
  echo
  echo "disco raiz:  $(mb "$used") MB usados de $(mb "$size") MB (${pct}%) · aviso em ${WARN_PCT}%, crítico em ${CRIT_PCT}%"
  echo "pool de bloco gratuito: boot ≈ ${boot_gb} GB de ${POOL_GB} GB (${pool_pct}%) — outros volumes não aparecem aqui; conferir no console da Oracle antes de criar qualquer um"
  echo "Object Storage (estimativa, LIMITE SUPERIOR): ${uploads} envios × $(mb "$zip_b") MB ≈ $(mb "$obj_b") MB de $(( OBJ_GIB * 1024 )) MB (${obj_pct}%)"
  if [ -n "$growth" ]; then
    echo "crescimento: $(( growth / 1024 )) KB/dia (média dos últimos dias com registro)${days_to_warn:+ · ${WARN_PCT}% do disco em ~${days_to_warn} dias}"
  else
    echo "crescimento: sem histórico ainda (precisa de 2 dias de registro)"
  fi
  echo
  echo "--- maiores consumidores (MB; o du conta uma vez só os arquivos compartilhados por hardlink entre o cache da uv e o venv do app) ---"
  du -sm "$HOME"/.cache "$HOME"/.local "$HOME"/runmind "$HOME"/runmind-backups "$HOME"/rollback_points \
         "$HOME"/deploy_backups "$HOME"/legacy-pc "$HOME"/notas-claude "$OUT" /var/log 2>/dev/null | sort -rn
  echo
  echo "--- retenção ---"
  echo "backups do app: $(ls "$HOME"/runmind-backups 2>/dev/null | wc -l) arquivos, $(mb "$backups_b") MB (mantém os últimos 28)"
  echo "deploy_backups: $(ls "$HOME"/deploy_backups 2>/dev/null | wc -l) pastas · rollback_points: $(ls "$HOME"/rollback_points 2>/dev/null | wc -l) pastas"
  echo "log do sistema (journald): $(du -sm /var/log/journal 2>/dev/null | cut -f1) MB"
  echo
  echo "--- alertas ---"
  if [ "${#alerts[@]}" -eq 0 ]; then
    echo "nenhum: tudo dentro do plano gratuito"
  else
    printf '%s\n' "${alerts[@]}"
  fi
} > "$STORE"

[ -s "$STORE" ] && cp "$STORE" "$OUT/armazenamento_latest.txt"

# aviso no Telegram do dono (mesmo caminho do alerta de serviço caído) — só quando há alerta E é
# novo (nível piorou) ou faz mais de 7 dias que avisou; nunca todo dia
notify() {
  if [ "${STORAGE_ALERT_DRY:-0}" = "1" ]; then
    echo "[DRY] $1"
    return 0
  fi
  local token admin
  token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$BACKEND/.env" | cut -d= -f2- | tr -d '\r\n')
  admin=$(grep -E '^ADMIN_TELEGRAM_ID=' "$BACKEND/.env" | cut -d= -f2- | tr -d '\r\n')
  [ -n "$token" ] && [ -n "$admin" ] || return 0
  curl -s "https://api.telegram.org/bot${token}/sendMessage" \
    -d chat_id="$admin" --data-urlencode text="$1" >/dev/null
}

STATE="$OUT/.armazenamento_alerta"
if [ "$level" -gt 0 ]; then
  last_day=""; last_level=0
  [ -f "$STATE" ] && read -r last_day last_level < "$STATE"
  age_days=999
  [ -n "$last_day" ] && age_days=$(( ( $(date +%s) - $(date -d "$last_day" +%s) ) / 86400 ))
  if [ "$level" -gt "${last_level:-0}" ] || [ "$age_days" -ge 7 ]; then
    notify "⚠️ RunMind — armazenamento da VM (plano gratuito da Oracle)
$(printf '%s\n' "${alerts[@]}")
Relatório completo: ssh na VM, ~/ops/reports/armazenamento_latest.txt"
    [ "${STORAGE_ALERT_DRY:-0}" = "1" ] || echo "$DAY $level" > "$STATE"
  fi
else
  rm -f "$STATE"
fi

# retenção dos próprios relatórios: 30 dias
find "$OUT" -name 'planos_20*.md' -mtime +30 -delete
find "$OUT" -name 'carga_20*.txt' -mtime +30 -delete
find "$OUT" -name 'armazenamento_20*.txt' -mtime +30 -delete

echo "$(date -u '+%F %T') relatório diário: planos $(wc -l < "$OUT/planos_$DAY.md") linhas, carga $(wc -l < "$OUT/carga_$DAY.txt") linhas, disco ${pct}%, alertas ${#alerts[@]}"
