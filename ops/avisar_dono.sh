#!/usr/bin/env bash
# Manda um texto pro Telegram do DONO (ADMIN_TELEGRAM_ID da VM) — e só pra ele. O texto vem pela
# entrada padrão, passa direto pra VM por ssh e é enviado de lá; nada é gravado no computador.
# Textos longos são quebrados abaixo do teto do Telegram (split_message do monitor de domingo).
#   echo "oi" | bash ops/avisar_dono.sh
#   bash ops/avisar_dono.sh < "$SCRATCH/revisao.txt"
#   DRY_RUN=1 bash ops/avisar_dono.sh < texto   # só diz quantas mensagens sairiam
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"

DRY="${DRY_RUN:-0}"

ssh -i "$KEY" "$VM" "cd ~/runmind/backend && GOOGLE_API_KEY=DISABLED PYTHONIOENCODING=utf-8 DRY=$DRY .venv/bin/python -c '
import asyncio, os, sys
from app.application.monitoring.coach_sanity_audit import _send
from app.application.monitoring.plan_generation_monitor import split_message
text = sys.stdin.read().strip()
if not text:
    sys.exit(\"texto vazio: nada enviado\")
chunks = split_message(text)
if os.environ.get(\"DRY\") == \"1\":
    print(f\"(dry-run) {len(chunks)} mensagem(ns), maior com {max(map(len, chunks))} caracteres\")
    sys.exit(0)
sent = sum(1 for c in chunks if asyncio.run(_send(c)))
print(f\"enviadas {sent} de {len(chunks)} mensagem(ns) pro dono\")
' 2>/dev/null | grep -E 'enviadas|dry-run|vazio'"
