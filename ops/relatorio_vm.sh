#!/usr/bin/env bash
# Lê o relatório diário da VM NA TELA — não grava arquivo no computador (dado de atleta fica na
# nuvem). O relatório é gerado todo dia na VM por ops/daily_report.sh.
#   bash ops/relatorio_vm.sh planos            # o mais novo
#   bash ops/relatorio_vm.sh carga 2026-11-09  # de um dia específico
#   bash ops/relatorio_vm.sh armazenamento     # vigia do plano gratuito (disco, Object Storage)
#   bash ops/relatorio_vm.sh lista             # os dias disponíveis
#   bash ops/relatorio_vm.sh geracao           # confere AGORA o plano de domingo de cada atleta
#   bash ops/relatorio_vm.sh geracao texto     # idem, com o texto que cada atleta recebeu
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"

KIND="${1:?uso: relatorio_vm.sh planos|carga|armazenamento [AAAA-MM-DD] | lista | geracao [texto]}"
DAY="${2:-latest}"

case "$KIND" in
  planos) FILE="planos_$DAY.md" ;;
  carga) FILE="carga_$DAY.txt" ;;
  armazenamento) FILE="armazenamento_$DAY.txt" ;;
  lista) ssh -i "$KEY" "$VM" "ls -1 ~/ops/reports | sort"; exit 0 ;;
  geracao)
    # roda a conferência na VM agora (só leitura, ZERO IA): nada é gravado aqui nem lá
    FLAG=""
    [ "${2:-}" = texto ] && FLAG="--texto"
    ssh -i "$KEY" "$VM" "cd ~/runmind/backend && GOOGLE_API_KEY=DISABLED PYTHONIOENCODING=utf-8 .venv/bin/python -m app.application.monitoring.plan_generation_monitor $FLAG 2>/dev/null" \
      | grep -v -E '^\[token|AFC|DeprecationWarning' || true
    exit 0 ;;
  *) echo "tipo inválido: $KIND (use planos, carga, armazenamento, lista ou geracao)" >&2; exit 1 ;;
esac

# o nome vem de lista fechada acima; DAY só aceita data ou "latest"
[[ "$DAY" =~ ^(latest|[0-9]{4}-[0-9]{2}-[0-9]{2})$ ]] || { echo "data inválida: $DAY" >&2; exit 1; }

ssh -i "$KEY" "$VM" "cat ~/ops/reports/$FILE"
