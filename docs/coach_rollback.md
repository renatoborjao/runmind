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
| 23 | `a25934f` | Bom dia: treino aliviado vira rodagem leve de verdade (propósito de recuperação, passo pro relógio com teto de FC) + COACH_VOICE e acentuação no bom dia e no recap | coach/planning/body_conduct_engine, review/monthly_recap_narrative_writer | 20260927-181111 |
| 24 | `d7a393e` | **Varredura final**: pular (dia/semana) aplica na hora e diz o que saiu (antes o pulo da semana não era aplicado e o coach prometia); doença em aberto (IllnessEpisode) = sem cobrança de furo, lembrete do dia acolhe, dossiê não lê "folga pra puxar"; ação `watch` no cérebro (manda pro Garmin em vez de "vou tentar"); "nada pra agendar" não é falha; acento regerado no cliente Gemini (JSON e prosa); dossiê com UMA leitura do corpo (deriva inclui hoje), ✅ no treino de hoje feito, lacuna sem duplicata, memória "a mais recente vale"; extrator de memória não grava pedido pontual de dia | coach/conversation/coach_brain, coach_brain_executor, coach_conversation_engine; coach/context/athlete_dossier; coach/memory/runner_memory_service, memory_extraction_engine; coach/writer/body_reading_writer; review/reengagement_writer; garmin/garmin_sync; history/stimulus_ledger, training_patterns; planner/daily_training_notifier, missed_workout_flow, weekly_plan_message_formatter; integrations/gemini/client; **novo** coach/intelligence/illness_episode | 20260927-184613 + 20260927-184859 (memória) |
| 25 | `efb5f7a` | Chat recebe o fato de QUANDO chega o plano da semana que vem (domingo 20h; ainda não montado antes disso) — o coach disse "amanhã cedinho" e descreveu um plano que não existia | coach/conversation/conversation_context_builder | 20260927-192204 |
| 26 | `f27e31a` | Plano escolhe LIVRE pela evolução da semana inteira (a instrução antiga mandava girar só o dia forte entre tempo/fartlek/progressivo); IA vê as últimas semanas dia a dia; SUBIDA sai do repertório do plano e das lacunas (só no avulso, quando o atleta pede — decisão do Renato) | coach/planning/coach_plan_engine, plan_context_builder, workout_menu, one_off_workout_engine; history/stimulus_ledger | 20260927-221759 |
| 27 | `da5788e` | Carga/ACWR: semana SEM treino no mês não entra na base (com 2+ semanas ativas) — a volta ao normal virava pico (Leonardo: 1,62 "risco de lesão alto" → 1,22); base baixa (<90 min/sem) só é pico com +30 min reais; risco de lesão respeita isso; dossiê explica | history/training_load_analyzer, injury_risk_analyzer; domain/entities/training_load; coach/context/athlete_dossier | 20260927-222803 |
| 28 | `7069ac4` | Carga do corpo (ACWR/risco de lesão) só com corrida/caminhada — musculação/futebol/bike saem da razão (antes somavam e inflavam pico: João) e aparecem no dossiê como "fora da corrida (7 dias)" pra pesar com a recuperação — decisão do Renato: coach de corrida | coach/intelligence/body_reading_builder; coach/context/athlete_dossier | 20260927-223300 |
| 29 | `93ff0f3` | HRV e FC de repouso: a última semana contra a FAIXA NORMAL do atleta (média ± 1 DP dos ~2 meses; mínimo 2 ms / 1,5 bpm) em vez de semana × semana — sem base de 2 meses, regra antiga. Recálculo de 8 semanas dia a dia: Maurício 62%→30% do tempo em alerta, Renato 55%→42%, Fernanda 21%→7%; episódios reais mantidos | history/recovery_trend_analyzer | 20260927-223853 |
| 30 | `69b96ca` | Calibração de pace contra a FAIXA prescrita (dentro = 0): medir contra o limite lento fazia "acertou o alvo" virar "~10 s mais rápido, APERTE" (renato2 4/4 e 7/8 no alvo) | history/pace_calibration_analyzer | 20260927-224600 |
| 31 | `0546c18` | Periodização em BLOCOS: a IA abre um bloco (3-6 semanas: foco + papel de cada semana) guardado no plano que o abriu; as semanas seguintes recebem "semana k de N — papel"; desvio redefine; mensagem mostra 📦. Dia extra: a IA PROPÕE (💡, campo suggest_extra_day) quando serve à evolução — nunca adiciona. Plano ganha block/block_label/extra_day_note (código antigo ignora) | domain/entities/training_plan; persistence/weekly_plan_repository; coach/planning/coach_plan_engine, plan_context_builder, ai_plan_service; planner/weekly_plan_message_formatter | 20260927-225325 |
| 32 | `4d25cc2` | Calibração de pace VIVA: sai o viés calculado (pace_calibration_analyzer/store → diretriz "aperte/afrouxe") e entra o PLANEJADO × EXECUTADO no dossiê — sessão a sessão (6 sem): alvo → feito, blocos do relógio (gravados no pós-treino em execution_log), FC, RPE; a IA calibra e lê a evolução. + STEPS_RULE: contínuo = 1 passo, nunca fatiar por km (Maurício: rodagem/longão com 8-9 passos de 1 km); duration_min arredonda (20 s virava 19 s) | history/execution_log (novo), persistence/execution_log_store (novo), orchestrators/training_pipeline, coach/context/athlete_dossier, history/training_patterns, coach/planning/workout_menu, domain/entities/workout_step; removidos history/pace_calibration_analyzer, persistence/pace_calibration_store | 20260928-083751 |
| 33 | `0dab979` | Refazer a semana (replan) leva o PEDIDO do atleta até o plano: as palavras dele + o que o cérebro entendeu entram no contexto como "PEDIDO DO ATLETA AGORA" (antes o replan refazia só com o dossiê e o "só leve até sexta" se perdia — pior no adjust + replan, em que o replan vence) | planner/current_plan_provider; coach/planning/ai_plan_service, plan_context_builder; coach/conversation/coach_brain_executor | 20260928-084758 |

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
| 27/09 | `coach_attention/*.json`: removidas as cobranças "weekly" que NUNCA foram enviadas (a revisão simulada do lab gravava em produção) — fernanda 3→1, helio 2→1, joaosoares 2→0, leonardo 2→0, mauricio 3→1, renato2 2→0 | copiar `rollback_points/coach-2026-09-27/data/coach_attention_antes_limpeza/*` de volta |
| 27/09 | `memory/renato2.json`: tirada a data duplicada "(27/09) (27/09)" da nota do longão | copiar `rollback_points/coach-2026-09-27/data/memory_renato2_antes_data_dup.json` de volta |
| 27/09 | `memory/mauricio.json`: arquivadas 4 notas de dia pontuais/superadas (01/09 chuva, 10/09 "o de hoje pra amanhã", 11/09 longo domingo + sexta — superada pela de 13/09 "fixos ter/qui/sáb", 17/09 prova de 19/09) | copiar `rollback_points/coach-2026-09-27/data/memory_mauricio_antes_dias.json` de volta |
| 28/09 | `app/.../pace_calibration_analyzer.py` e `pace_calibration_store.py` movidos da VM (órfãos após o nº 32) | reverter o nº 32 os devolve; ou copiar de `rollback_points/coach-2026-09-27/orphans_20260928/` |
| 27/09 | `pace_calibration/*.json`: amostras zeradas (medidas contra o limite lento da faixa — viés falso de "mais rápido"); ids processadas mantidas | copiar `rollback_points/coach-2026-09-27/data/pace_calibration_antes/*` de volta |
| 28/09 → | `execution_log/{perfil}.json` (novo; preenchido com a seção "Execução por bloco" das análises já enviadas: fernanda 2, leonardo 2, mauricio 4, renato2 6) | nada a fazer: código antigo ignora |
| 28/09 | `memory/mauricio.json` nota m-192e6561 "paces por km (parciais)" reescrita como estratégia de PROVA (não de treino) — era da prova de 19/09 e fazia a IA fatiar rodagem/longão por km | copiar `rollback_points/coach-2026-09-27/data/memory_mauricio_20260928_pre_scope.json` de volta |
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
