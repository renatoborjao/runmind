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
