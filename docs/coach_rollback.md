# Coach — registro de mudanças e rollback

Registro vivo de **toda** mudança no coach (análise, chat, plano, vozes, carga,
evolução) com o jeito de desfazer cada uma. Toda mudança nova no coach ganha uma
linha aqui **no mesmo commit** (ou no commit seguinte ao deploy).

## Pontos de retorno

| O quê | Onde |
|---|---|
| Tag `coach-v0-antes-varredura` | `babb27f` — o coach como estava no ar antes de 26/09 (falta o piso `generated_at`, que já estava na VM e está em `a9aa821` — **não reverter esse**) |
| Tag `coach-v1-com-guardiao` | `b63f05e` — coach com o PlanGuard (regras de código no plano) |
| Tag `coach-v2-ia-decide` | `ae0a92e` — sem guardião; descarga/segurar viram sinal pra IA decidir |
| Tag `coach-v3-dossie` | `4fafb65` — um cérebro só (dossiê único), percepção, PRO pra todos, sem revisor de realismo |
| Tag `coach-v4-entende` | `84967af` — coach entende troca × soma de meta, dias e "refaz a semana"; executa todas as ações da mensagem |
| Backups de 27/09 | `~/rollback_points/coach-2026-09-27/` — stamps, `orphans/` (módulos removidos) e `data/` (dados antes da correção) |
| Backups congelados na VM | `~/rollback_points/coach-2026-09-26/<stamp>/` — cópia do que estava no ar ANTES de cada deploy (o `~/deploy_backups` só guarda os 20 últimos e roda; este não roda) |
| Perfil do renato2 (régua de FC) | `~/rollback_points/coach-2026-09-26/renato2.json.bak-hrzones-20260926` (e o original em `storage/profiles/`) |

## Mudanças (mais antiga → mais nova)

Branch: `fix/avulso-ajuste-sem-loop`. "Stamp" = backup na VM tirado **antes** daquele deploy.

| # | Commit | O que mudou | Arquivos (backend/app/…) | Stamp |
|---|---|---|---|---|
| 1 | `30322b6` | Avulso: ajuste ("bora 8 km?") não cai no loop "pra qual dia?"; avisa e justifica | coach/conversation/coach_brain_executor, one_off_workout_flow; coach/planning/one_off_workout_engine; garmin/one_off_proposal_store | 20260926-200117 |
| 2 | `ab11932` | Avulso honra o ajuste decidido pelo cérebro; "Foco" sem duplicar | coach_brain_executor; planner/weekly_plan_message_formatter | 20260926-201123 |
| 3 | `a8c4555` | Evolução semana a semana no contexto; "manda pro relógio" sem confirmação | coach_brain_executor, conversation_context_builder, one_off_workout_detector, one_off_workout_flow, one_off_workout_engine; **novo** history/weekly_evolution_digest | 20260926-201749 |
| 4 | `d534df7` | Bom dia: corpo em alerta volta a orientar no dia puxado | coach/intelligence/readiness_service; review/readiness_notifier | 20260926-202922 |
| 5 | `adaee42` | Cardápio completo (~30 tipos) + passos com FC/bloco aberto | coach/planning/workout_menu, coach_plan_engine, negotiation_engine, one_off_workout_engine, body_conduct_engine; review/readiness_notifier | 20260926-211700 |
| 6 | `b4dbc7b` | Balanço de estímulos × meta (coach oferece o treino certo) | coach_brain, conversation_context_builder, one_off_workout_flow, ai_plan_service, body_conduct_engine, workout_menu; **novo** history/stimulus_ledger | 20260926-220422 |
| 7 | `0238292` | Balanço mostra a prova real (15 km 20/12) | history/stimulus_ledger | 20260926-220600 |
| 8 | `e6a69f3` | Merge da `feat/strava-no-app` (devolveu o Dossiê da prova que o deploy nº 3 tinha apagado) | conversation_context_builder (+ o resto da feat branch) | 20260926-221702 |
| 9 | `28f685d` | **Coach honesto**: voz única (COACH_VOICE), padrões com dado, puxão de orelha, análise com veredito/atenção/próximo passo, plano segura com piora real, projeção de meta honesta | coach_brain, conversation_context_builder, on_demand_answers, state_portrait_synthesizer, coach_message, ai_plan_service, body_directive, ai_analysis_writer, coach_writer, phrasebook, state_portrait_writer, whatsapp_formatter, training_completed, race_time_predictor, stimulus_ledger, training_pipeline, goal_projection_writer, monthly_recap_narrative_writer, weekly_review_narrative_writer, weekly_review_notifier, core/messages; **novos** coach/writer/coach_voice (vira coach_persona no nº 13), history/training_patterns, persistence/coach_attention_log | 20260926-224050 |
| 10 | `83de7d3` | **Carga (ACWR) régua única**: histograma de FC relido com uma régua (ou Banister) | body_reading_builder, hr_zone_calculator, training_load_analyzer, load_training_history, domain/entities/activity, domain/value_objects/hr_zones, garmin/garmin_activity_source, persistence/activity_archive_repository | 20260926-230315 |
| 11 | `d2d42f6` | Evolução com uma verdade só (panorama na medida da "Forma") | history/weekly_evolution_digest | 20260926-230635 |
| 12 | `bda4fdf` | Chat enxerga a diretriz do plano | conversation_context_builder | 20260926-230824 |
| 13 | `5b3d629` | 2ª varredura das vozes: furo repetido vira conversa franca, primeiro nome, chat antigo | coach_brain, coach_conversation_engine, missed_workout_judge, ai_analysis_writer, coach_writer, state_portrait_writer, events/coach_conversation, notifications/coach_outbox, planner/missed_workout_flow, weekly_review_narrative_writer; coach_voice → **coach_persona** | 20260926-231526 |
| 14 | `a9aa821` | (não é mudança) traz pro git o piso `generated_at` que só existia na VM desde 19/09 — **não reverter** | domain/entities/training_plan, persistence/weekly_plan_repository | — |
| 15 | `10931fa` | PlanGuard (regras no plano) + casamento justo do longão + aderência por família | ai_plan_service, coach_plan_engine, negotiation_engine, history/adherence_analyzer, stimulus_ledger, training_patterns, planner/weekly_plan_matcher; **novo** coach/planning/plan_guard | 20260926-233327 |
| 16 | `b63f05e` | PlanGuard: teto de fortes depende do corpo | ai_plan_service, plan_guard | 20260926-234156 |
| 17 | `0169412` | **Sai o guardião**: IA decide; prompt troca limites fixos por critério de treinador | ai_plan_service, body_directive, coach_plan_engine, negotiation_engine; **removido** plan_guard (guardado em `rollback_points/.../20260927-021547-plan_guard/`) | 20260927-021547 |
| 18 | `ae0a92e` | Descarga vira sinal pra IA pesar (não ordem) e para de brigar com "segurar" | history/deload_analyzer, body_directive, conversation_context_builder | 20260927-022004 |
| 19 | `601f6e7` | Plano no modelo PRO pra TODOS (fim do canário renato2+mauricio) | core/config (default ligado); **VM `.env`** `PLAN_MODEL_PROFILES=` vazio (antigo em `rollback_points/coach-2026-09-26/env.bak-20260927-planpro`) | 20260927-094112 |
| 20 | `4fafb65` | **Um cérebro só**: AthleteDossier em todas as vozes; percepção (relógio/resposta/conversa); sai o revisor de realismo e o brief antigo; forma = veredito combinado; volume real × tendência explícitos; GPS quebrado não ancora VDOT; prova nova não herda tempo-alvo; /ajuda | **novos** coach/context/athlete_dossier, coach/intelligence/perception_recorder; **removidos** coach/context/athlete_brief, coach/planning/plan_realism_reviewer (em `rollback_points/coach-2026-09-27/orphans/`); + 27 arquivos (ver `git show --stat 4fafb65`) | 20260927-102813 |
| 21 | `84967af` | **Coach entende o que o atleta muda**: executor roda TODAS as ações da mensagem; ações novas `days` (dias viram dado do perfil) e `replan` (refaz os dias que faltam da semana e entrega; passado/feito preservado); meta com tempo sem prova vira alvo; cérebro distingue troca × principal × soma × degrau e não promete sem ação; executor de metas pra todos | coach/conversation/coach_brain, coach_brain_executor, goal_action_executor; coach/planning/ai_plan_service, plan_context_builder; core/config (goal_brain default ligado); **VM `.env`** `GOAL_BRAIN_PROFILES=` vazio (antigo em `rollback_points/coach-2026-09-27/data/env.bak-goalbrain`) | 20260927-104241 |
| 22 | `65e3499` | Orçamento de raciocínio do cérebro do chat vira config (`coach_brain_thinking_budget`, padrão 0 = igual antes). Avaliação com gabarito (`ops/coach_lab.sh --braineval 0,4096`): 24/24 nos dois, 2,7 s × 9,5 s → fica o mínimo | core/config, coach/conversation/coach_brain | 20260927-172431 |

### Dados (não é código)

| Quando | O quê | Como desfazer |
|---|---|---|
| 26/09 | `storage/profiles/renato2.json` → `hr_zones` 130/142/155/167/180 (máx 192, repouso 67, garmin:HR_RESERVE) + linha em `hr_zones_history` | copiar `renato2.json.bak-hrzones-20260926` por cima (atenção: a sincronização do Garmin pode regravar as zonas do relógio) |
| 26/09 → | `coach_attention/{perfil}.json` (o que o coach já cobrou) | nada a fazer: código antigo ignora |
| 26/09 → | `hr_histogram` nas atividades do arquivo | nada a fazer: código antigo lê campo a campo e ignora (só descarta o histograma ao regravar a atividade; ao reaplicar o nº 10, a carga usa Banister até o histograma voltar) |
| 27/09 | `profiles/mauricio.json` `target_time` 00:57:00 → 01:22:30 e `races/mauricio.json` (15 km 20/12) → 01:22:30 | copiar `rollback_points/coach-2026-09-27/data/profiles_mauricio.json` e `races_mauricio.json` de volta |
| 27/09 | `best_effort_vdot/helio.json` `max_vdot` 52,2 → null (marca vinda de GPS quebrado; dado derivado, se reconstrói) | copiar `rollback_points/coach-2026-09-27/data/best_effort_vdot_helio.json` de volta |
| 27/09 | `profiles/joaosoares.json`: goal "fazer uma prova de 10 km em pelo menos 55 minutos" → "correr 5 km em 23 minutos", target_time 00:23:00, target_race "5 km", dias ter/sáb → seg/qui/sáb (3x) — o que ele pediu em 05/09 e o coach não aplicou; + 2 linhas na memória | copiar `rollback_points/coach-2026-09-27/data/profiles_joaosoares.json` de volta |
| 27/09 | `memory/renato2.json`: arquivada a nota de 31/07 "longão aos domingos"; nova: longão sempre no fim de semana (sáb OU dom, varia) e semana com tempo curto — pedido do Renato | copiar `rollback_points/coach-2026-09-27/data/memory_renato2.json` de volta |
| 27/09 | renato2: norte vira a MEIA da 31ª Maratona Internacional de São Paulo (04/04/2027, sub-2h, 01:59:59) no lugar da Nike SP de 25/07/2027 (removida da lista de provas; 2 memórias arquivadas + estratégia nova); 15k de 20/12 segue âncora | copiar `rollback_points/coach-2026-09-27/data/{profiles,races,memory}_renato2_meia.json` de volta |
| 27/09 → | `session_rpe/{perfil}.json` ganha `feel`/`note`/`source` | **ATENÇÃO ao reverter o nº 20**: o código antigo lê com `SessionRpe(**record)` e quebraria com os campos novos — antes, remover as chaves `feel`,`note`,`source` dos registros |

## Como desfazer

### A) Pelo git (preferido — passa pela suíte de testes e pelo rollback automático do deploy)

```bash
git switch fix/avulso-ajuste-sem-loop          # a branch que está na VM
git switch -c rollback/<motivo>
git revert --no-edit <commit>                  # um ou vários, do MAIS NOVO pro mais antigo
bash ops/deploy_back.sh --since <commit-antes-dos-reverts>
git push -u origin rollback/<motivo>
```

- Voltar só o "IA decide" (religar o guardião): `git revert --no-edit ae0a92e 0169412`.
- Voltar o dossiê único (nº 20): `git revert --no-edit 4fafb65` + devolver os órfãos de `rollback_points/coach-2026-09-27/orphans/` + limpar `feel/note/source` do `session_rpe` (ver Dados).
- Toda mudança nova no coach: validar ANTES com `bash ops/coach_lab.sh <saida.txt>` (código candidato × dados reais, sem gravar/mandar) e ler o relatório.
- Voltar o coach inteiro pra antes de 26/09: reverter de `ae0a92e` até `28f685d` (nºs 18→9, pulando o 14), depois 7→1 se quiser tirar também avulso/cardápio/balanço. O merge nº 8 **não** se reverte (ele só devolveu código que já estava no ar).
- Arquivo que o revert **apaga** (módulo novo) não é removido da VM pelo deploy — fica como código morto (inofensivo). Pra limpar: `ssh ... mv ~/runmind/backend/app/<arquivo> ~/rollback_points/...`.
- Depois: conferir VM == git (procedimento em `feedback_branch_base_deploy`).

### B) Emergência pela VM (sem máquina local / sem git)

Cada pasta de stamp tem os arquivos **como estavam antes** daquele deploy (e `.new_files` = arquivos que o deploy criou). Pra voltar ao estado de antes do deploy X, aplicar os stamps **do mais novo até X**, nessa ordem:

```bash
ssh -i ~/.ssh/oracle ubuntu@163.176.28.178
cd ~/runmind/backend
RP=~/rollback_points/coach-2026-09-26
for s in 20260927-022004 20260927-021547; do      # do mais novo até o alvo
  (cd $RP/$s && find . -type f ! -name .new_files -exec cp -p {} ~/runmind/backend/{} \;)
  [ -f $RP/$s/.new_files ] && xargs -r rm -f < $RP/$s/.new_files
done
.venv/bin/python -c "import app.main" && sudo systemctl restart runmind.service
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/health   # 200
```

- **Obrigatório** ao aplicar o stamp 20260927-021547: copiar também `$RP/20260927-021547-plan_guard/plan_guard.py` pra `app/application/coach/planning/` (o stamp só tem os arquivos editados; sem ele o `ai_plan_service` antigo não acha o guardião e o plano cai no fallback determinístico).
- Depois de uma emergência, **trazer o git pro mesmo estado** (caminho A) — a VM não pode ficar com código fora de branch.
