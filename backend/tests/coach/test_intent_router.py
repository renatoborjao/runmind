from app.application.coach.conversation.intent_router import (
    ChatIntent,
    IntentRouter,
)

# ==========================================================
# LAST_TRAINING
# ==========================================================

def test_como_foi_meu_ultimo_treino():

    assert (
        IntentRouter.detect("Como foi meu último treino?")
        == ChatIntent.LAST_TRAINING
    )


def test_como_foi_a_corrida_sem_acento():

    assert (
        IntentRouter.detect("como foi minha corrida hoje")
        == ChatIntent.LAST_TRAINING
    )


def test_analise_do_treino():

    assert (
        IntentRouter.detect("me manda a análise do treino")
        == ChatIntent.LAST_TRAINING
    )


def test_resumo_do_ultimo_treino():

    assert (
        IntentRouter.detect("quero ver o resultado do meu último treino")
        == ChatIntent.LAST_TRAINING
    )


# ==========================================================
# NEXT_TRAINING
# ==========================================================

def test_qual_meu_proximo_treino():

    assert (
        IntentRouter.detect("Qual meu próximo treino?")
        == ChatIntent.NEXT_TRAINING
    )


def test_quando_e_meu_proximo_treino():

    assert (
        IntentRouter.detect("quando será meu próximo treino?")
        == ChatIntent.NEXT_TRAINING
    )


def test_treino_de_amanha():

    assert (
        IntentRouter.detect("qual meu treino de amanhã?")
        == ChatIntent.NEXT_TRAINING
    )


def test_quando_eu_treino():

    assert (
        IntentRouter.detect("quando eu treino de novo?")
        == ChatIntent.NEXT_TRAINING
    )


# ==========================================================
# Sem intenção (segue para o Gemini)
# ==========================================================

def test_statement_about_last_training_is_not_intent():
    """Desabafo sobre o treino não é pedido do card — vai pro Gemini."""

    assert (
        IntentRouter.detect("meu último treino foi bem cansativo viu")
        is None
    )


def test_generic_greeting_is_not_intent():

    assert IntentRouter.detect("bom dia, tudo certo?") is None


def test_plano_da_semana_is_weekly_plan_intent():

    assert (
        IntentRouter.detect("me mostra o plano da semana")
        == ChatIntent.WEEKLY_PLAN
    )


def test_qual_meu_plano_de_treino_is_weekly_plan():
    """A pergunta original do Renato ('qual meu plano de treino')."""

    assert (
        IntentRouter.detect("Qual meu plano de treino?")
        == ChatIntent.WEEKLY_PLAN
    )


def test_proximo_treino_is_not_weekly_plan():
    """'próximo treino' é sessão única, não o plano inteiro."""

    assert (
        IntentRouter.detect("qual meu próximo treino?")
        == ChatIntent.NEXT_TRAINING
    )


def test_ambiguous_last_and_next_returns_none():
    """Casa com os dois — melhor deixar o Gemini resolver."""

    text = "como foi meu último treino e qual o próximo treino?"

    assert IntentRouter.detect(text) is None


# ==========================================================
# BODY_READING
# ==========================================================

def test_como_ta_meu_corpo():

    assert (
        IntentRouter.detect("como tá meu corpo hoje?")
        == ChatIntent.BODY_READING
    )


def test_estou_sobrecarregado():

    assert (
        IntentRouter.detect("acho que estou sobrecarregado")
        == ChatIntent.BODY_READING
    )


def test_minha_recuperacao():

    assert (
        IntentRouter.detect("como está minha recuperação?")
        == ChatIntent.BODY_READING
    )


def test_body_reading_does_not_collide_with_training_intents():
    """'como foi meu treino' segue LAST, não vira leitura do corpo."""

    assert (
        IntentRouter.detect("como foi meu último treino?")
        == ChatIntent.LAST_TRAINING
    )


# ==========================================================
# FITNESS_TREND (estou evoluindo?)
# ==========================================================

def test_estou_evoluindo():

    assert (
        IntentRouter.detect("será que estou evoluindo?")
        == ChatIntent.FITNESS_TREND
    )


def test_minha_evolucao():

    assert (
        IntentRouter.detect("como está minha evolução?")
        == ChatIntent.FITNESS_TREND
    )


def test_estou_ficando_mais_rapido():

    assert (
        IntentRouter.detect("to ficando mais rápido?")
        == ChatIntent.FITNESS_TREND
    )


def test_meu_condicionamento():

    assert (
        IntentRouter.detect("como anda meu condicionamento?")
        == ChatIntent.FITNESS_TREND
    )


def test_meu_sono_is_sleep_axis():
    """Sono virou EIXO PRÓPRIO — sai do corpo, vai pro cartão de sono."""

    assert (
        IntentRouter.detect("e o meu sono, como anda?")
        == ChatIntent.SLEEP
    )


def test_como_esta_meu_sono_is_sleep():

    assert (
        IntentRouter.detect("como está meu sono?")
        == ChatIntent.SLEEP
    )


def test_qualidade_do_sono_is_sleep():

    assert (
        IntentRouter.detect("como anda a qualidade do meu sono?")
        == ChatIntent.SLEEP
    )


def test_meu_corpo_still_body_not_sleep():
    """'como está meu corpo' segue no corpo (não é o eixo de sono)."""

    assert (
        IntentRouter.detect("como está meu corpo?")
        == ChatIntent.BODY_READING
    )


def test_meu_hrv_is_body_reading():

    assert IntentRouter.detect("como está meu hrv?") == ChatIntent.BODY_READING


def test_fitness_does_not_collide_with_body_reading():
    """'como tá meu corpo' segue leitura do corpo, não vira evolução."""

    assert (
        IntentRouter.detect("como tá meu corpo hoje?")
        == ChatIntent.BODY_READING
    )


# ==========================================================
# STATE_PORTRAIT (como você está, no geral)
# ==========================================================

def test_bare_como_estou_is_portrait():

    assert IntentRouter.detect("como estou?") == ChatIntent.STATE_PORTRAIT


def test_como_estou_no_geral_is_portrait():

    assert (
        IntentRouter.detect("como eu tô no geral?")
        == ChatIntent.STATE_PORTRAIT
    )


def test_raio_x_is_portrait():

    assert (
        IntentRouter.detect("me dá um raio-x do meu momento")
        == ChatIntent.STATE_PORTRAIT
    )


def test_panorama_is_portrait():

    assert IntentRouter.detect("quero um panorama geral") == ChatIntent.STATE_PORTRAIT


def test_portrait_does_not_collide_with_body():
    """Pergunta específica do corpo NÃO vira retrato (segue no eixo do corpo)."""

    assert (
        IntentRouter.detect("como está minha recuperação?")
        == ChatIntent.BODY_READING
    )


def test_portrait_does_not_collide_with_fitness():
    """Pergunta específica de evolução NÃO vira retrato."""

    assert (
        IntentRouter.detect("como está minha evolução?")
        == ChatIntent.FITNESS_TREND
    )


# ==========================================================
# HELP (o que dá pra perguntar?)
# ==========================================================

def test_ajuda_is_help():

    assert IntentRouter.detect("ajuda") == ChatIntent.HELP
    assert IntentRouter.detect("/ajuda") == ChatIntent.HELP


def test_menu_is_help():

    assert IntentRouter.detect("menu") == ChatIntent.HELP


def test_o_que_voce_faz_is_help():

    assert IntentRouter.detect("o que você faz?") == ChatIntent.HELP


def test_o_que_posso_perguntar_is_help():

    assert (
        IntentRouter.detect("o que eu posso te perguntar?")
        == ChatIntent.HELP
    )


def test_help_does_not_collide_with_plan():
    """'qual meu plano' segue plano da semana, não vira ajuda."""

    assert (
        IntentRouter.detect("qual meu plano da semana?")
        == ChatIntent.WEEKLY_PLAN
    )


def test_como_corro_a_prova_is_race_strategy():

    assert (
        IntentRouter.detect("como corro minha prova?")
        == ChatIntent.RACE_STRATEGY
    )


def test_pace_da_prova_is_race_strategy():

    assert (
        IntentRouter.detect("qual o pace da prova?")
        == ChatIntent.RACE_STRATEGY
    )


def test_race_strategy_does_not_collide_with_weekly_plan():
    """'plano da prova' é estratégia; 'plano da semana' é a agenda."""

    assert (
        IntentRouter.detect("qual o plano da semana?")
        == ChatIntent.WEEKLY_PLAN
    )


# ==========================================================
# PACE_ZONES
# ==========================================================

def test_minhas_zonas_de_pace_is_pace_zones():

    assert (
        IntentRouter.detect("quais minhas zonas de pace?")
        == ChatIntent.PACE_ZONES
    )


def test_em_que_ritmo_eu_treino_is_pace_zones():

    assert (
        IntentRouter.detect("em que ritmo eu treino?")
        == ChatIntent.PACE_ZONES
    )


def test_pace_do_facil_is_pace_zones():

    assert (
        IntentRouter.detect("qual o pace do fácil?")
        == ChatIntent.PACE_ZONES
    )


def test_pace_zones_does_not_collide_with_race_strategy():
    """'zonas de pace' é treino; 'pace da prova' é estratégia de prova."""

    assert (
        IntentRouter.detect("qual o pace da prova?")
        == ChatIntent.RACE_STRATEGY
    )


# ==========================================================
# MUTAÇÃO suprime cards que só recitam a agenda (bug 03/08)
# ==========================================================

def test_trocar_treino_de_amanha_nao_vira_card_de_proximo():
    """Pedido de TROCAR o treino de amanhã não pode acionar o card de
    'próximo treino' (senão o coach recita o plano e ignora o pedido)."""

    msg = (
        "amanhã vou treinar com meu irmão, o treino dele é 50min de rodagem "
        "6-6:20, quero trocar meu treino de amanhã pra fazer o dele, é possível?"
    )

    assert IntentRouter.detect(msg) is None


def test_mudar_treino_de_hoje_nao_vira_card():

    assert IntentRouter.detect("quero mudar meu treino de hoje") is None


def test_no_lugar_de_suprime_card():

    assert IntentRouter.detect("faço uma rodagem no lugar do treino de hoje?") is None


def test_info_pura_ainda_dispara_apesar_de_hoje_amanha():
    """Sem sinal de mutação, o card informativo segue funcionando."""

    assert IntentRouter.detect("qual meu treino de hoje?") == ChatIntent.NEXT_TRAINING
    assert IntentRouter.detect("qual meu treino de amanhã?") == ChatIntent.NEXT_TRAINING


def test_mudei_de_ideia_nao_e_mutacao():
    """'mudei de ideia' não é pedido de mudar o treino — não suprime o card."""

    assert (
        IntentRouter.detect("mudei de ideia, qual meu treino de hoje?")
        == ChatIntent.NEXT_TRAINING
    )


def test_apply_and_sync_request_is_not_a_plan_recital():
    """Bug do Renato: 'atualizar o plano e enviar o treino pro relógio' casava
    WEEKLY_PLAN e recitava o plano VELHO. Pedido de AGIR não vira recital —
    devolve None pra seguir pros fluxos de ação."""

    assert (
        IntentRouter.detect(
            "consegue atualizar o plano e enviar o treino pro relogio?"
        )
        is None
    )
    assert IntentRouter.detect("manda esse treino pro relógio") is None


def test_pure_plan_question_still_recites():
    """Sem verbo de ação, 'qual meu plano da semana' segue recitando."""

    assert (
        IntentRouter.detect("qual meu plano da semana?")
        == ChatIntent.WEEKLY_PLAN
    )
