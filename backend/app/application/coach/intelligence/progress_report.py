"""'Como eu evoluí?' sob demanda — o VOCÊ vs VOCÊ com arco LONGO (meses): o
melhor esforço de quando começou vs agora, traduzido em ritmo, + a jornada de
km. Torna a evolução VISÍVEL = motivação. Determinístico, reusa o VDOT (a mesma
fonte do plano/zonas). Distinto do 'estou evoluindo?' (tendência curta ~8sem):
aqui é o retrospecto do arco inteiro. Ver [[project_modelo_pace_vdot]]."""

from datetime import timedelta

from app.application.history.pace_model_builder import PaceModelBuilder
from app.application.history.vdot_calculator import (
    FRAC_THRESHOLD,
    VdotCalculator,
)
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)

# janela de comparação em cada ponta (o mês inicial vs o mês atual)
_WINDOW = 28

# arco mínimo (dias) entre o 1º e o último treino pra valer "você vs você"
_MIN_SPAN = 56


class ProgressReport:

    @staticmethod
    def build(profile: str) -> str | None:

        activities = ActivityArchiveRepository().load_activities(profile)

        runs = sorted(
            (a for a in activities if is_run_sport(a.sport) and a.average_speed > 0),
            key=lambda a: a.start_date,
        )

        if len(runs) < 4:

            return None

        first_day = runs[0].start_date.date()

        last_day = runs[-1].start_date.date()

        span = (last_day - first_day).days

        lines: list[str] = []

        # VOCÊ vs VOCÊ (só com arco de verdade): VDOT do 1º mês vs o do mês atual
        if span >= _MIN_SPAN:

            then_vdot = ProgressReport._window_vdot(
                runs, first_day, first_day + timedelta(days=_WINDOW)
            )

            now_vdot = ProgressReport._window_vdot(
                runs, last_day - timedelta(days=_WINDOW), last_day
            )

            gain = ProgressReport._pace_gain(then_vdot, now_vdot)

            if gain is not None and gain > 0:

                months = max(1, round(span / 30))

                lines.append(
                    f"Há ~{months} {'mês' if months == 1 else 'meses'}, no "
                    "mesmo esforço, você corria mais devagar. Hoje você está "
                    f"~{gain}s/km MAIS RÁPIDO no mesmo esforço. 🚀"
                )

        # a JORNADA de km (sempre que há histórico)
        stats = ActivityArchiveRepository().stats(profile)

        if stats:

            first = stats["first_date"]

            when = f"{first[5:7]}/{first[:4]}"

            lines.append(
                f"Desde {when} você já somou "
                f"{stats['total_km']:.0f} km em {stats['total_runs']} treinos — "
                f"maior treino: {stats['longest_km']:.1f} km."
            )

        if not lines:

            return None

        header = "📈 Seu progresso — você vs você"

        closing = "Isso é evolução de verdade, construída teimosia por teimosia. 👊"

        return "\n\n".join([header, *lines, closing])

    # ------------------------------------------------------------------

    @staticmethod
    def _window_vdot(runs, start, end) -> float | None:
        """Melhor VDOT das corridas na janela [start, end] — reusa o
        PaceModelBuilder (mesma âncora do plano/zonas)."""

        subset = [a for a in runs if start <= a.start_date.date() <= end]

        if not subset:

            return None

        return PaceModelBuilder.build(TrainingHistory(activities=subset)).vdot

    @staticmethod
    def _pace_gain(then_vdot, now_vdot) -> int | None:
        """Ganho em s/km no ritmo de limiar (mesmo esforço), do 'antes' pro
        'agora'. None se faltar uma das pontas."""

        if then_vdot is None or now_vdot is None:

            return None

        pace_then = VdotCalculator.pace_min_km(then_vdot, FRAC_THRESHOLD)

        pace_now = VdotCalculator.pace_min_km(now_vdot, FRAC_THRESHOLD)

        return round((pace_then - pace_now) * 60)
