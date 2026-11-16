---
name: relatorio
description: Lê os relatórios e logs do Ritmind na VM (planos × feito, carga, armazenamento, conferência do plano de domingo, auditorias, backups) e entrega ao Renato um resumo curto do que importa e do que fazer. Use quando ele pedir "relatório", "como estão os atletas", "como foi a semana", "deu algum problema?", "status", ou no começo de uma sessão de acompanhamento.
---

# Relatório do Ritmind

Tudo roda na VM, só leitura e sem IA paga. Dado de atleta fica na nuvem: leia na tela e resuma;
não grave nada no PC (se precisar de arquivo, só no scratchpad e apague logo).

## Fontes

| O quê | Comando | Quando é gerado |
|---|---|---|
| Plano × feito + gasto de IA | `bash ops/relatorio_vm.sh planos [AAAA-MM-DD]` | todo dia 07:00 BRT |
| Carga (ACWR, salto de sessão, retorno) | `bash ops/relatorio_vm.sh carga [AAAA-MM-DD]` | todo dia 07:00 BRT |
| Armazenamento (plano gratuito Oracle) | `bash ops/relatorio_vm.sh armazenamento` | todo dia 07:00 BRT |
| Dias disponíveis | `bash ops/relatorio_vm.sh lista` | — |
| Conferência do plano de domingo, agora | `bash ops/relatorio_vm.sh geracao` (`geracao texto` = com o que cada um recebeu) | sob demanda; cron dom 21:30 |

Logs dos crons (via `ssh -i ~/.ssh/oracle ubuntu@163.176.28.178 '<comando>'`), sempre com `tail`
e filtrando as linhas de resumo (`grep -v -E 'STATUS|====|"ok"'`), nunca o arquivo inteiro:

- `~/ops/coach_sanity.log` — auditoria de sanidade diária (08:30 BRT)
- `~/ops/coach_audit_weekly.log` — auditoria semanal (seg 09:00 BRT)
- `~/ops/plan_generation_monitor.log` — monitor de domingo
- `~/ops/daily_report.log` — o gerador dos relatórios diários
- `~/ops/backup_offsite.log` — backup pro Object Storage (última linha `enviado ...`)
- Serviço: `sudo journalctl -u runmind.service --since "-24h" | grep -i -E "error|falh|traceback" | tail`

## Como escolher

- "Como estão os atletas / a semana": `planos` + `carga` (latest).
- "Deu problema?": logs de sanidade e do monitor, journal do serviço, data da última linha de cada
  log (cron parado = log velho).
- Segunda-feira: `geracao` + auditoria semanal + `planos`.
- Armazenamento só se perguntar ou se o relatório tiver alerta.

## Como responder

- Até ~10 linhas: primeiro o que exige ação (🔴), depois o que é pra acompanhar (🟡), por fim
  "o resto está normal". Primeiro nome do atleta e números, sem colar o relatório bruto.
- Para cada 🔴, uma linha de ação concreta (ex.: "refazer a semana dele: `/regerar-semana`, ~R$ 0,40").
- Se uma fonte não respondeu ou está velha, diga qual e desde quando.
- Gasto de IA: diga o total do período e se saiu do normal.
- Achado sobre um atleta que vale lembrar depois: nota só na VM (`~/notas-claude/memory/`).
