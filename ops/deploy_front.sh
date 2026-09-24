#!/usr/bin/env bash
# Deploy do app (PWA) pra VM — o ÚNICO jeito de subir o front.
#   bash ops/deploy_front.sh
# Trava o que já derrubou o app em produção:
#  - build apontando pra localhost (2026-09-23): aborta se sobrar "localhost" no out/
#  - tela branca por chunk velho (2026-09-20): nunca apaga o /_next/ antigo
# Não reinicia o backend (o front é estático, servido pelo Caddy).
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
SITE="https://runmind.duckdns.org"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT/frontend"

echo "==> build de produção"
rm -rf out
NEXT_PUBLIC_API_URL= npm run build

echo "==> trava: nada de localhost no build"
if grep -rlE "https?://(localhost|127.0.0.1)" out/_next out/*.html >/dev/null 2>&1; then
  grep -rlE "https?://(localhost|127.0.0.1)" out/_next out/*.html | head
  echo "ABORTADO: o build aponta pra localhost — NÃO subiu nada." >&2
  exit 1
fi

echo "==> enviando pra VM"
tar -czf /tmp/ritmind-front.tgz -C out .
scp -i "$KEY" /tmp/ritmind-front.tgz "$VM:/tmp/ritmind-front.tgz"
ssh -i "$KEY" "$VM" 'set -e
  rm -rf /tmp/ritmind-front && mkdir /tmp/ritmind-front
  tar -xzf /tmp/ritmind-front.tgz -C /tmp/ritmind-front
  # páginas: espelha (apaga o que saiu) MAS preserva /_next/
  sudo rsync -a --delete --exclude=_next/ /tmp/ritmind-front/ /var/www/ritmind/
  # chunks: só ADICIONA (app já aberto no celular ainda acha os antigos)
  sudo rsync -a /tmp/ritmind-front/_next/ /var/www/ritmind/_next/'

echo "==> conferindo o que o site entrega de verdade"
expected="$(grep -o 'ritmind-v[0-9]*' out/sw.js)"
served="$(curl -s "$SITE/sw.js" | grep -o 'ritmind-v[0-9]*')"
[ "$served" = "$expected" ] || { echo "FALHOU: site serve $served, esperado $expected" >&2; exit 1; }
for c in $(curl -s "$SITE/inicio/" | grep -o '/_next/static/chunks/[^"]*\.js' | sort -u); do
  if curl -s "$SITE$c" | grep -qE "https?://(localhost|127.0.0.1)"; then
    echo "FALHOU: $c aponta pra localhost" >&2; exit 1
  fi
done

echo "OK: front no ar ($served), sem localhost."
