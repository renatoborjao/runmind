from app.application.coach.models.coach_summary import (
    CoachSummary,
)
from app.application.coach.signals.codes import (
    DistanceStatus,
    RecoveryStatus,
    WeeklyVolumeStatus,
)
from app.application.coach.signals.finding import (
    Finding,
    FindingSeverity,
)
from app.application.coach.writer.coach_writer import (
    CoachWriter,
)
from app.domain.entities.workout_structure import WorkoutStructure
from tests.coach.factories import (
    make_activity,
    make_context,
    make_enriched_activity,
)


def _finding(code: str, params: dict | None = None) -> Finding:

    return Finding(
        code=code,
        severity=FindingSeverity.NEUTRAL,
        params=params or {},
    )


def test_render_all_matches_expected_phrase():

    context = make_context()

    summary = CoachSummary(
        runner_name="Renato",
        positives=[
            _finding(
                DistanceStatus.ABOVE.value,
                {"delta_percent": 12.3, "delta_percent_abs": 12.3},
            ),
        ],
    )

    message = CoachWriter.write(context, summary)

    assert message.positives == [
        "Hoje você correu 12% acima da distância prevista. Esse "
        "aumento gera uma carga maior para o organismo."
    ]


def test_render_all_skips_findings_without_template():

    context = make_context()

    summary = CoachSummary(
        runner_name="Renato",
        history=[
            _finding(WeeklyVolumeStatus.IN_PROGRESS.value),
        ],
    )

    message = CoachWriter.write(context, summary)

    assert message.history == []


def test_closing_reflects_recovery_status():

    context = make_context()

    for code, expected in [
        (RecoveryStatus.LONG.value, "Evite treinos intensos até recuperar totalmente."),
        (RecoveryStatus.SHORT.value, "Você pode seguir normalmente com o planejamento."),
    ]:

        summary = CoachSummary(
            runner_name="Renato",
            recovery=[_finding(code)],
        )

        message = CoachWriter.write(context, summary)

        assert message.closing == expected


def test_closing_moderate_without_next_session_is_week_done():
    """Sem próximo treino no plano, o fechamento não fala em 'amanhã'."""

    context = make_context()

    summary = CoachSummary(
        runner_name="Renato",
        recovery=[
            _finding(
                RecoveryStatus.MODERATE.value,
                {"when": "nos próximos dias", "next_day": None},
            ),
        ],
    )

    message = CoachWriter.write(context, summary)

    assert message.closing == (
        "Semana concluída — aproveite o descanso; retomamos no próximo plano."
    )

    assert "amanhã" not in message.closing


def test_closing_moderate_with_next_session_names_the_day():
    """Havendo próximo treino, o fechamento cita o dia — nunca 'amanhã'."""

    context = make_context()

    summary = CoachSummary(
        runner_name="Renato",
        recovery=[
            _finding(
                RecoveryStatus.MODERATE.value,
                {
                    "when": "antes do próximo treino (quinta-feira)",
                    "next_day": "quinta-feira",
                },
            ),
        ],
    )

    message = CoachWriter.write(context, summary)

    assert message.closing == (
        "No próximo treino (quinta-feira), se ainda houver fadiga, "
        "prefira pegar mais leve."
    )


def _interval_structure() -> WorkoutStructure:

    return WorkoutStructure(
        km_splits=[4.0, 6.5, 4.0],
        km_hr=[178, 150, 179],
        lap_count=4,
        lap_paces=[3.9, 6.6, 3.9, 6.6],
        fastest_km_pace=4.0,
        slowest_km_pace=6.5,
        pace_spread=0.625,
        split_trend="even",
        is_interval=True,
        cadence_spm=176,
        hr_avg=168,
        hr_max=185,
        has_detail=True,
    )


def test_executed_lines_carry_full_strava_data():

    activity = make_activity(
        distance=7200.0,
        moving_time=3120,
        max_speed=4.5,
        average_heartrate=168.0,
        max_heartrate=185.0,
        elevation_gain=42.0,
        suffer_score=95,
        raw={"calories": 512},
    )

    executed = make_enriched_activity(
        activity=activity,
        structure=_interval_structure(),
        estimated_zone="Z4",
    )

    context = make_context(executed=executed)

    message = CoachWriter.write(context, CoachSummary(runner_name="Renato"))

    joined = "\n".join(message.executed_lines)

    assert "Distância: 7.20 km" in joined
    assert "Tempo: 52:00" in joined
    assert "Cadência: 176 ppm" in joined
    assert "Elevação: +42 m" in joined
    assert "Calorias: 512 kcal" in joined
    assert "Esforço relativo: 95" in joined
    assert "FC média: 168 · máx 185 bpm (Z4)" in joined


def test_splits_lines_are_rendered():

    executed = make_enriched_activity(structure=_interval_structure())

    context = make_context(executed=executed)

    message = CoachWriter.write(context, CoachSummary(runner_name="Renato"))

    assert message.splits_lines[0] == "km 1: 4:00 min/km · 178 bpm"
    assert len(message.splits_lines) == 3


def test_treadmill_marks_distance_and_hides_rep_meters():

    from app.domain.entities.interval_analysis import IntervalAnalysis

    structure = _interval_structure()
    structure.interval = IntervalAnalysis(
        rep_count=3,
        avg_rep_pace=5.5,
        avg_peak_hr=175,
        avg_recovery_hr=140,
        reps=[
            {"distance_m": 133, "pace": 5.5, "peak_hr": 172},
            {"distance_m": 415, "pace": 5.6, "peak_hr": 168},
            {"distance_m": 210, "pace": 5.5, "peak_hr": 170},
        ],
    )

    executed = make_enriched_activity(structure=structure, indoor=True)

    context = make_context(executed=executed)

    message = CoachWriter.write(context, CoachSummary(runner_name="Renato"))

    executed_text = "\n".join(message.executed_lines)

    assert "(esteira, estimada)" in executed_text

    # metros do relógio (não confiáveis na esteira) não aparecem por tiro
    interval_text = "\n".join(message.interval_lines)

    assert " m ·" not in interval_text
    assert "Tiro 1: 5:30 min/km · pico 172 bpm" in interval_text


def test_no_structure_means_no_splits_section():

    executed = make_enriched_activity(structure=None)

    context = make_context(executed=executed)

    message = CoachWriter.write(context, CoachSummary(runner_name="Renato"))

    assert message.splits_lines == []


def test_external_next_training_notes_are_cleaned():

    from app.application.coach.models.next_training import NextTraining

    nt = NextTraining(
        day="Thursday",
        workout_type="Caminhada com corrida",
        objective="Caminhada com corrida",  # repete o tipo => some
        distance_km=0,
        pace="-",
        heart_rate="-",
        warmup="-",
        main_set="-",
        cooldown="-",
        shoes="-",
        notes=(
            "Descrição: ***FERIADO*** ***TREINO LIVRE***\n"
            "Aquecimento ativo 10' a 15'\n"
            "OBS: Inclinar a esteira em 1% ou 2%\n"
            "Percurso: Livre (Livre )\n"
            "Séries: • 8 x (02:00 - HIIT Moderado)\n"
            "• 10:00 - CAM Moderado"
        ),
    )

    lines = CoachWriter._render_next_training(nt)

    text = "\n".join(lines)

    # objetivo redundante suprimido
    assert not any(line.startswith("Objetivo:") for line in lines)

    # markdown e ruído removidos
    assert "*" not in text
    assert "Percurso: Livre" not in text
    assert "Descrição:" not in text
    assert "Séries:" not in text

    # passos limpos e legíveis
    assert "Do treinador:" in lines
    assert "Aquecimento ativo 10' a 15'" in lines
    assert "Inclinar a esteira em 1% ou 2%" in lines
    assert "8 x (02:00 - HIIT Moderado)" in lines
    assert "10:00 - CAM Moderado" in lines


def test_ai_plan_objective_is_kept_when_it_adds_value():

    from app.application.coach.models.next_training import NextTraining

    nt = NextTraining(
        day="Thursday",
        workout_type="Rodagem leve",
        objective="Construção da base aeróbica",
        distance_km=8.3,
        pace="6:32 - 7:08",
        heart_rate="-",
        warmup="-",
        main_set="-",
        cooldown="-",
        shoes="-",
        notes="-",
    )

    lines = CoachWriter._render_next_training(nt)

    assert "Objetivo: Construção da base aeróbica" in lines
    assert "Do treinador:" not in lines


def test_greeting_uses_runner_name():

    context = make_context()

    summary = CoachSummary(runner_name="Renato")

    message = CoachWriter.write(context, summary)

    assert message.greeting == "Parabéns pelo treino, Renato! 👊"
