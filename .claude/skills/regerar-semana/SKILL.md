---
name: regerar-semana
description: Refaz o plano da semana de UM atleta do Ritmind com o código atual do coach — primeiro um dry-run grátis, depois, só com OK do Renato, a geração paga (~R$ 0,40) que salva, sincroniza o relógio e envia. Use quando o Renato pedir "refaz a semana do X", "regera o plano do X", ou quando o monitor de domingo apontar plano genérico, plano faltando ou corte indevido.
---

# Refazer a semana de um atleta

Script: `ops/regerar_semana.sh` (roda `ops/regerar_semana.py` na VM; a saída vem na tela, nada
fica no PC).

## Regras

- **Um atleta por vez.** Nunca refaça todos, nem em loop, sem pedido explícito do Renato por nome.
- **IA paga só com OK.** O `--apply` faz UMA chamada paga (~R$ 0,40) e ENVIA a mensagem ao atleta.
  Peça o OK no chat dizendo o atleta, a semana e se vai enviar; o pedido inicial ("refaz a semana
  do X") já vale como OK para esse atleta e essa semana.
- O perfil é o id do arquivo (minúsculas, números e `_`, ex.: `renato2`). Se só tiver o nome,
  descubra o id na VM:
  `ssh -i ~/.ssh/oracle ubuntu@163.176.28.178 'ls ~/runmind/backend/storage/profiles'`.
- Treinador externo: o coach não gera o plano dele. Não refaça.

## Roteiro

1. **Por quê?** Tenha claro o motivo (plano de rede, plano faltando, corte de quem entregou,
   lógica do coach mudou depois do domingo). Se a causa é um bug do coach, conserte antes pela
   skill `mudanca-coach`, senão o plano novo sai igual.

2. **Dry-run (grátis, sem IA, sem enviar):**
   ```bash
   bash ops/regerar_semana.sh <atleta>
   ```
   Opções: `--week AAAA-MM-DD` (segunda-feira; o padrão é a PRÓXIMA semana — numa segunda ou
   no meio da semana, passe a semana atual se é ela que quer refazer).
   Resuma ao Renato o plano guardado (km, treinos, maior treino) e o que se espera mudar.

3. **Aplicar (com OK):**
   ```bash
   bash ops/regerar_semana.sh <atleta> --apply [--week AAAA-MM-DD] [--no-send]
   ```
   O script faz backup em `~/rollback_points/regerar-<atleta>-<semana>-<hora>/`, gera, e se a IA
   cair no plano de rede ele RESTAURA o backup e aborta. `--no-send` salva sem mandar mensagem
   (útil quando o Renato quer olhar antes).

4. **Conferir:** a saída tem que mostrar o plano novo salvo (e enviado, se não for `--no-send`).
   Rode `bash ops/relatorio_vm.sh geracao` e confira que o atleta ficou 🟢. Conte ao Renato em
   2-3 linhas: antes × depois (km, treinos), custo e se a mensagem saiu.

5. **Se deu errado:** com o OK do Renato, copie o backup do passo 3 de volta, na VM:
   `plano_<atleta>.json` → `~/runmind/backend/storage/plans/<atleta>.json` e
   `historico_<atleta>.json` → `~/runmind/backend/storage/plans/history/<atleta>.json`.
   Se a mensagem nova já saiu, o atleta precisa de um aviso de que vale o plano anterior.
