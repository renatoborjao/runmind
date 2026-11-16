---
name: mudanca-coach
description: Roteiro obrigatório pra qualquer mudança no coach do Ritmind (plano, chat, análise, carga, dossiê, prompts, vozes) — lab antes × depois na VM, leitura do resultado, deploy e linha no docs/coach_rollback.md. Use sempre que a mudança tocar backend/app/application/coach/**, planner/**, history/** ou os prompts, e quando o Renato disser "muda o coach", "o coach devia...", "ajusta o plano".
---

# Mudança no coach

O coach é o coração do produto e não tem guardião de código por cima: a IA decide com dado +
conhecimento. A segurança é ver o que muda ANTES de ir pro ar e saber desfazer depois.

## Regras que não mudam

- **Dado de atleta só na nuvem.** A saída do lab tem dado real: grave SEMPRE no scratchpad desta
  sessão, leia, resuma e APAGUE o arquivo na mesma hora. Nunca no repo, nunca em `docs/`, nunca na
  memória do PC. Nota sobre atleta específico vai só pra `~/notas-claude/memory/` na VM.
- **IA paga só com OK.** O lab com `--context-only` é grátis (só monta contexto/dossiê/sinais).
  Sem essa flag ele chama o Gemini de verdade: diga quantos atletas e cenários e peça o OK antes.
- Sem guarda de código decidindo pela IA: a mudança dá dado e diretriz melhores; não um `if` que
  sobrescreve a decisão.
- Datas "de hoje" só via `app/core/clock.py` (fuso BRT); teste a virada de semana.

## Roteiro

1. **Entender e mudar.** Faça a mudança no código e os testes (puros, sem storage real).
   `cd backend && py -m pytest tests/<área> -q -p no:cacheprovider`.

2. **Lab grátis, antes × depois** (sem commit ainda: o lab sobe o que difere do HEAD):
   ```bash
   S=<scratchpad desta sessão>
   bash ops/coach_lab.sh --no-overlay "$S/antes.txt" --context-only --only dossier,plan
   bash ops/coach_lab.sh "$S/depois.txt" --context-only --only dossier,plan
   ```
   - Se o plano da semana já existe e a mudança é na geração do plano, acrescente `--replay`
     (refaz o estado de antes do plano existir).
   - `--profiles a,b` pra limitar; `--full` imprime o contexto inteiro do plano.
   - Compare (`diff`) e leia: o sinal/diretriz mudou do jeito esperado e SÓ onde devia?

3. **Lab com IA (opcional, pago).** Se a mudança é na fala/decisão e o contexto não basta pra
   julgar, peça o OK do Renato com o custo estimado e rode sem `--context-only`
   (`--only plan` ou `chat`) com `--profiles a,b` — o script RECUSA lab pago sem atletas escolhidos
   (todos só com `--todos`). O plano no lab usa o Pro, como na produção (~R$ 0,33 por atleta), e
   o gasto aparece como "lab" no medidor.

4. **Contar ao Renato** em poucas linhas, sem colar dado bruto: o que mudou no antes × depois,
   para quantos atletas, e qualquer surpresa. Apague `antes.txt`/`depois.txt` em seguida.

5. **Deploy** pela skill `deploy` (commit com caminhos explícitos, push,
   `bash ops/deploy_back.sh <arquivos>`). Anote o stamp do backup.

6. **Registro de rollback** em `docs/coach_rollback.md`, no topo da lista de seções datadas
   (logo antes da seção datada mais recente), no mesmo commit ou no seguinte ao deploy:
   ```markdown
   ## DD/MM/AAAA — <título curto>

   - **O que mudou:** <arquivos e comportamento, sem nome/dado de atleta além do primeiro nome>
   - **Backup na VM:** `~/deploy_backups/<stamp>`.
   - **Voltar:** copiar os arquivos do stamp de volta pra `~/runmind/backend/` e
     `sudo systemctl restart runmind.service`.
   - **Motivo:** Renato DD/MM ("<pedido>").
   ```
   Commit + push do registro.

7. **Refazer a semana de alguém?** Só de UM atleta e só se o Renato pedir:
   `bash ops/regerar_semana.sh <atleta>` (dry-run, grátis) e, com OK,
   `bash ops/regerar_semana.sh <atleta> --apply` (~R$ 0,40). Nunca de todos sem pedido.

8. **Depois do domingo:** o monitor das 21:30 manda o resumo e o plano de cada atleta no Telegram.
   Para conferir na hora: `bash ops/relatorio_vm.sh geracao`.
