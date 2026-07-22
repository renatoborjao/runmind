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
