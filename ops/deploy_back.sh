#!/usr/bin/env bash
# Deploy do backend pra VM — o ÚNICO jeito de subir o backend.
#   bash ops/deploy_back.sh app/x.py app/y/z.py   # arquivos, relativos a backend/
#   bash ops/deploy_back.sh --since <git-ref>     # tudo de backend/app que mudou desde o ref
# Trava:
#  - nada sobe se não compila ou se a suíte de testes não está 100% verde
#  - na VM: guarda a versão ATUAL dos arquivos (~/deploy_backups/<stamp>) e testa
#    o import do app ANTES de reiniciar (import quebrado = não reinicia)
#  - depois do restart espera o /health responder; se não voltar, ROLLBACK
#    automático pro backup e reinicia de novo — o coach nunca fica no chão
# A VM não é git-sincronizada (o app roda dos arquivos) — por isso scp, não pull.
set -euo pipefail

VM="ubuntu@163.176.28.178"
KEY="$HOME/.ssh/oracle"
SITE="https://runmind.duckdns.org"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PY:-$(command -v py || command -v python3 || command -v python)}"

die() { echo "ABORTADO: $* — NÃO subiu nada." >&2; exit 1; }

cd "$ROOT/backend"

FILES=()
if [ "${1:-}" = "--since" ]; then
  [ -n "${2:-}" ] || die "uso: --since <git-ref>"
  while IFS= read -r f; do
    [ -f "$f" ] && FILES+=("$f")
  done < <(git diff --name-only --relative "$2" -- app)
else
  FILES=("$@")
fi

[ ${#FILES[@]} -gt 0 ] || die "nenhum arquivo pra subir"

for f in "${FILES[@]}"; do
  case "$f" in app/*) ;; *) die "'$f' fora de backend/app (só código do app sobe por aqui)";; esac
  [ -f "$f" ] || die "'$f' não existe"
done

echo "==> arquivos:"; printf '    %s\n' "${FILES[@]}"

echo "==> compila"
"$PY" -m py_compile "${FILES[@]}" || die "arquivo não compila"

echo "==> suíte de testes (tem que estar 100% verde)"
"$PY" -m pytest -q -p no:cacheprovider >/tmp/ritmind-pytest.log 2>&1 \
  || { tail -15 /tmp/ritmind-pytest.log; die "testes falharam"; }
tail -1 /tmp/ritmind-pytest.log

STAMP="$(date +%Y%m%d-%H%M%S)"
tar -czf /tmp/ritmind-back.tgz "${FILES[@]}"

echo "==> enviando pra VM (backup em ~/deploy_backups/$STAMP)"
scp -q -i "$KEY" /tmp/ritmind-back.tgz "$VM:/tmp/ritmind-back.tgz"

ssh -i "$KEY" "$VM" bash -s -- "$STAMP" "${FILES[@]}" <<'REMOTE'
set -euo pipefail
STAMP="$1"; shift
cd ~/runmind/backend
BK=~/deploy_backups/$STAMP
mkdir -p "$BK"

# guarda o que está no ar AGORA (inclusive mudança viva que não está no git)
for f in "$@"; do
  if [ -f "$f" ]; then mkdir -p "$BK/$(dirname "$f")"; cp -p "$f" "$BK/$f"
  else echo "$f" >> "$BK/.new_files"; fi
done

rollback() {
  echo "!!! ROLLBACK: restaurando a versão anterior" >&2
  (cd "$BK" && find . -type f ! -name .new_files -exec cp -p {} ~/runmind/backend/{} \;)
  [ -f "$BK/.new_files" ] && xargs -r rm -f < "$BK/.new_files"
  if [ "${1:-}" = restart ]; then
    sudo systemctl restart runmind.service
    for i in $(seq 1 45); do
      [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8000/api/v1/health)" = 200 ] \
        && { echo "rollback no ar (versão anterior respondendo)" >&2; break; }
      sleep 2
    done
  fi
  exit 1
}

tar -xzf /tmp/ritmind-back.tgz

# import do app ANTES de reiniciar: quebrado aqui = nem derruba o que está no ar
.venv/bin/python -c "import app.main" >/tmp/ritmind-import.log 2>&1 \
  || { tail -8 /tmp/ritmind-import.log >&2; rollback; }

sudo systemctl restart runmind.service

ok=""
for i in $(seq 1 45); do
  [ "$(curl -s -o /dev/null -m 5 -w '%{http_code}' http://127.0.0.1:8000/api/v1/health)" = 200 ] && { ok=1; break; }
  sleep 2
done
[ -n "$ok" ] || { journalctl -u runmind.service -n 20 --no-pager >&2; rollback restart; }

# mantém os 20 backups mais recentes
ls -1dt ~/deploy_backups/*/ | tail -n +21 | xargs -r rm -rf
echo "no ar (backup da versão anterior: $BK)"
REMOTE

echo "==> conferindo pelo site"
code="$(curl -s -o /dev/null -m 15 -w '%{http_code}' "$SITE/api/v1/health")"
[ "$code" = 200 ] || { echo "FALHOU: $SITE/api/v1/health respondeu $code" >&2; exit 1; }

echo "OK: backend no ar e respondendo ($STAMP)."
