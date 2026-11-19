#!/usr/bin/env bash
# Convites do Ritmind (o cadastro no app E pelo Telegram/WhatsApp só entra com um). Roda na VM.
#   bash ops/convite.sh                         # lista os convites (uso / validade)
#   bash ops/convite.sh novo "Maria"            # 1 uso, vale 30 dias
#   bash ops/convite.sh novo "grupo" 5 60       # 5 usos, vale 60 dias (0 dias = não expira)
# O atleta manda o código no Telegram (ou digita no app). Link direto do Telegram:
#   https://t.me/<bot>?start=RIT-XXXX
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"

ACTION="${1:-listar}"
LABEL="${2:-}"
USES="${3:-1}"
DAYS="${4:-30}"

[[ "$USES" =~ ^[0-9]+$ && "$DAYS" =~ ^[0-9]+$ ]] || { echo "usos e dias são números" >&2; exit 1; }

LABEL_Q=$(printf '%q' "$LABEL")

ssh -i "$KEY" "$VM" "cd ~/runmind/backend && ACTION=$ACTION LABEL=$LABEL_Q USES=$USES DAYS=$DAYS .venv/bin/python -c '
import os
from app.infrastructure.persistence.invite_code_repository import InviteCodeRepository
r = InviteCodeRepository()
if os.environ[\"ACTION\"] == \"novo\":
    days = int(os.environ[\"DAYS\"]) or None
    code = r.issue(label=os.environ[\"LABEL\"], max_uses=int(os.environ[\"USES\"]), ttl_days=days)
    print(\"convite:\", code)
else:
    for code, rec in r._load().items():
        ok = \"válido\" if r.validate(code) else \"usado/vencido\"
        print(code, \"|\", rec.get(\"label\") or \"-\", \"|\", rec.get(\"uses\", 0), \"/\", rec.get(\"max_uses\") or \"∞\", \"|\", (rec.get(\"expires_at\") or \"sem prazo\")[:10], \"|\", ok)
'"
