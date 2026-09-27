"""Guarda de QUALIDADE do plano gerado pela IA — regras objetivas de treinador
que o prompt sozinho não garantiu (auditoria de 26/09 nos planos reais):

1. ORÇAMENTO DE QUALIDADE pela frequência: quem corre até 3x/semana tem no
   máximo UMA sessão forte (e o longão com blocos/progressão CONTA como forte).
   O renato2 vinha com 2 de 3 sessões fortes toda semana (tiro + longão
   "misto/progressivo") — somado ao leve saindo em zona cinzenta, virou fadiga
   crônica.
2. PACE PELA CAPACIDADE ATUAL: nenhum bloco sustentado mais rápido que o
   limiar ATUAL, nenhum tiro médio mais rápido que o VO2 ATUAL. O plano ancorava
   na META: "Longão Misto" com blocos a 5:05 com o limiar em 5:29 (cortou o
   treino), progressivo a 5:25-5:40 no fim de 14,5 km (não saiu).

Não reescreve nada: devolve as violações em texto pra IA CORRIGIR (uma vez),
assim o texto do treino e os passos do relógio seguem coerentes. Puro."""

from app.application.history.stimulus_ledger import (
    FARTLEK,
    HILLS,
    LONG,
    PROGRESSION,
    RACE_PACE,
    THRESHOLD,
    VO2,
    StimulusLedger,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.runner_metrics import RunnerMetrics
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import INTERVAL, RUN, parse_steps

_QUALITY = {THRESHOLD, VO2, FARTLEK, HILLS, RACE_PACE, PROGRESSION}

_LONG_QUALITY_CUES = ("progress", "misto", "bloco", "final", "ritmo", "prova")

# folga (min/km) antes de acusar "mais rápido que a capacidade" (~5 s/km)
_SLACK = 5 / 60

# bloco SUSTENTADO (limiar): ≥ 1,6 km ou ≥ 8 min
_SUSTAINED_M = 1600
_SUSTAINED_SEC = 8 * 60

# tiro MÉDIO (VO2): ≥ 400 m ou ≥ 90 s — abaixo disso é aceleração/sprint, que
# PODE ser mais rápido que o VO2 (neuromuscular)
_REP_M = 400
_REP_SEC = 90

_RUNNING_KINDS = ("run", "walk", "run_walk")


class PlanGuard:

    @staticmethod
    def quality_budget(running_sessions: int, body_green: bool = False) -> int:
        """Teto de sessões fortes. Com o corpo EM ALERTA (recuperação em queda,
        sobrecarga) é o teto de proteção: ≤3 corridas → 1, 4+ → 2. Com o corpo
        VERDE (absorvendo bem) sobe um degrau — aí quem decide se cabem 2 fortes
        em 3 corridas é a IA, pela meta/fase; a regra fixa só protege quando o
        corpo pede."""

        base = 1 if running_sessions <= 3 else 2

        return base + 1 if body_green else base

    @staticmethod
    def violations(
        plan: TrainingPlan,
        metrics: RunnerMetrics | None,
        real_weekly_km: float | None = None,
        allow_reduction: bool = False,
        body_green: bool = False,
    ) -> list[str]:
        """Violações objetivas do plano, em frases prontas pra IA corrigir.
        Lista vazia = plano dentro das regras. `real_weekly_km` = o que o
        atleta de fato corre por semana; `allow_reduction` = há motivo real pra
        cortar volume (sobrecarga/descarga, polimento de prova)."""

        running = [
            s for s in plan.sessions
            if getattr(s, "kind", "run") in _RUNNING_KINDS
        ]

        issues: list[str] = []

        quality = [
            s for s in running if PlanGuard._is_quality(s.workout_type)
        ]

        budget = PlanGuard.quality_budget(len(running), body_green)

        if len(quality) > budget:

            names = ", ".join(
                f"{s.day} ({s.workout_type})" for s in quality
            )

            issues.append(
                f"{len(quality)} sessões FORTES numa semana de {len(running)} "
                f"corridas: {names}. O orçamento é {budget}: mantenha a que "
                "mais serve à meta/fase e transforme as outras em leve de "
                "verdade (longão CONSTANTE, sem blocos fortes)."
            )

        if metrics is not None:

            issues += PlanGuard._pace_issues(running, metrics)

        issue = PlanGuard._volume_issue(
            running, metrics, real_weekly_km, allow_reduction,
        )

        if issue:

            issues.append(issue)

        return issues

    @staticmethod
    def planned_km(sessions, metrics: RunnerMetrics | None) -> float:
        """Volume do plano: km prescritos + sessões por TEMPO estimadas no
        pace fácil (o grosso do tempo de uma sessão por tempo é leve)."""

        easy = (
            (metrics.easy_pace_min + metrics.easy_pace_max) / 2
            if metrics is not None and metrics.easy_pace_min else 6.5
        )

        total = 0.0

        for session in sessions:

            if session.planned_distance_km:

                total += session.planned_distance_km

            elif session.planned_duration_minutes:

                total += session.planned_duration_minutes / easy

        return total

    @staticmethod
    def _volume_issue(sessions, metrics, real_weekly_km, allow_reduction) -> str | None:
        """Plano descolado do que o atleta CORRE (auditoria 26/09: Fernanda
        corre ~22 km/sem e recebia ~14 km, com o longão tirado)."""

        if not real_weekly_km or real_weekly_km < 8:

            return None

        planned = PlanGuard.planned_km(sessions, metrics)

        if planned <= 0:

            return None

        ratio = planned / real_weekly_km

        if ratio < 0.7 and not allow_reduction:

            return (
                f"O plano soma ~{planned:.0f} km, bem abaixo do que ele corre "
                f"de verdade (~{real_weekly_km:.0f} km/sem). Dimensione perto da "
                "realidade (~0,9× a 1,1×) — SEGURAR é manter o volume, não "
                "cortar; corte forte só com sobrecarga, lesão ou polimento de "
                "prova. Se ele gosta/pediu longão, o longão fica."
            )

        if ratio > 1.2:

            return (
                f"O plano soma ~{planned:.0f} km — salto de "
                f"{(ratio - 1) * 100:.0f}% sobre o que ele sustenta "
                f"(~{real_weekly_km:.0f} km/sem). Progressão de até ~10% por "
                "semana."
            )

        return None

    @staticmethod
    def correction_block(issues: list[str]) -> str:

        lines = "\n".join(f"- {issue}" for issue in issues)

        return (
            "\n\nCORREÇÕES OBRIGATÓRIAS — a versão anterior deste plano violou "
            "regras de treinador; gere o plano de novo corrigindo TODAS "
            "(ajuste texto E passos, coerentes):\n" + lines
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _is_quality(workout_type: str) -> bool:

        family = StimulusLedger.classify(workout_type)

        if family in _QUALITY:

            return True

        if family == LONG:

            norm = StimulusLedger._normalize(workout_type)

            return any(cue in norm for cue in _LONG_QUALITY_CUES)

        return False

    @staticmethod
    def _pace_issues(sessions, metrics: RunnerMetrics) -> list[str]:

        issues = []

        threshold = metrics.threshold_pace

        vo2 = metrics.vo2_pace

        for session in sessions:

            raw = session.steps or []

            # passos já hidratados (WorkoutStep) no plano; dicts crus em teste
            steps = raw if raw and not isinstance(raw[0], dict) else parse_steps(raw)

            for step in PlanGuard._leaves(steps):

                if step.kind not in (INTERVAL, RUN) or not step.pace_min:

                    continue

                pace = PlanGuard._to_min(step.pace_min)

                if pace is None:

                    continue

                length = step.distance_m or 0

                duration = step.duration_sec or 0

                sustained = length >= _SUSTAINED_M or duration >= _SUSTAINED_SEC

                rep = length >= _REP_M or duration >= _REP_SEC

                if sustained and threshold and pace < threshold - _SLACK:

                    issues.append(
                        f"{session.day} ({session.workout_type}): bloco "
                        f"sustentado a {step.pace_min}/km — mais rápido que o "
                        f"LIMIAR ATUAL dele ({PaceFormatter.format(threshold)}"
                        "/km). Bloco longo não passa do limiar de hoje; a meta "
                        "dá a direção, o degrau sai do que ele sustenta."
                    )

                    break

                if rep and not sustained and vo2 and pace < vo2 - _SLACK:

                    issues.append(
                        f"{session.day} ({session.workout_type}): tiro a "
                        f"{step.pace_min}/km — mais rápido que o VO2 ATUAL dele "
                        f"({PaceFormatter.format(vo2)}/km). Tiros de 400 m+ "
                        "ficam no VO2 de hoje (só acelerações curtas passam)."
                    )

                    break

        return issues

    @staticmethod
    def _leaves(steps):
        """Passos executáveis, abrindo os grupos de repetição."""

        for step in steps:

            if step.is_repeat:

                yield from PlanGuard._leaves(step.steps)

            else:

                yield step

    @staticmethod
    def _to_min(text: str) -> float | None:

        try:

            minutes, seconds = str(text).strip().split(":")[:2]

            return int(minutes) + int(seconds) / 60

        except (ValueError, TypeError):

            return None
