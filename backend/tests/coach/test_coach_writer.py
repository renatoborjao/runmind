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
from tests.coach.factories import (
    make_context,
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


def test_greeting_uses_runner_name():

    context = make_context()

    summary = CoachSummary(runner_name="Renato")

    message = CoachWriter.write(context, summary)

    assert message.greeting == "Parabéns pelo treino, Renato! 👊"
