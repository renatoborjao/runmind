from app.application.coach.conversation.plan_preference_detector import (
    PlanPreferenceDetector,
)


def test_detects_long_run_day_from_the_renato_example():

    pref = PlanPreferenceDetector.detect(
        "domingo eu gosto de longão, se puder manter esse treino",
    )

    assert pref is not None
    assert pref.long_run_day == "Sunday"


def test_detects_various_phrasings():

    assert (
        PlanPreferenceDetector.detect("quero o longão no sábado")
        .long_run_day == "Saturday"
    )
    assert (
        PlanPreferenceDetector.detect("prefiro fazer meu longao na quarta")
        .long_run_day == "Wednesday"
    )
    assert (
        PlanPreferenceDetector.detect("pode colocar o longão na terça?")
        .long_run_day == "Tuesday"
    )


def test_question_about_last_long_run_is_not_a_preference():
    """'como foi meu longão de domingo?' é pergunta, não pedido."""

    assert (
        PlanPreferenceDetector.detect("como foi meu longão de domingo?")
        is None
    )


def test_no_weekday_is_not_a_preference():

    assert PlanPreferenceDetector.detect("gosto de longão") is None


def test_no_long_run_mention_is_not_a_preference():
    """v1 cobre só o dia do longão; outra preferência vai pro chat."""

    assert (
        PlanPreferenceDetector.detect("prefiro treinar de manhã no domingo")
        is None
    )


def test_move_of_a_session_is_not_a_long_run_preference():
    """Bug recorrente do Renato: 'mudar meu treino DE domingo PARA amanhã'
    (mesmo mencionando longão) é um MOVE, não preferência de dia — não pode
    pescar o dia de ORIGEM e responder 'quer incluir domingo nos seus dias?'.
    Deve devolver None pra o MoveSkipFlow cuidar."""

    assert (
        PlanPreferenceDetector.detect(
            "vou precisar mudar meu treino de domingo para amanhã, vai ser um "
            "longão pra dar quilometragem"
        )
        is None
    )


def test_weekday_to_weekday_move_is_not_a_preference():
    """Origem→destino explícito entre dias = move, não preferência."""

    assert (
        PlanPreferenceDetector.detect("muda o longão de sábado pra domingo")
        is None
    )


def test_long_run_of_a_day_stays_a_preference():
    """Guarda não pode over-fire: 'prefiro o longão de domingo' é preferência
    (um dia só, sem destino) — 'de domingo' aqui NÃO é origem de move."""

    pref = PlanPreferenceDetector.detect("prefiro o longão de domingo")

    assert pref is not None
    assert pref.long_run_day == "Sunday"
