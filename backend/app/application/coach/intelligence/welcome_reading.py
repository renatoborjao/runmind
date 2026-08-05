"""Leitura de boas-vindas — a PRIMEIRA impressão do coach.

Quando o atleta conecta o Strava, em vez de só "plano pronto", o coach mostra
que ESTUDOU ele: revela 2-4 coisas específicas e não-óbvias sobre o próprio
treino dele (ritmo real, forma atual traduzida em prova, evolução, padrão de
dias, salto de carga) e emenda no plano. É o momento "esse coach me vê".

Regras de produto:
- TUDO ancorado em número REAL do histórico — zero invenção (a 1ª impressão é
  onde a confiança nasce ou morre). Determinístico, sem IA, sem custo.
- Só dispara se houver sinal de verdade (histórico mínimo); pouco dado =
  silêncio, não uma leitura genérica que entregaria o contrário do "me vê".
- Uma vez por atleta (DispatchGuard). Onboarding e late-connector compartilham
  a trava — quem chegar primeiro manda, o outro cala.

Ver [[project_ideias_produto]] (ativação) e [[feedback_melhor_solucao_primeiro]]."""

from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.history.race_time_predictor import RaceTimePredictor
from app.application.history.runner_metrics import (
    RUN_MIN_DISTANCE_KM,
    WALK_PACE_CUTOFF,
    RunnerMetricsBuilder,
)
from app.application.history.vdot_calculator import (
    FRAC_THRESHOLD,
    VdotCalculator,
)
from app.application.history.weekly_volume_analyzer import WeeklyVolumeAnalyzer
from app.application.planner.race_time_formatter import RaceTimeFormatter
from app.application.use_cases.build_training_goal import BuildTrainingGoal
from app.core.clock import today_local
from app.core.weekdays import weekday_label, weekday_name
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.persistence.dispatch_guard import DispatchGuard

_KIND = "welcome_reading"

# histórico mínimo pra uma leitura que impressione com honestidade
_MIN_RUNS = 4

# insights mínimos (além da abertura) pra valer a pena enviar
_MIN_INSIGHTS = 2

# distâncias oficiais nomeadas
_HALF = 21.0975
_FULL = 42.195

# arco mínimo (dias) pra afirmar "você evoluiu" (você vs você)
_MIN_SPAN = 56
_WINDOW = 28

# salto de volume na última semana que já merece um aviso de coach
_RAMP_JUMP = 1.5

# concentração de dias pra afirmar um padrão ("você quase sempre corre X")
_DAY_CONCENTRATION = 0.6
_MAX_PATTERN_DAYS = 3


class WelcomeReading:

    @staticmethod
    def once(
        profile: str,
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str | None:
        """Leitura de boas-vindas UMA vez por atleta. None se já enviada ou
        se não há sinal suficiente (nesse caso NÃO marca — deixa uma próxima
        conexão, com mais histórico, tentar de novo)."""

        if DispatchGuard.already_sent(_KIND, profile, "v1"):

            return None

        message = WelcomeReading.build(runner, history)

        if message is None:

            return None

        DispatchGuard.mark(_KIND, profile, "v1")

        return message

    @staticmethod
    def build(
        runner: RunnerProfile,
        history: TrainingHistory,
    ) -> str | None:
        """Conteúdo puro da leitura (sem I/O nem trava) — fácil de testar."""

        runs = WelcomeReading._runs(history)

        if len(runs) < _MIN_RUNS:

            return None

        insights: list[str] = []

        WelcomeReading._add_fitness(insights, runner, history)

        WelcomeReading._add_volume(insights, runner, history, runs)

        WelcomeReading._add_progress(insights, runs)

        WelcomeReading._add_day_pattern(insights, runs)

        WelcomeReading._add_load_watchout(insights, history)

        if len(insights) < _MIN_INSIGHTS:

            return None

        # no máximo 4 — leitura densa demais vira ruído
        bullets = "\n".join(f"• {line}" for line in insights[:4])

        return (
            f"🔎 Antes do plano, {runner.name}, dei uma boa olhada no seu "
            "histórico de corridas — e já vi umas coisas sobre você:\n\n"
            f"{bullets}\n\n"
            "É em cima disso — o SEU ponto real, não um plano genérico — "
            "que montei sua semana. 👇"
        )

    # ==================================================================
    # insights (cada um só entra se tiver sinal REAL)
    # ==================================================================

    @staticmethod
    def _add_fitness(insights, runner, history) -> None:
        """Forma atual traduzida em prova — o "ponto de partida" tangível.
        Usa a distância da meta; se a extrapolação não fecha, tenta 10k e 5k."""

        goal = BuildTrainingGoal.execute(runner)

        for dist in WelcomeReading._distance_candidates(goal.distance_km):

            prediction = RaceTimePredictor.predict(history, dist)

            if prediction is None:

                continue

            time = RaceTimeFormatter.format(prediction["predicted_seconds"])

            insights.append(
                f"Pelo seu ritmo atual, hoje você cruzaria "
                f"{WelcomeReading._dist_label(dist)} em torno de {time} — "
                "esse é seu ponto de partida real, e é daqui que a gente sobe."
            )

            return

    @staticmethod
    def _add_volume(insights, runner, history, runs) -> None:
        """Volume semanal + frequência recente + maior treino — o retrato do
        ritmo de treino dele, que ele mesmo talvez não tenha em número."""

        metrics = RunnerMetricsBuilder.build(history, runner)

        volume = metrics.weekly_volume

        if not volume:

            return

        per_week = WelcomeReading._runs_per_week(runs)

        freq = (
            f", em cerca de {per_week} corridas por semana"
            if per_week
            else ""
        )

        line = f"Você roda em média ~{volume:.0f} km por semana{freq}"

        longest = metrics.max_long_run

        if longest:

            line += f"; seu treino mais longo foi {longest:.0f} km"

        insights.append(line + ".")

    @staticmethod
    def _add_progress(insights, runs) -> None:
        """Você vs você: no mesmo esforço, ficou mais rápido ao longo dos
        meses (VDOT do 1º mês vs o do mês atual). Só com arco de verdade."""

        first = runs[0].start_date.date()

        last = runs[-1].start_date.date()

        if (last - first).days < _MIN_SPAN:

            return

        import datetime

        then = WelcomeReading._window_vdot(
            runs, first, first + datetime.timedelta(days=_WINDOW)
        )

        now = WelcomeReading._window_vdot(
            runs, last - datetime.timedelta(days=_WINDOW), last
        )

        if then is None or now is None:

            return

        gain = round(
            (
                VdotCalculator.pace_min_km(then, FRAC_THRESHOLD)
                - VdotCalculator.pace_min_km(now, FRAC_THRESHOLD)
            )
            * 60
        )

        if gain <= 0:

            return

        insights.append(
            f"E você não está parado: no mesmo esforço, está ~{gain}s/km "
            "mais rápido do que uns meses atrás. 🚀"
        )

    @staticmethod
    def _add_day_pattern(insights, runs) -> None:
        """Padrão de dias — "você quase sempre corre ter/qui/sáb". Só quando
        é REALMENTE concentrado (senão vira palpite que quebra a confiança)."""

        counts: dict[str, int] = {}

        for run in runs:

            day = WelcomeReading._weekday_name(run)

            counts[day] = counts.get(day, 0) + 1

        if not counts:

            return

        top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)

        top_days = [d for d, _ in top[:_MAX_PATTERN_DAYS]]

        covered = sum(c for _, c in top[:_MAX_PATTERN_DAYS])

        if covered / len(runs) < _DAY_CONCENTRATION:

            return

        labels = [weekday_label(d) for d in top_days]

        joined = (
            " e ".join(labels)
            if len(labels) <= 2
            else ", ".join(labels[:-1]) + " e " + labels[-1]
        )

        insights.append(f"Notei que você quase sempre corre em {joined}.")

    @staticmethod
    def _add_load_watchout(insights, history) -> None:
        """Aviso de coach: a última semana deu um salto de volume — sinaliza
        que vou construir com segurança (mostra que o coach PROTEGE)."""

        weekly = WeeklyVolumeAnalyzer.analyze(history)

        last = weekly["last_week"]

        avg = weekly["average_4_weeks"]

        if avg > 0 and last >= avg * _RAMP_JUMP:

            insights.append(
                "Só de olho: seu volume deu um salto na última semana — vou "
                "construir a subida com segurança pra te proteger de lesão."
            )

    # ==================================================================
    # helpers
    # ==================================================================

    @staticmethod
    def _runs(history: TrainingHistory) -> list:
        """Corridas de verdade, em ordem cronológica (fragmento/caminhada
        fora — não representam o atleta)."""

        runs = [
            a
            for a in history.activities
            if is_run_sport(a.sport)
            and a.average_speed > 0
            and a.distance / 1000 >= RUN_MIN_DISTANCE_KM
            and (1000 / a.average_speed) / 60 <= WALK_PACE_CUTOFF
        ]

        return sorted(runs, key=lambda a: a.start_date)

    @staticmethod
    def _runs_per_week(runs) -> int:
        """Frequência RECENTE (corridas nos últimos 28 dias / 4). 0 se o
        atleta não correu recentemente (aí a linha de frequência some)."""

        cutoff = today_local()

        recent = sum(
            1 for a in runs if (cutoff - a.start_date.date()).days <= 28
        )

        return round(recent / 4) if recent >= 4 else 0

    @staticmethod
    def _window_vdot(runs, start, end) -> float | None:
        """Melhor VDOT das corridas na janela [start, end] — mesma âncora do
        plano/zonas (PaceModelBuilder), sem drift."""

        subset = [a for a in runs if start <= a.start_date.date() <= end]

        if not subset:

            return None

        return PaceModelBuilder.build(TrainingHistory(activities=subset)).vdot

    @staticmethod
    def _weekday_name(activity) -> str:
        """Dia da semana no padrão interno (inglês, chave do weekday_label),
        da hora LOCAL do atleta quando o Strava a trouxe (start_date_local) —
        senão do start_date. Usa weekday_name (via .weekday()), que INDEPENDE
        do locale do Windows; strftime('%A') sairia traduzido em pt-BR."""

        raw = activity.raw or {}

        local = raw.get("start_date_local")

        if isinstance(local, str) and len(local) >= 10:

            try:

                from datetime import datetime

                return weekday_name(
                    datetime.fromisoformat(local.replace("Z", ""))
                )

            except ValueError:

                pass

        return weekday_name(activity.start_date)

    @staticmethod
    def _distance_candidates(goal_km: float) -> list[float]:
        """Distância da meta primeiro; depois 10k e 5k como alternativas
        quando a extrapolação da meta não é confiável."""

        candidates = [goal_km]

        for fallback in (10.0, 5.0):

            if fallback not in candidates:

                candidates.append(fallback)

        return candidates

    @staticmethod
    def _dist_label(km: float) -> str:

        if abs(km - _HALF) < 0.5:

            return "uma meia maratona"

        if abs(km - _FULL) < 0.5:

            return "uma maratona"

        return f"{km:.0f} km"
