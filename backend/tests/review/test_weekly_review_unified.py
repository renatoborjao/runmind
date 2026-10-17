"""DOMINGO EM 2 MENSAGENS (atrás de flag, canário renato2): o resumo da semana leva o
retrato condensado e o "rumo à meta" (só com novidade ou 1x/mês) DENTRO dele, em vez de
3 mensagens no mesmo minuto. O plano das 20h segue separado (outro job)."""

import asyncio
from contextlib import ExitStack
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.application.coach.writer.state_portrait_writer import StatePortraitWriter
from app.application.review.goal_projection_news import (
    MONTHLY_DAYS,
    projection_is_news,
    weeks_band,
)
from app.application.review.goal_projection_writer import GoalProjectionWriter
from app.application.review.weekly_review_notifier import WeeklyReviewNotifier
from app.domain.entities.aerobic_efficiency import EFF_IMPROVING, AerobicEfficiency
from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BUILDING,
    BodyReading,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import (
    EVO_IMPROVING,
    EVO_INSUFFICIENT,
    FitnessEvolution,
)
from app.domain.entities.training_goal import TrainingGoal
from app.domain.entities.training_load import LOAD_OPTIMAL, TrainingLoad
from tests.coach.factories import make_runner

N = "app.application.review.weekly_review_notifier"

TODAY = date(2026, 10, 18)

SNAP = {
    "seconds": 5382, "target_time": "01:22:30", "distance_km": 15.0,
    "race_date": "2026-12-20", "weeks": 9,
}


# ---- quando o "rumo à meta" volta a aparecer ----------------------------------


def test_first_time_is_news():

    assert projection_is_news(None, SNAP, TODAY) == (True, "first")


def test_nothing_new_stays_silent_until_the_monthly_return():

    last = {**SNAP, "date": "2026-10-11"}

    assert projection_is_news(last, SNAP, TODAY) == (False, "nothing_new")

    # 28 dias depois, sem mais nada: volta 1x por mês
    old = {**SNAP, "date": date.fromordinal(TODAY.toordinal() - MONTHLY_DAYS).isoformat()}

    assert projection_is_news(old, SNAP, TODAY) == (True, "monthly")


def test_projection_that_moved_enough_is_news():

    last = {**SNAP, "date": "2026-10-11"}

    # 1% de 5382 s = 54 s: 60 s mais rápido já é novidade; 30 s não
    assert projection_is_news(last, {**SNAP, "seconds": 5322}, TODAY) == (True, "moved")
    assert projection_is_news(last, {**SNAP, "seconds": 5352}, TODAY)[0] is False


def test_changed_goal_or_a_closer_race_band_is_news():

    last = {**SNAP, "date": "2026-10-11"}

    assert projection_is_news(last, {**SNAP, "target_time": "01:25:00"}, TODAY) == (
        True, "goal_changed",
    )

    # 9 semanas -> 8: entrou na faixa de 8 semanas
    assert projection_is_news(last, {**SNAP, "weeks": 8}, TODAY) == (True, "band")


def test_weeks_band():

    assert [weeks_band(w) for w in (None, 20, 12, 9, 8, 5, 4, 1, 0)] == [
        "none", "far", "12w", "12w", "8w", "8w", "4w", "4w", "week",
    ]


# ---- as seções condensadas ----------------------------------------------------


def _reading(body_state=BODY_ABSORBING, has_recovery=True):

    rec = (
        RecoveryTrend(
            days_covered=5, hrv_recent=57.0, rhr_recent=48,
            sleep_avg_hours=5.7, short_nights=8, nights_counted=14,
        )
        if has_recovery
        else RecoveryTrend(days_covered=0)
    )

    load = TrainingLoad(
        acute_load=100, chronic_load=95, acwr=1.05, status=LOAD_OPTIMAL,
        days_of_history=40, weekly_loads=[90, 95, 100, 105],
    )

    return BodyReading(load=load, recovery=rec, body_state=body_state, limiter="sono")


def _evolution(direction=EVO_IMPROVING):

    ef = AerobicEfficiency(
        direction=EFF_IMPROVING, runs_counted=8, weeks_covered=8,
        ref_hr=154, pace_gain_sec=17,
    )

    return FitnessEvolution(direction=direction, ef=ef, days_since_last_run=2)


def test_compact_portrait_is_short_and_keeps_the_sleep_warning():

    text = StatePortraitWriter.write_compact(_reading(), _evolution())

    assert text.startswith("📷 Como você está")
    assert "💪 Corpo: absorvendo bem o aumento de treino · atenção ao sono" in text
    assert "📈 Forma: subindo" in text
    assert "17 s/km" in text                       # a tradução sentível da forma continua
    # sem o painel de números (HRV, sono, FC...) — esse fica em "como estou?" e no app
    assert "Sua recuperação" not in text and "HRV" not in text
    assert len(text.splitlines()) <= 6


def test_compact_portrait_is_none_without_any_axis():

    nothing = _reading(body_state=BODY_BUILDING, has_recovery=False)

    empty_evolution = FitnessEvolution(direction=EVO_INSUFFICIENT)

    assert StatePortraitWriter.write_compact(nothing, empty_evolution) is None


def test_projection_section_is_compact_and_returns_the_snapshot():

    goal = TrainingGoal(
        name="15 km", distance_km=15.0, target_time="01:22:30",
        race_date=date(2026, 12, 20),
    )

    pred = {"formatted": "1:29:42", "seconds": 5382, "delta_seconds": 432}

    with patch(
        "app.application.review.goal_projection_writer.RaceTimePredictor.predict_formatted",
        return_value=pred,
    ):

        text, snap = GoalProjectionWriter.section("Mauricio", goal, object(), weeks_to_race=9)

    assert text.startswith("🎯 Rumo à meta (15 km)")
    assert "1:29:42" in text and "Faltam 9 semanas" in text
    assert "\n\n" not in text                      # enxuto: sem linhas em branco
    assert snap == {
        "seconds": 5382, "target_time": "01:22:30", "distance_km": 15.0,
        "race_date": "2026-12-20", "weeks": 9,
    }


# ---- o fluxo de domingo -------------------------------------------------------


class _Shown:
    """Store em memória do 'rumo à meta' já mostrado."""

    def __init__(self, last=None):

        self.last = last
        self.saved = []

    def load(self, _profile):

        return self.last

    def save(self, profile, snapshot, shown_on):

        self.saved.append((profile, snapshot, shown_on))


def _sunday(unified, shown=None, profile="renato2"):
    """Roda o domingo de UM atleta. Devolve (CoachOutbox mock, store, portrait/proj mocks)."""

    store = shown or _Shown()

    settings = SimpleNamespace(
        weekly_review_unified_active_for=lambda p: unified and p == "renato2"
    )

    goal = TrainingGoal(
        name="15 km", distance_km=15.0, target_time="01:22:30",
        race_date=date(2026, 12, 20),
    )

    with ExitStack() as stack:

        def on(target, **kwargs):

            return stack.enter_context(patch(target, **kwargs))

        def on_method(name):

            return stack.enter_context(
                patch.object(WeeklyReviewNotifier, name, new=AsyncMock())
            )

        repo_cls = on(f"{N}.RunnerProfileRepository")
        load_runner = on(f"{N}.LoadRunnerProfile")
        load_history = on(f"{N}.LoadTrainingHistory")
        on(f"{N}.WeeklyReviewBuilder")
        narrative = on(f"{N}.WeeklyReviewNarrativeWriter")
        formatter = on(f"{N}.WeeklyReviewMessageFormatter")
        outbox = on(f"{N}.CoachOutbox")
        on(f"{N}.now_in", return_value=datetime(2026, 10, 18, 19, 0))
        guard = on(f"{N}.DispatchGuard")
        portrait_service = on(f"{N}.StatePortraitService")
        portrait_writer = on(f"{N}.StatePortraitWriter")
        on(f"{N}.get_settings", return_value=settings)
        on(f"{N}.GoalProjectionShownStore", return_value=store)
        legacy_portrait = on_method("_send_state_portrait")
        legacy_projection = on_method("_send_goal_projection")
        on_method("_refresh_best_efforts")
        on_method("_notify_pace_progress")
        on_method("_notify_cadence_progress")
        on_method("_distill_learnings")
        on(
            "app.application.review.goal_projection_writer.GoalProjectionWriter.section",
            return_value=("🎯 PROJEÇÃO", SNAP),
        )
        on(
            "app.application.use_cases.build_training_goal.BuildTrainingGoal.execute",
            return_value=goal,
        )
        on(
            "app.application.history.training_patterns.TrainingPatterns.drift_for_profile",
            return_value=None,
        )

        guard.already_sent.return_value = False

        repo_cls.return_value.list_active.return_value = [profile]
        load_runner.execute.return_value = make_runner(name="Renato", phone="+5511900000001")
        load_history.execute = AsyncMock(return_value=object())
        narrative.write = AsyncMock(return_value=None)
        formatter.format.return_value = "📝 RESUMO DA SEMANA"
        portrait_service.read.return_value = (MagicMock(), MagicMock())
        portrait_writer.write_compact.return_value = "📷 RETRATO"
        outbox.send = AsyncMock()

        asyncio.run(WeeklyReviewNotifier.notify_all())

        return outbox, store, legacy_portrait, legacy_projection


def test_unified_sends_ONE_message_with_review_portrait_projection_and_tip():

    outbox, store, legacy_portrait, legacy_projection = _sunday(unified=True)

    assert outbox.send.await_count == 1

    (_runner, text), kwargs = outbox.send.await_args.args, outbox.send.await_args.kwargs

    assert kwargs["kind"] == "weekly_review"
    assert text.index("RESUMO DA SEMANA") < text.index("RETRATO") < text.index("PROJEÇÃO")
    assert "💡" in text                                       # a dica segue no rodapé
    # as duas mensagens separadas de antes NÃO saem mais
    legacy_portrait.assert_not_awaited()
    legacy_projection.assert_not_awaited()
    # o que foi mostrado fica gravado (pra só voltar com novidade)
    assert store.saved == [("renato2", SNAP, "2026-10-18")]


def test_unified_skips_the_projection_when_there_is_nothing_new():

    shown = _Shown(last={**SNAP, "date": "2026-10-11"})

    outbox, store, _, _ = _sunday(unified=True, shown=shown)

    text = outbox.send.await_args.args[1]

    assert "RETRATO" in text and "PROJEÇÃO" not in text
    assert store.saved == []                                  # nada novo, nada gravado


def test_flag_off_keeps_the_three_messages():
    """Regressão: sem a flag, o domingo é o de sempre (resumo + retrato + projeção)."""

    outbox, store, legacy_portrait, legacy_projection = _sunday(unified=False)

    # o resumo; retrato e projeção saem pelos métodos antigos (mocados)
    assert outbox.send.await_count == 1
    assert "PROJEÇÃO" not in outbox.send.await_args.args[1]
    legacy_portrait.assert_awaited_once()
    legacy_projection.assert_awaited_once()
    assert store.saved == []


def test_canary_other_athletes_keep_the_old_sunday():

    outbox, _, legacy_portrait, legacy_projection = _sunday(unified=True, profile="mauricio")

    assert "RETRATO" not in outbox.send.await_args.args[1]
    legacy_portrait.assert_awaited_once()
    legacy_projection.assert_awaited_once()


# ---- sem repetir a previsão e sem passar do fecho --------------------------------


def _goal():

    return TrainingGoal(
        name="15 km", distance_km=15.0, target_time="01:15:00",
        race_date=date(2026, 12, 20),
    )


_FRANK = {"formatted": "1:23:18", "seconds": 4998, "delta_seconds": 498}


def test_lean_projection_carries_only_the_verdict_not_the_repeated_numbers():
    """O resumo já diz 'se a prova fosse hoje: ~1:23:18 — faltam ~8:18': o 'rumo à
    meta' dentro dele leva só o que ninguém mais diz — o veredito franco."""

    with patch(
        "app.application.review.goal_projection_writer.RaceTimePredictor.predict_formatted",
        return_value=_FRANK,
    ):

        text, snap = GoalProjectionWriter.section(
            "Renato", _goal(), object(), weeks_to_race=9, lean=True,
        )

        full, _ = GoalProjectionWriter.section(
            "Renato", _goal(), object(), weeks_to_race=9, lean=False,
        )

    assert text.startswith("🎯 Rumo à meta (15 km)")
    assert "Sendo franco" in text and "alvo realista" in text
    # o que o resumo já mostra NÃO repete
    assert "1:23:18" not in text.split("alvo realista")[0]
    assert "Tua meta é" not in text and "Faltam 9 semanas" not in text
    assert "No teu nível atual" in full and "Tua meta é" in full   # o completo segue igual
    assert snap["seconds"] == 4998


def test_lean_projection_without_a_verdict_adds_nothing():
    """Sem tempo-alvo não há veredito: nada a acrescentar dentro do resumo."""

    no_target = TrainingGoal(name="15 km", distance_km=15.0, target_time=None, race_date=None)

    with patch(
        "app.application.review.goal_projection_writer.RaceTimePredictor.predict_formatted",
        return_value={"formatted": "1:23:18", "seconds": 4998, "delta_seconds": None},
    ):

        assert GoalProjectionWriter.section("R", no_target, object(), lean=True) is None


def test_gap_line_is_unchanged_by_the_split_into_numbers_and_verdict():
    base, verdict = GoalProjectionWriter._gap_parts(_goal(), _FRANK, 9)

    assert base.startswith("Tua meta é 01:15:00 — faltam ~")
    assert GoalProjectionWriter._gap_line(_goal(), _FRANK, 9) == f"{base} {verdict}"

    # já bateu a meta: só o veredito
    on_target = {"formatted": "1:14:00", "seconds": 4440, "delta_seconds": -60}

    assert GoalProjectionWriter._gap_parts(_goal(), on_target, 9)[0] is None


def test_sections_go_BEFORE_the_closing_line():

    review = (
        "📝 corpo do resumo\n\n🔥 Consistência: 58%\n\n"
        "Teu plano da próxima semana chega já já. Bora! 💪"
    )

    placed = WeeklyReviewNotifier._place_sections(review, ["📷 RETRATO", "🎯 META"])

    assert placed.index("Consistência") < placed.index("RETRATO") < placed.index("META")
    assert placed.index("META") < placed.index("Bora! 💪")
    assert placed.rstrip().endswith("Bora! 💪")

    # a outra despedida do resumo também
    other = "📝 corpo\n\nSegue firme na próxima — bora! 💪"

    assert WeeklyReviewNotifier._place_sections(other, ["📷 X"]).index("📷 X") < (
        WeeklyReviewNotifier._place_sections(other, ["📷 X"]).index("Segue firme")
    )

    # sem fecho reconhecível: vai ao final; sem seções: intacto
    assert WeeklyReviewNotifier._place_sections("só isto", ["📷 X"]) == "só isto\n\n📷 X"
    assert WeeklyReviewNotifier._place_sections("só isto", []) == "só isto"
