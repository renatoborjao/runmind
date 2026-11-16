---
name: deploy
description: Fecha uma mudança do Ritmind do jeito do Renato — testes, commit só com caminhos explícitos, push, deploy do backend e/ou do front na VM e conferência no ar. Use ao terminar QUALQUER mudança de código (sem esperar pedido), e quando o Renato disser "deploy", "sobe", "manda pro ar", "publica".
---

# Deploy do Ritmind

Regra do dono: mudança concluída = commit + push + DEPLOY, sem perguntar. "Pronto" só depois de
conferir no ar. Fale em português do Brasil, direto.

## 1. Antes

- `git status --short` e `git branch --show-current`. Liste o que é DESTA mudança; arquivos soltos
  na pasta (HANDOFF, docs/nutricao_*, ops/informativos/*, .claude/worktrees) NÃO entram.
- Deploy parte da branch que contém o que está no ar. Se a `main` estiver atrás da branch atual,
  avise o Renato numa linha (não faça merge sem ele pedir).
- Mudou algo do coach (`backend/app/application/coach/**`, `planner/**`, prompts, carga,
  dossiê)? Pare e use a skill `mudanca-coach` antes — ela volta pra cá no fim.

## 2. Testes (sem dado de atleta)

- Rodar o teste da área: `cd backend && py -m pytest tests/<área> -q -p no:cacheprovider`.
- Teste nunca lê nem escreve `backend/storage`; use dublês. O gate completo roda sozinho no
  `deploy_back.sh`, numa cópia temporária.

## 3. Commit e push

- `git add <caminho> <caminho> ...` — SEMPRE caminhos explícitos. Nunca `git add -A`, `git add .`
  ou `git commit -a`.
- Mensagem em português: título curto + o que mudou e por quê. Termina com a linha de coautoria
  que o sistema indicar.
- `git push origin <branch>`.

## 4. Deploy

- Backend (arquivos de `backend/app/`):
  `bash ops/deploy_back.sh app/caminho/a.py app/caminho/b.py`
  (ou `bash ops/deploy_back.sh --since <ref>`). Ele compila, roda a suíte inteira, faz backup na
  VM (`~/deploy_backups/<stamp>`), testa o import, reinicia e faz rollback sozinho se o /health
  não voltar. Rodar com timeout longo (~10 min).
- Front (`frontend/`): `bash ops/deploy_front.sh`.
- Scripts de `ops/` que vivem na VM em `~/ops/` não sobem por esses scripts: copiar com
  `scp -i ~/.ssh/oracle ops/<arquivo> ubuntu@163.176.28.178:~/ops/` depois de comparar com o que
  está lá (`md5sum`).
- Cron, serviço ou qualquer configuração persistente na VM: SÓ com OK explícito do Renato no chat.

## 5. Conferir no ar

- Backend: a última linha do deploy tem que ser `OK: backend no ar e respondendo (<stamp>)`.
  Se mudou um módulo rodado por cron/monitor, rode-o na VM em modo de leitura (dry-run) e mostre
  só contagens/resumo, não o dado de atleta.
- Front: abrir `https://runmind.duckdns.org` e conferir o `version.json` novo.
- Anote o stamp do backup — ele vai no registro de rollback quando a mudança é do coach.

## 6. Fechar

Diga em 2-3 frases: o que subiu, o commit, o stamp do backup e como foi conferido. Se algo não foi
conferido, diga isso claramente.
