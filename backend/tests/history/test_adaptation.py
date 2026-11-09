"""A ADAPTAÇÃO DO ATLETA (nº 87). O coach cortou o plano do Leonardo (23,5 → 15 km, longão 9-10 →
6) por um sinal de corpo de 2 dias, quando ele cumpria 100%, estava "absorvendo bem" nas duas
semanas de 22 km e voltou ao normal na semana seguinte das duas vezes que deu sinal. O dono
(29/10): "problemas acontecem; o que de fato segue e deve considerar é a evolução e adaptação do
atleta"."""

from datetime import date, timedelta

from app.application.history import adaptation
from app.application.history.adaptation import assess, render
from app.application.history.weekly_evolution_digest import WeekStat
from app.domain.entities.body_reading_snapshot import BodyReadingSnapshot

CURRENT = date(2026, 10, 26)


def _snap(day: date, state: str):

    return BodyReadingSnapshot(
        at=f"{day.isoformat()}T08:00:00", body_state=state, limiter=None, acwr=None,
        acwr_status="", hrv_recent=None, hrv_direction="", rhr_recent=None, rhr_direction="",
        sleep_avg_hours=None, short_nights=0, nights_counted=0,
    )


def _weeks(rows: list[tuple[float, str | None]]) -> list[WeekStat]:
    """Uma linha por semana, da mais antiga pra atual (`CURRENT` é a última): (km, corpo)."""

    out = []

    for index, (km, state) in enumerate(rows):

        start = CURRENT - timedelta(weeks=len(rows) - 1 - index)

        out.append(
            WeekStat(
                start=start, runs=2 if km else 0, km=km, longest_km=km / 2, pace_sec=None,
                avg_hr=None, aerobic_pace_sec=None,
                body=_snap(start, state) if state else None,
            )
        )

    return out


# 07/09 .. 26/10: o corpo do Leonardo em cada semana (a última é a em andamento, sobrecarregado)
LEONARDO = _weeks([
    (13.3, None), (10.0, "ABSORBING"), (12.6, "ABSORBING"), (10.2, "RECOVERY_FLAG"),
    (22.1, "ABSORBING"), (8.0, "RECOVERY_FLAG"), (22.1, "ABSORBING"), (6.0, "STRAINED"),
])


def test_leonardos_history_says_he_absorbs_load_and_recovers_in_a_week():

    found = assess(LEONARDO, fulfilled=6, planned=6, current=CURRENT)

    assert [(day.day, km) for day, km, _ in found.heavy] == [(5, 22.1), (19, 22.1)]
    assert found.dips == [(date(2026, 9, 28), True), (date(2026, 10, 12), True)]
    assert found.recovered == 2 and found.complies and found.recovers_fast and found.adapts


def test_the_week_in_progress_never_counts_as_history():
    """26/10 está "sobrecarregado" — é o sinal de agora, não o histórico."""

    found = assess(LEONARDO, 6, 6, CURRENT)

    assert all(day < CURRENT for day, _, _ in found.heavy)
    assert all(day < CURRENT for day, _ in found.dips)


def test_the_render_shows_the_numbers_and_the_plan_voice_gets_how_to_weigh_them():

    found = assess(LEONARDO, 6, 6, CURRENT)

    fact = render(found)

    assert "ADAPTAÇÃO DELE" in fact
    assert "Cumpriu 6 de 6 sessões do plano" in fact
    assert "05/10 (22 km, corpo absorvendo bem), 19/10 (22 km, corpo absorvendo bem)" in fact
    assert "em 2 de 2 o corpo não deu sinal na própria semana" in fact
    assert "(semanas de 28/09, 12/10): voltou ao normal na semana seguinte em 2 de 2" in fact
    assert "CONHECIMENTO" not in fact                       # as outras vozes recebem só o fato

    plan = render(found, directive=True)

    assert "a evolução e a adaptação dele pesam MAIS que a semana ruim" in plan
    assert "SEGUIR a rota dele (ele entrega e absorve)" in plan
    assert "Congelar a semana toda vez que o corpo oscila é estagnar" in plan
    assert "Segurar a rampa só se o sinal PERSISTIR por 2 semanas" in plan
    assert "dente de serra" in plan


def test_when_the_signs_did_not_clear_the_next_week_the_signal_weighs_more():

    stuck = _weeks([
        (20.0, "ABSORBING"), (22.0, "RECOVERY_FLAG"), (21.0, "STRAINED"), (20.0, "RECOVERY_FLAG"),
        (19.0, "RECOVERY_FLAG"), (18.0, "STRAINED"),
    ])

    found = assess(stuck, 6, 6, CURRENT)

    assert found.recovered == 0 and not found.recovers_fast and not found.adapts

    text = render(found, directive=True)

    assert "pede mais peso ao sinal de corpo" in text
    assert "os sinais anteriores NÃO voltaram ao normal na semana seguinte" in text
    assert "SEGUIR a rota dele" not in text


def test_who_does_not_follow_the_plan_does_not_get_the_benefit_of_the_doubt():

    found = assess(LEONARDO, fulfilled=2, planned=9, current=CURRENT)

    assert not found.complies and not found.adapts
    assert "ele cumpre pouco do plano" in render(found, directive=True)


def test_without_past_signals_there_is_nothing_to_prove_against_him():

    calm = _weeks(
        [(20.0, "ABSORBING"), (22.0, "ABSORBING"), (21.0, "BALANCED"), (10.0, "STRAINED")]
    )

    found = assess(calm, 6, 6, CURRENT)

    assert found.dips == [] and found.recovers_fast and found.adapts
    assert "Sinais de corpo anteriores" not in render(found)


def test_no_closed_week_with_a_run_gives_no_history():

    assert assess([], 0, 0, CURRENT) is None
    assert assess(_weeks([(0.0, None), (5.0, "STRAINED")]), 0, 0, CURRENT) is None


def test_constants_make_sense():

    assert 0.5 < adaptation._HEAVY_SHARE < 1.0 and 0.5 < adaptation._RECOVERS <= 1.0


def test_five_of_six_is_not_labelled_as_barely_following_the_plan():
    """Renato 01/11: 5 de 6 sessões (83%) caía no corte único de 85% e virava "ele cumpre pouco"
    — a causa era chuva e frio. A zona cinza (60-85%) não decide: nem prova, nem acusa."""

    found = assess(LEONARDO, fulfilled=5, planned=6, current=CURRENT)

    assert not found.complies and not found.barely_complies and not found.weighs_signal

    text = render(found, directive=True)

    assert "cumpre pouco" not in text and "pede mais peso ao sinal de corpo" not in text
    assert "NÃO decide sozinho" in text and "cumpriu 5 de 6" in text
    assert "o MENOR que o sinal justifica" in text


def test_a_single_past_signal_is_a_fact_not_a_pattern():
    """Um sinal anterior que não passou é UMA amostra: não prova que ele não se recupera."""

    one = _weeks([(20.0, "ABSORBING"), (22.0, "ABSORBING"), (21.0, "STRAINED"), (20.0, "STRAINED")])

    found = assess(one, 6, 6, CURRENT)

    assert found.dips == [(date(2026, 10, 19), False)]
    assert found.recovers_fast and not found.stuck and found.adapts
    assert "SEGUIR a rota dele" in render(found, directive=True)  # cumpre + sem padrão: segue a rota


def test_clearly_not_following_or_clearly_stuck_still_weigh_the_signal():

    assert assess(LEONARDO, fulfilled=3, planned=6, current=CURRENT).weighs_signal  # 50% < 60%


def test_stuck_signals_that_started_before_the_load_do_not_justify_a_bigger_cut():
    """Renato 08/11: "0 de 2" eram semanas seguidas do MESMO episódio, que começou numa semana
    leve. Não voltar ao normal não prova que o volume é demais; recuo de volume só destreina."""

    stuck = _weeks([
        (20.0, "ABSORBING"), (22.0, "RECOVERY_FLAG"), (21.0, "STRAINED"), (20.0, "RECOVERY_FLAG"),
        (19.0, "RECOVERY_FLAG"), (18.0, "STRAINED"),
    ])

    found = assess(stuck, 6, 6, CURRENT)

    assert found.stuck

    assert "pede mais peso ao sinal de corpo" in render(found, directive=True)

    unrelated = render(found, directive=True, load_unrelated=True)

    assert "pede mais peso ao sinal de corpo" not in unrelated
    assert "ANTES de a carga subir" in unrelated and "só destreina" in unrelated


def test_barely_following_the_plan_still_weighs_even_if_the_signal_is_load_unrelated():

    stuck = _weeks([
        (20.0, "ABSORBING"), (22.0, "RECOVERY_FLAG"), (21.0, "STRAINED"), (20.0, "RECOVERY_FLAG"),
        (19.0, "RECOVERY_FLAG"), (18.0, "STRAINED"),
    ])

    found = assess(stuck, fulfilled=2, planned=9, current=CURRENT)

    assert "ele cumpre pouco do plano" in render(found, directive=True, load_unrelated=True)
