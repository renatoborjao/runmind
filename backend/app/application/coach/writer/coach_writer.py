import re

from app.application.coach.context.coach_context import (
    CoachContext,
)
from app.application.coach.models.coach_message import (
    CoachMessage,
)
from app.application.coach.models.coach_summary import (
    CoachSummary,
)
from app.application.coach.models.next_training import (
    NextTraining,
)
from app.application.coach.signals.finding import (
    Finding,
)
from app.application.coach.writer.labels import (
    intensity_label,
    plan_workout_label,
    workout_type_label,
)
from app.application.coach.signals.codes import (
    RecoveryStatus,
)
from app.application.coach.writer.phrasebook import (
    ALL_TEMPLATES,
    CLOSING_MODERATE_NEXT,
    CLOSING_MODERATE_WEEK_DONE,
    CLOSING_TEMPLATES,
    GREETING_TEMPLATE,
)
from app.application.planner.pace_formatter import (
    PaceFormatter,
)
from app.core.weekdays import (
    weekday_label,
    weekday_name,
)
from app.domain.entities.enriched_activity import (
    EnrichedActivity,
)
from app.domain.entities.planned_session import (
    PlannedSession,
)


class CoachWriter:

    @staticmethod
    def write(
        context: CoachContext,
        summary: CoachSummary,
    ) -> CoachMessage:

        return CoachMessage(
            greeting=CoachWriter._greeting(summary.runner_name),
            planned_lines=CoachWriter._planned_lines(
                context.planned,
                context.planned_date,
            ),
            executed_lines=CoachWriter._executed_lines(context.executed),
            interval_lines=CoachWriter._interval_lines(context.executed),
            splits_lines=CoachWriter._splits_lines(context.executed),
            positives=CoachWriter._render_all(summary.positives),
            improvements=CoachWriter._render_all(summary.improvements),
            history=CoachWriter._render_all(summary.history),
            recovery=CoachWriter._render_all(summary.recovery),
            next_training=CoachWriter._render_next_training(
                summary.next_training,
            ),
            closing=CoachWriter._closing(summary),
        )

    @staticmethod
    def _greeting(
        name: str,
    ) -> str:

        return GREETING_TEMPLATE.format(name=name)

    @staticmethod
    def _planned_lines(
        planned: PlannedSession | None,
        planned_date=None,
    ) -> list[str]:

        # treino extra: sem sessão planejada, a seção some da mensagem
        if planned is None:

            return []

        lines = []

        # dia + data da sessão planejada (deixa claro qual dia do plano
        # está sendo comparado — nada de se perder na data)
        if planned_date is not None:

            lines.append(
                f"{weekday_label(planned.day)} "
                f"({planned_date.strftime('%d/%m')})"
            )

        lines.append(
            plan_workout_label(
                planned.workout_type,
                planned.planned_distance_km,
            )
        )

        lines.append(f"{(planned.planned_distance_km or 0):.1f} km")

        return lines

    @staticmethod
    def _executed_lines(
        executed: EnrichedActivity,
    ) -> list[str]:
        """Ficha completa do treino: tudo que o Strava entrega, pra o
        atleta não precisar abrir o app pra ver os números."""

        activity = executed.activity

        distance = activity.distance / 1000

        start = activity.start_date

        raw = activity.raw or {}

        # na esteira, distância/pace vêm de estimativa do relógio — deixa
        # explícito pra não parecer erro nem cobrar diferença
        treadmill = " (esteira, estimada)" if executed.indoor else ""

        lines = [
            f"{weekday_label(weekday_name(start))} "
            f"({start.strftime('%d/%m')})",
            f"Distância: {distance:.2f} km{treadmill}",
            f"Tempo: {CoachWriter._duration(activity.moving_time)}",
            f"Ritmo médio: {PaceFormatter.format(executed.pace_min_km)} "
            f"min/km{treadmill}",
        ]

        # ritmo mais rápido no pico (do max_speed)
        if activity.max_speed and activity.max_speed > 0:

            best_pace = (1000 / activity.max_speed) / 60

            lines.append(
                f"Ritmo máximo: {PaceFormatter.format(best_pace)} min/km"
            )

        if activity.average_heartrate:

            hr = f"FC média: {int(activity.average_heartrate)}"

            if activity.max_heartrate:

                hr += f" · máx {int(activity.max_heartrate)}"

            lines.append(
                f"{hr} bpm ({executed.estimated_zone})"
            )

        structure = executed.structure

        if structure is not None and structure.cadence_spm:

            lines.append(f"Cadência: {structure.cadence_spm} ppm")

        if activity.elevation_gain:

            lines.append(f"Elevação: +{int(activity.elevation_gain)} m")

        calories = raw.get("calories")

        if calories:

            lines.append(f"Calorias: {int(calories)} kcal")

        if activity.suffer_score:

            lines.append(f"Esforço relativo: {int(activity.suffer_score)}")

        lines.append(
            f"Tipo identificado: {workout_type_label(executed.training_type)}"
        )

        lines.append(
            f"Intensidade: {intensity_label(executed.intensity)}"
        )

        return lines

    @staticmethod
    def _interval_lines(
        executed: EnrichedActivity,
    ) -> list[str]:
        """Tiros detectados no stream (rep a rep) + resposta de FC — o que
        os splits por km escondem num intervalado curto."""

        structure = executed.structure

        if structure is None or structure.interval is None:

            return []

        interval = structure.interval

        lines = [
            f"{interval.rep_count} tiros · "
            f"pace médio {PaceFormatter.format(interval.avg_rep_pace)} min/km",
        ]

        if interval.avg_peak_hr:

            hr = f"FC de pico média: {interval.avg_peak_hr} bpm"

            if interval.avg_recovery_hr:

                hr += f" · recuperação {interval.avg_recovery_hr} bpm"

            lines.append(hr)

        for index, rep in enumerate(interval.reps):

            # na esteira a distância do relógio não é confiável — mostra o
            # tiro por ritmo + FC, sem o metro enganoso
            if executed.indoor:

                line = f"Tiro {index + 1}: {PaceFormatter.format(rep['pace'])} min/km"

            else:

                line = (
                    f"Tiro {index + 1}: {rep['distance_m']} m · "
                    f"{PaceFormatter.format(rep['pace'])} min/km"
                )

            if rep.get("peak_hr"):

                line += f" · pico {rep['peak_hr']} bpm"

            lines.append(line)

        return lines

    @staticmethod
    def _splits_lines(
        executed: EnrichedActivity,
    ) -> list[str]:
        """Parciais km a km (pace + FC), como no Strava."""

        structure = executed.structure

        if structure is None or not structure.km_splits:

            return []

        lines = []

        for index, pace in enumerate(structure.km_splits):

            line = f"km {index + 1}: {PaceFormatter.format(pace)} min/km"

            hr = (
                structure.km_hr[index]
                if index < len(structure.km_hr)
                else None
            )

            if hr:

                line += f" · {hr} bpm"

            lines.append(line)

        return lines

    @staticmethod
    def _duration(
        seconds: int,
    ) -> str:
        """Segundos em H:MM:SS (ou M:SS quando menos de 1h)."""

        hours, rest = divmod(int(seconds), 3600)

        minutes, secs = divmod(rest, 60)

        if hours:

            return f"{hours}:{minutes:02d}:{secs:02d}"

        return f"{minutes}:{secs:02d}"

    @staticmethod
    def _render_all(
        findings: list[Finding],
    ) -> list[str]:

        lines = []

        for finding in findings:

            if finding is None:

                continue

            template = ALL_TEMPLATES.get(finding.code)

            if template is None:

                continue

            lines.append(
                template.format(**finding.params),
            )

        return lines

    @staticmethod
    def _render_next_training(
        next_training: NextTraining | None,
    ) -> list[str]:

        if next_training is None:

            return []

        lines = [
            f"Dia: {weekday_label(next_training.day)}",
            f"Tipo: {plan_workout_label(next_training.workout_type, next_training.distance_km)}",
        ]

        # objetivo só quando AGREGA — não quando só repete o tipo
        objective = (next_training.objective or "").strip()

        if objective and objective not in ("-", next_training.workout_type):

            lines.append(f"Objetivo: {objective}")

        if next_training.distance_km:

            lines.append(
                f"Distância: {next_training.distance_km:.1f} km",
            )

        if next_training.pace != "-":

            lines.append(f"Pace: {next_training.pace}")

        # nota do treinador externo: vem como texto cru (markdown, rótulos,
        # ruído). Limpa e quebra em passos legíveis.
        lines += CoachWriter._coach_notes_lines(next_training.notes)

        return lines

    # rótulos redundantes no começo de cada passo do plano do treinador
    _NOTE_LABEL = re.compile(
        r"^(descri[çc][aã]o|obs|observa[çc][aã]o|s[ée]ries?)\s*:\s*",
        re.IGNORECASE,
    )

    # linhas sem valor pro atleta (começo, minúsculas, sem espaços)
    _NOTE_NOISE = (
        "percurso: livre",
    )

    @staticmethod
    def _coach_notes_lines(
        notes: str,
    ) -> list[str]:
        """Transforma a nota crua do plano do treinador (markdown, rótulos,
        bullets bagunçados) numa lista de passos limpos."""

        if not notes or notes.strip() in ("", "-"):

            return []

        # tira negrito de markdown
        text = notes.replace("*", " ")

        steps = []

        # quebra por linha e por bullet cru
        for chunk in re.split(r"[\n•]+", text):

            step = " ".join(chunk.split())

            if not step:

                continue

            # remove rótulo redundante do começo (Descrição:, OBS:, Séries:)
            step = CoachWriter._NOTE_LABEL.sub("", step).strip()

            if not step:

                continue

            if step.lower().startswith(CoachWriter._NOTE_NOISE):

                continue

            steps.append(step)

        if not steps:

            return []

        return ["Do treinador:"] + steps

    @staticmethod
    def _closing(
        summary: CoachSummary,
    ) -> str:

        if not summary.recovery:

            return ""

        recovery_finding = summary.recovery[0]

        # Recuperação moderada: o fechamento depende de haver um próximo
        # treino no plano. Sem ele (semana concluída), não fala em "amanhã".
        if recovery_finding.code == RecoveryStatus.MODERATE.value:

            next_day = recovery_finding.params.get("next_day")

            if next_day:

                return CLOSING_MODERATE_NEXT.format(next_day=next_day)

            return CLOSING_MODERATE_WEEK_DONE

        return CLOSING_TEMPLATES.get(recovery_finding.code, "")
