from datetime import date

from app.application.planner.weekly_plan_message_formatter import (
    WeeklyPlanMessageFormatter,
)
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan


def _session(day, code, distance, **overrides) -> PlannedSession:

    defaults = dict(
        day=day,
        workout_type=code,
        objective="",
        planned_distance_km=distance,
        planned_duration_minutes=None,
        target_pace_min="6:34",
        target_pace_max="7:10",
    )

    defaults.update(overrides)

    return PlannedSession(**defaults)


def _plan(sessions) -> TrainingPlan:

    return TrainingPlan(
        athlete_name="Renato",
        objective="10k",
        phase="BUILD",
        weekly_volume=30.0,
        running_days=["Tuesday", "Thursday", "Saturday"],
        week_start=date(2026, 7, 20),
        sessions=sessions,
    )


def test_format_includes_runner_name_and_week_start():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Tuesday", "EASY", 6.0)]),
    )

    assert "Renato" in text
    assert "20/07" in text


def test_external_session_shows_coach_text_without_duplicate_km():
    """Plano do treinador (tipo desconhecido): o cabeçalho já traz a km;
    o detalhe mostra o objetivo/observações do treinador, sem repetir a
    distância."""

    plan = _plan([
        _session(
            "Tuesday", "Caminhada com corrida", 5.0,
            objective="HIIT 2x2k ritmo moderado",
            notes="Inclinar a esteira 1-2%",
        ),
    ])

    lines = WeeklyPlanMessageFormatter.session_lines(plan)

    # cabeçalho com a distância uma única vez
    header = lines[0]
    assert "Caminhada com corrida · 5.0 km" in header

    # detalhe traz o que o treinador escreveu, não a km repetida
    # (bullets de detalhe são indentados: "   • ...")
    detail = [line for line in lines if line.startswith("   •")]
    assert any("HIIT 2x2k" in line for line in detail)
    assert any("Inclinar a esteira" in line for line in detail)
    assert not any("5.0 km" in line for line in detail)


def test_external_session_splits_multiline_text_into_clean_bullets():
    """Texto do treinador com várias linhas (e '•' crus embutidos) vira um
    bullet limpo por linha — não um blocão só com o resto vazando."""

    plan = _plan([
        _session(
            "Tuesday", "Caminhada com corrida", 5.0,
            objective="Aquecimento + HIIT 2x2k",
            notes="OBS: inclinar 1-2%\n• 2 x (2km HIIT)\n• 1km CAM",
        ),
    ])

    lines = WeeklyPlanMessageFormatter.session_lines(plan)

    detail = [line for line in lines if line.startswith("   •")]

    assert "   • Aquecimento + HIIT 2x2k" in detail
    assert "   • OBS: inclinar 1-2%" in detail
    assert "   • 2 x (2km HIIT)" in detail
    assert "   • 1km CAM" in detail
    # nada de "•" cru duplicado herdado do texto do treinador
    assert not any("• •" in line for line in detail)


def test_external_session_without_extra_text_is_header_only():
    """Sem objetivo/notas úteis, a sessão externa vira só o cabeçalho —
    nenhum bullet repetindo a distância."""

    plan = _plan([
        _session("Tuesday", "Corrida", 5.0, objective="", notes=""),
    ])

    lines = WeeklyPlanMessageFormatter.session_lines(plan)

    detail = [line for line in lines if line.startswith("   •")]
    assert detail == []


def test_next_session_message_skips_already_done_session():
    """Fez o longão de sábado adiantado: o "próximo treino" pula sábado e
    aponta a terça, em vez de mandar de volta o que já foi feito."""

    plan = _plan([
        _session("Tuesday", "EASY", 6.0),
        _session("Saturday", "LONG_RUN", 12.0),
    ])

    msg = WeeklyPlanMessageFormatter.next_session_message(
        "Renato", plan,
        reference_date=date(2026, 7, 20),  # segunda
        done_days={"Saturday"},
    )

    assert "terça-feira" in msg
    assert "Longão" not in msg


def test_next_session_message_rest_when_remaining_is_done():
    """Só resta a sessão já cumprida -> mensagem de descanso, não repete o
    treino feito."""

    plan = _plan([
        _session("Tuesday", "EASY", 6.0),
        _session("Saturday", "LONG_RUN", 12.0),
    ])

    msg = WeeklyPlanMessageFormatter.next_session_message(
        "Renato", plan,
        reference_date=date(2026, 7, 23),  # quinta (terça já passou)
        done_days={"Saturday"},
    )

    assert "fechou os treinos" in msg


def test_workout_types_are_ptbr_runner_language():

    plan = _plan([
        _session("Tuesday", "EASY", 6.0),
        _session("Thursday", "VO2", 6.5,
                 target_pace_min="5:43", target_pace_max="5:43",
                 notes="5x400m"),
        _session("Saturday", "LONG_RUN", 12.0),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Rodagem leve" in text
    assert "Intervalado" in text
    assert "Longão" in text
    # nada de inglês cru
    assert "Easy Run" not in text
    assert "VO2 Max" not in text
    assert "Long Run" not in text


def test_short_longest_session_is_rodagem_longa_not_longao():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Saturday", "LONG_RUN", 5.1)]),
    )

    assert "Rodagem longa" in text
    assert "Longão" not in text


def test_long_session_over_10km_is_longao():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Saturday", "LONG_RUN", 14.0)]),
    )

    assert "Longão" in text


def test_interval_session_shows_series_and_pace():

    plan = _plan([
        _session("Thursday", "VO2", 6.5,
                 target_pace_min="5:43", target_pace_max="5:43",
                 notes="5x400m"),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Série: 5x400m forte a 5:43/km" in text
    assert "Aquecimento" in text
    assert "Desaquecimento" in text


def test_easy_session_shows_execution_detail():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Tuesday", "EASY", 6.0)]),
    )

    assert "confortáveis" in text
    assert "6:34–7:10/km" in text
    assert "conversar" in text


def test_sessions_in_chronological_order_ptbr():

    plan = _plan([
        _session("Saturday", "LONG_RUN", 12.0),
        _session("Tuesday", "EASY", 6.0),
    ])

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    tuesday_index = text.index("terça-feira")
    saturday_index = text.index("sábado")

    assert tuesday_index < saturday_index
    assert "Tuesday" not in text


# ==========================================================
# next_session_message — "qual meu próximo treino?"
# ==========================================================

def _week_plan() -> TrainingPlan:

    return _plan([
        _session("Tuesday", "EASY", 6.0),
        _session("Thursday", "VO2", 6.5,
                 target_pace_min="5:43", target_pace_max="5:43",
                 notes="5x400m"),
        _session("Saturday", "LONG_RUN", 12.0),
    ])


def test_next_session_includes_today_and_shows_detail():

    # terça 21/07 é dia de treino — o "próximo" é o de hoje
    text = WeeklyPlanMessageFormatter.next_session_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 21),
    )

    assert "Seu próximo treino, Renato" in text
    assert "terça-feira" in text
    assert "confortáveis" in text  # detalhe de execução presente


def test_next_session_skips_to_future_session():

    # quarta 22/07 é descanso — o próximo é quinta (intervalado)
    text = WeeklyPlanMessageFormatter.next_session_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 22),
    )

    assert "quinta-feira" in text
    assert "Série: 5x400m forte a 5:43/km" in text
    assert "terça-feira" not in text


def test_next_session_after_week_done_is_rest_message():

    # domingo 26/07: semana encerrada
    text = WeeklyPlanMessageFormatter.next_session_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 26),
    )

    assert "já fechou os treinos desta semana" in text
    assert "domingo" in text


# ==========================================================
# today_session_message — lembrete matinal 06h
# ==========================================================

def test_today_session_message_on_training_day():

    # quinta 23/07 tem treino
    text = WeeklyPlanMessageFormatter.today_session_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 23),
    )

    assert text is not None
    assert "Bom dia, Renato" in text
    assert "Hoje é dia de treino" in text
    assert "quinta-feira" in text
    assert "Série: 5x400m forte a 5:43/km" in text


def test_today_session_message_on_rest_day_is_none():

    # quarta 22/07 é descanso
    text = WeeklyPlanMessageFormatter.today_session_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 22),
    )

    assert text is None


def test_today_session_message_ignores_session_from_another_week():

    # Bug real (domingo 12/07): o plano corrente já é o da semana que vem
    # (week_start 13/07), com um Longão no DOMINGO 19/07. Hoje (12/07) é
    # domingo e dia de descanso. O lembrete NÃO pode casar a sessão pelo
    # nome do dia ("domingo") e mandar o longão de 19/07 como "treino de
    # hoje" — tem que casar pela DATA real e retornar None.
    next_week = _plan(
        [_session("Sunday", "LONG_RUN", 12.0)],
    )
    next_week.week_start = date(2026, 7, 13)

    text = WeeklyPlanMessageFormatter.today_session_message(
        "Renato",
        next_week,
        reference_date=date(2026, 7, 12),
    )

    assert text is None


# ==========================================================
# week_plan_message — "qual meu plano da semana?" (marca os feitos)
# ==========================================================

def test_week_plan_marks_past_sessions_as_done():

    # sábado 25/07: terça e quinta já passaram, sábado é hoje
    text = WeeklyPlanMessageFormatter.week_plan_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 25),
    )

    assert "Seu plano da semana, Renato" in text

    # terça e quinta marcadas como feitas, em uma linha só (sem detalhe)
    assert "terça-feira (21/07) — Rodagem leve · 6.0 km ✅ (já feito)" in text
    assert "quinta-feira (23/07)" in text
    assert "✅ (já feito)" in text

    # o treino de hoje (sábado) mantém o detalhe de execução
    assert "sábado (25/07)" in text
    assert "ritmo leve e constante" in text

    # passados não repetem o detalhe de execução
    assert "5x400m" not in text


def test_week_plan_start_of_week_has_no_done_marks():

    # segunda 20/07: nada passou ainda
    text = WeeklyPlanMessageFormatter.week_plan_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 20),
    )

    assert "✅ (já feito)" not in text
    assert "5x400m" in text  # detalhe do intervalado presente


def test_plan_message_shows_phase():

    text = WeeklyPlanMessageFormatter.format(
        "Renato",
        _plan([_session("Tuesday", "EASY", 6.0)]),
    )

    assert "Fase: Construção" in text


def test_plan_message_shows_deload_notice():

    plan = _plan([_session("Tuesday", "EASY", 6.0)])
    plan.is_deload = True

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Semana de recuperação" in text


def test_external_plan_has_no_phase_line():

    plan = _plan([_session("Tuesday", "EASY", 6.0)])
    plan.source = "externo"

    text = WeeklyPlanMessageFormatter.format("Renato", plan)

    assert "Fase:" not in text


def test_week_plan_marks_done_and_not_done_from_history():
    """Passado validado no histórico: cumprido = ✅ feito, resto = ❌."""

    text = WeeklyPlanMessageFormatter.week_plan_message(
        "Renato",
        _week_plan(),
        reference_date=date(2026, 7, 25),   # sábado: ter e qui passaram
        done_days={"Tuesday"},              # só a terça foi treinada
    )

    assert "terça-feira (21/07) — Rodagem leve · 6.0 km ✅ (feito)" in text
    assert "quinta-feira (23/07) — Intervalado · 6.5 km ❌ (não feito)" in text
    # nada de assumir que passou = feito
    assert "já feito" not in text


def test_session_lines_custom_past_label():
    """Onboarding marca dias passados como 'já passou', não 'já feito'."""

    lines = WeeklyPlanMessageFormatter.session_lines(
        _week_plan(),
        reference_date=date(2026, 7, 25),  # sábado: ter/qui passaram
        past_label="⏭️ (já passou)",
    )

    text = "\n".join(lines)

    assert "terça-feira (21/07) — Rodagem leve · 6.0 km ⏭️ (já passou)" in text
    assert "já feito" not in text


def test_week_plan_empty_plan_is_friendly():

    plan = _plan([])

    text = WeeklyPlanMessageFormatter.week_plan_message(
        "Renato",
        plan,
        reference_date=date(2026, 7, 20),
    )

    assert "ainda não há um plano" in text
