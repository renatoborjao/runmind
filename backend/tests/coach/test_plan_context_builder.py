from app.application.coach.planning.plan_context_builder import (
    PlanContextBuilder,
)
from datetime import date

from app.domain.entities.training_goal import TrainingGoal
from tests.coach.factories import make_runner

WEEK = date(2026, 9, 28)


def _context(runner, goal=None, days_to_race=None, dossier="") -> str:

    return PlanContextBuilder.build(
        runner=runner,
        goal=goal or TrainingGoal(
            name="10k", distance_km=10.0, target_time=None,
            race_date=None, priority="A",
        ),
        week_start=WEEK,
        days_to_race=days_to_race,
        dossier=dossier,
    )


def test_no_long_run_soft_default_line():
    """O dia do longão não é mais campo rígido — não sai a linha de 'padrão'
    no contexto (a preferência vem pela memória evolutiva, injetada à parte)."""

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Sunday"],
    )

    context = _context(runner).lower()

    assert "por padrao ele faz o longao" not in context
    assert "por padrão ele faz o longão" not in context


def test_days_line_anchors_specific_days_and_count():
    """O retrato TRAVA os dias e a quantidade (não só a frequência) — o Pro
    reshuffava Tue/Thu/Sat pra Wed/Fri/Sat+Sun (bug do Mauricio). A exceção
    (mover por preferência/furo) fica explícita."""

    runner = make_runner(
        preferred_running_days=["Tuesday", "Thursday", "Saturday"],
    )

    context = _context(runner)

    assert "terça-feira, quinta-feira, sábado (3x/semana)" in context.lower()
    assert "AGENDE as sessões NESSES dias" in context
    assert "mantenha ESSA quantidade" in context
    # a exceção legítima continua permitida (longão por preferência / furo)
    assert "longão no domingo" in context


def test_missed_pattern_line_nudges_to_reposition():
    """O que ele vive furando não é bronca — é insumo pra a IA MOVER o
    treino em vez de prescrever de novo igual (a linha vive no dossiê)."""

    from app.domain.entities.adherence_report import (
        AdherenceReport,
        MissedPattern,
    )

    line = PlanContextBuilder._missed_pattern_line(
        AdherenceReport(
            missed_day=MissedPattern("Thursday", 3, 4),
            missed_type=MissedPattern("Intervalado", 3, 4),
        )
    )

    assert "quinta-feira (3 de 4 vezes que foi prescrita)" in line
    assert "treino de Intervalado (3 de 4)" in line
    assert "Não é preguiça" in line


def test_no_pattern_adds_no_line():
    """Sem padrão (ou sem report), o prompt não ganha ruído."""

    from app.domain.entities.adherence_report import AdherenceReport

    assert PlanContextBuilder._missed_pattern_line(AdherenceReport()) == ""

    assert PlanContextBuilder._missed_pattern_line(None) == ""


def test_week_to_build_and_race_distance_open_the_context():

    goal = TrainingGoal(
        name="15k", distance_km=15.0, target_time=None,
        race_date=date(2026, 12, 20),
    )

    context = _context(make_runner(), goal=goal, days_to_race=83)

    assert context.startswith("SEMANA A MONTAR: 28/09 a 04/10/2026.")
    assert "fica a 83 dias do início dela" in context


def test_dossier_closes_the_context():
    """O quadro inteiro (meta, capacidade, corpo, percepção, padrões...) vem
    do DOSSIÊ — a mesma base das outras vozes — depois do que é da tarefa."""

    context = _context(make_runner(), dossier="DOSSIÊ-DO-ATLETA")

    assert context.rstrip().endswith("DOSSIÊ-DO-ATLETA")
    assert context.index("Dias de corrida dele") < context.index("DOSSIÊ")


def test_goal_line_counts_days_not_floored_weeks():
    """13 dias até a prova é ~2 semanas — mostrar 'faltam 13 dias', não
    '1 semana' (o piso de //7 enganava o coach a afiar cedo). Bug do Renato.
    Além disso, prova (10k) e objetivo de fundo (21km) ficam separados."""

    from datetime import date

    goal = TrainingGoal(
        name="correr 21 km, buscar saúde",
        distance_km=10.0,
        target_time=None,
        race_date=date(2026, 8, 23),
    )

    line = PlanContextBuilder._goal_line(
        goal, weeks_to_race=1, days_to_race=13,
    )

    assert "faltam 13 dias" in line
    assert "1 semana" not in line
    assert "Prova-âncora" in line and "10 km" in line
    assert "Objetivo de fundo" in line


def test_goal_line_injects_concrete_target_pace():
    """Com tempo-alvo, o coach recebe o PACE-ALVO exato (00:55:00 em 10k =
    5:30/km) pra ancorar os tiros no ritmo-alvo E o SIMULADO — sem chutar."""

    from datetime import date

    goal = TrainingGoal(
        name="10 km sub-55", distance_km=10.0,
        target_time="00:55:00", race_date=date(2026, 8, 23),
    )

    line = PlanContextBuilder._goal_line(goal, weeks_to_race=2, days_to_race=13)

    assert "alvo 00:55:00" in line
    assert "~5:30/km" in line
    assert "SIMULADO" in line


def test_goal_pace_and_time_parsing():

    from datetime import date

    from app.domain.entities.training_goal import TrainingGoal as TG

    assert PlanContextBuilder._time_to_seconds("00:55:00") == 3300
    assert PlanContextBuilder._time_to_seconds("55:00") == 3300
    assert PlanContextBuilder._time_to_seconds("agosto") is None
    assert PlanContextBuilder._time_to_seconds(None) is None

    goal = TG(name="x", distance_km=10.0, target_time="00:55:00",
              race_date=date(2026, 8, 23))
    assert PlanContextBuilder._goal_pace(goal) == "5:30"

    # sem tempo-alvo -> sem pace
    no_target = TG(name="x", distance_km=21.0975, target_time=None,
                   race_date=date(2026, 9, 1))
    assert PlanContextBuilder._goal_pace(no_target) is None
