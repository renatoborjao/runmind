#!/usr/bin/env bash
#
# Self-test da LÓGICA do oracle_retry.sh — sem Oracle nem OCI CLI de verdade.
# Injeta um "oci" fake (via OCI_BIN) que simula falta de capacidade e depois
# sucesso, e verifica que o loop se comporta como esperado.
#
#   bash ops/selftest_oracle_retry.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

check() {
  if [ "$1" = "$2" ]; then
    echo "  ok: $3"
    pass=$((pass + 1))
  else
    echo "  FALHOU: $3 (esperado '$2', veio '$1')"
    fail=$((fail + 1))
  fi
}

common_env=(
  RETRY_SLEEP=0 THROTTLE_SLEEP=0 MAX_ROUNDS=20 OCI_ADS="AD-1,AD-2"
  OCI_COMPARTMENT=x OCI_SUBNET=x OCI_IMAGE=x OCI_SSH_KEY=/dev/null
)

# --- caso 1: sem vaga nas 3 primeiras tentativas, depois CRIA -------
COUNTER="$WORK/count"
echo 0 > "$COUNTER"

cat > "$WORK/oci_capacity" <<EOF
#!/usr/bin/env bash
n=\$(cat "$COUNTER"); n=\$((n + 1)); echo \$n > "$COUNTER"
if [ \$n -le 3 ]; then
  echo "ServiceError: Out of host capacity." >&2
  exit 1
fi
echo "instance RUNNING"
exit 0
EOF
chmod +x "$WORK/oci_capacity"

out1="$(env "${common_env[@]}" OCI_BIN="$WORK/oci_capacity" \
        bash "$HERE/oracle_retry.sh" 2>&1)"
rc1=$?

check "$rc1" "0" "cria a instância assim que a vaga abre"
echo "$out1" | grep -q "INSTÂNCIA CRIADA" \
  && check ok ok "loga o sucesso" \
  || check no ok "loga o sucesso"

# --- caso 2: erro que NÃO é de capacidade -> para na hora (exit 1) --
cat > "$WORK/oci_authfail" <<'EOF'
#!/usr/bin/env bash
echo "ServiceError: NotAuthorizedOrNotFound" >&2
exit 1
EOF
chmod +x "$WORK/oci_authfail"

out2="$(env "${common_env[@]}" OCI_BIN="$WORK/oci_authfail" \
        bash "$HERE/oracle_retry.sh" 2>&1)"
rc2=$?

check "$rc2" "1" "para num erro que não é de capacidade"
echo "$out2" | grep -q "NÃO é de capacidade" \
  && check ok ok "explica o motivo da parada" \
  || check no ok "explica o motivo da parada"

# --- caso 3: rate limit (429) nas 2 primeiras -> RETENTA, depois CRIA --
COUNTER3="$WORK/count3"
echo 0 > "$COUNTER3"

cat > "$WORK/oci_429" <<EOF
#!/usr/bin/env bash
n=\$(cat "$COUNTER3"); n=\$((n + 1)); echo \$n > "$COUNTER3"
if [ \$n -le 2 ]; then
  echo '{"code": "TooManyRequests", "status": 429}' >&2
  exit 1
fi
echo "instance RUNNING"
exit 0
EOF
chmod +x "$WORK/oci_429"

out3="$(env "${common_env[@]}" OCI_BIN="$WORK/oci_429" \
        bash "$HERE/oracle_retry.sh" 2>&1)"
rc3=$?

check "$rc3" "0" "rate limit (429) NÃO é fatal: recua e retenta até criar"
echo "$out3" | grep -q "rate limit (429)" \
  && check ok ok "loga o recuo por rate limit" \
  || check no ok "loga o recuo por rate limit"

# --- caso 4: timeout de rede nas 2 primeiras -> RETENTA, depois CRIA ---
COUNTER4="$WORK/count4"
echo 0 > "$COUNTER4"

cat > "$WORK/oci_net" <<EOF
#!/usr/bin/env bash
n=\$(cat "$COUNTER4"); n=\$((n + 1)); echo \$n > "$COUNTER4"
if [ \$n -le 2 ]; then
  echo "RequestException: The connection to endpoint timed out." >&2
  exit 1
fi
echo "instance RUNNING"
exit 0
EOF
chmod +x "$WORK/oci_net"

out4="$(env "${common_env[@]}" OCI_BIN="$WORK/oci_net" \
        bash "$HERE/oracle_retry.sh" 2>&1)"
rc4=$?

check "$rc4" "0" "erro transitório de rede NÃO é fatal: recua e retenta até criar"
echo "$out4" | grep -q "transitório de rede" \
  && check ok ok "loga o recuo por erro de rede" \
  || check no ok "loga o recuo por erro de rede"

echo ""
echo "RESULTADO: $pass ok, $fail falha(s)"
[ "$fail" -eq 0 ]
