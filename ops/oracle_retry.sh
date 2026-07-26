#!/usr/bin/env bash
#
# Retry de criação da instância ARM Always Free da Oracle (VM.Standard.A1.Flex).
# A Oracle recusa com "Out of host capacity" quando não há máquina livre; a
# capacidade abre e fecha ao longo do dia. Este script tenta em loop, revezando
# os availability domains, e PARA na hora que conseguir (ou num erro que não
# seja de capacidade — pra não rodar à toa num problema de config/cota).
#
# Uso:
#   1) instale e configure a OCI CLI (oci setup config)
#   2) preencha os 6 valores abaixo (ou passe por variável de ambiente)
#   3) rode em segundo plano:
#        nohup bash ops/oracle_retry.sh > ops/oracle_retry.out 2>&1 &
#   4) acompanhe:  tail -f ops/oracle_retry.out
#
# Como pegar cada OCID:
#   ADs      : oci iam availability-domain list   (use os "name")
#   COMPART. : Console > Identity > Compartments  (ou o OCID da tenancy)
#   SUBNET   : crie uma VCN pelo Start VCN Wizard e copie a subnet pública
#   IMAGE    : Compute > Images, filtre por aarch64/ARM (Ubuntu/Oracle Linux)
#   SSH_KEY  : ssh-keygen -t ed25519 -f ~/.ssh/oracle  (usa o .pub)

set -uo pipefail

# ---- preencha (ou exporte OCI_* antes de rodar) --------------------
COMPARTMENT="${OCI_COMPARTMENT:-ocid1.tenancy.oc1..PREENCHER}"
SUBNET="${OCI_SUBNET:-ocid1.subnet.oc1..PREENCHER}"
IMAGE="${OCI_IMAGE:-ocid1.image.oc1..PREENCHER}"
SSH_KEY="${OCI_SSH_KEY:-$HOME/.ssh/oracle.pub}"
SHAPE="${OCI_SHAPE:-VM.Standard.A1.Flex}"
OCPUS="${OCI_OCPUS:-4}"       # teto Always Free ARM: 4 OCPU
MEM_GB="${OCI_MEM_GB:-24}"    # teto Always Free ARM: 24 GB
# ADs separados por vírgula (São Paulo costuma ter só 1)
IFS=',' read -r -a ADS <<< "${OCI_ADS:-AD-1,AD-2,AD-3}"

# ---- knobs (também usados pelo self-test) --------------------------
OCI_BIN="${OCI_BIN:-oci}"          # binário da OCI CLI (o self-test injeta um fake)
RETRY_SLEEP="${RETRY_SLEEP:-120}"  # segundos entre rodadas
MAX_ROUNDS="${MAX_ROUNDS:-0}"      # 0 = infinito (o self-test limita)

ERR_LOG="$(mktemp)"
trap 'rm -f "$ERR_LOG"' EXIT

round=0

while true; do

  round=$((round + 1))

  for AD in "${ADS[@]}"; do

    echo "$(date '+%H:%M:%S') [rodada $round] tentando em $AD..."

    if "$OCI_BIN" compute instance launch \
        --availability-domain "$AD" \
        --compartment-id "$COMPARTMENT" \
        --subnet-id "$SUBNET" \
        --image-id "$IMAGE" \
        --shape "$SHAPE" \
        --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM_GB}" \
        --assign-public-ip true \
        --ssh-authorized-keys-file "$SSH_KEY" \
        --wait-for-state RUNNING 2>"$ERR_LOG"; then

      echo "🎉 INSTÂNCIA CRIADA em $AD! (rodada $round)"
      exit 0

    fi

    if grep -qi "capacity" "$ERR_LOG"; then

      echo "  sem vaga em $AD, sigo tentando"

    else

      echo "❌ erro que NÃO é de capacidade — parando pra você ver:"
      cat "$ERR_LOG"
      exit 1

    fi

  done

  if [ "$MAX_ROUNDS" -gt 0 ] && [ "$round" -ge "$MAX_ROUNDS" ]; then

    echo "atingiu MAX_ROUNDS=$MAX_ROUNDS sem vaga; encerrando."
    exit 2

  fi

  sleep "$RETRY_SLEEP"

done
