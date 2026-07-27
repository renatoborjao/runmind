"""Vigia de prontidão — a decisão de conduta do dia a partir do corpo.

Traduz o `body_state` (carga à luz da recuperação, já computado pelo
BodyReadingService) + a exigência do treino de HOJE num veredito de conduta:
freia / atenção / sinal verde / nada. É PURO e determinístico — custo zero,
sem IA, sem I/O. A camada de cima (o notifier) decide se ENVIA, com dedup por
mudança de estado e no horário local. Ver [[project_analise_corpo_garmin]].
"""

from app.domain.entities.body_reading import (
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RISING,
    BodyReading,
)
from app.domain.entities.readiness_verdict import (
    READINESS_BRAKE,
    READINESS_CAUTION,
    READINESS_GREEN,
    READINESS_NEUTRAL,
    ReadinessVerdict,
)

# Exigência do treino de HOJE — quem chama resolve do plano; o avaliador só a lê.
DEMAND_DEMANDING = "demanding"   # tiro/longão/limiar — puxado
DEMAND_EASY = "easy"             # rodagem leve/regenerativo
DEMAND_REST = "rest"             # descanso previsto
DEMAND_UNKNOWN = "unknown"       # sem plano casável pra hoje


class ReadinessEvaluator:

    @staticmethod
    def evaluate(
        reading: BodyReading,
        todays_demand: str = DEMAND_UNKNOWN,
    ) -> ReadinessVerdict:

        state = reading.body_state
        limiter = reading.limiter

        # sem histórico de carga / sem dado de recuperação → sem veredito
        if state == BODY_BUILDING or not reading.recovery.has_data:

            return ReadinessVerdict(
                tier=READINESS_NEUTRAL,
                reason="sem leitura de corpo suficiente ainda",
                should_speak=False,
                body_state=state,
                limiter=limiter,
            )

        if state == BODY_STRAINED:

            # sobrecarga real: vale segurar HOJE — a menos que hoje já seja
            # descanso (nesse caso não há o que ajustar)
            return ReadinessVerdict(
                tier=READINESS_BRAKE,
                reason=ReadinessEvaluator._brake_reason(reading),
                should_speak=todays_demand != DEMAND_REST,
                body_state=state,
                limiter=limiter,
                signals=ReadinessEvaluator._concern_phrases(reading),
            )

        if state == BODY_RECOVERY_FLAG:

            # recuperação caindo com carga ok: só cutuca se hoje é puxado
            # (num dia leve/descanso não há decisão a tomar)
            return ReadinessVerdict(
                tier=READINESS_CAUTION,
                reason=ReadinessEvaluator._caution_reason(reading),
                should_speak=todays_demand == DEMAND_DEMANDING,
                body_state=state,
                limiter=limiter,
                signals=ReadinessEvaluator._concern_phrases(reading),
            )

        if state == BODY_FRESH:

            # recuperado e com espaço: só vale dizer se hoje é puxado (dá o
            # aval); num dia leve/descanso um "pode puxar" seria ruído
            return ReadinessVerdict(
                tier=READINESS_GREEN,
                reason="recuperado e com espaço pra puxar",
                should_speak=todays_demand == DEMAND_DEMANDING,
                body_state=state,
                limiter=limiter,
                signals=ReadinessEvaluator._green_phrases(reading),
            )

        # BALANCED / ABSORBING: está tudo no lugar — o coach fica quieto
        return ReadinessVerdict(
            tier=READINESS_NEUTRAL,
            reason="carga e recuperação em equilíbrio",
            should_speak=False,
            body_state=state,
            limiter=limiter,
        )

    @staticmethod
    def _brake_reason(reading: BodyReading) -> str:

        parts = ["corpo sobrecarregado"]

        if reading.limiter:

            parts.append(f"limitador: {reading.limiter}")

        parts.extend(ReadinessEvaluator._recovery_flags(reading))

        return "; ".join(parts)

    @staticmethod
    def _caution_reason(reading: BodyReading) -> str:

        parts = ["recuperação em queda"]

        if reading.limiter:

            parts.append(f"limitador: {reading.limiter}")

        parts.extend(ReadinessEvaluator._recovery_flags(reading))

        return "; ".join(parts)

    @staticmethod
    def _concern_phrases(reading: BodyReading) -> tuple[str, ...]:
        """Sinais de ALERTA em linguagem de gente — é o que o coach fala pra
        narrar o porquê ('seu HRV vem caindo', '2 noites curtas essa semana').
        Ordem: o mais 'sentido' primeiro (sono), depois HRV, depois FC."""

        rec = reading.recovery
        phrases: list[str] = []

        if rec.short_nights and rec.nights_counted:

            if rec.short_nights == 1:

                phrases.append("você teve uma noite curta essa semana")

            else:

                phrases.append(
                    f"você teve {rec.short_nights} noites curtas essa semana"
                )

        if rec.hrv_direction == FALLING and rec.hrv_recent is not None:

            phrases.append("seu HRV vem caindo")

        if rec.rhr_direction == RISING and rec.rhr_recent is not None:

            phrases.append("sua FC de repouso subiu um pouco")

        # nada concreto capturado, mas há um limitador nomeado: fala dele
        if not phrases and reading.limiter:

            phrases.append(f"o {reading.limiter} tá pesando na recuperação")

        return tuple(phrases)

    @staticmethod
    def _green_phrases(reading: BodyReading) -> tuple[str, ...]:
        """Sinais POSITIVOS pro sinal verde ('seu HRV tá firme', 'você vem
        dormindo bem'). Vazio quando não há nada marcante a destacar."""

        rec = reading.recovery
        phrases: list[str] = []

        if rec.hrv_direction == RISING and rec.hrv_recent is not None:

            phrases.append("seu HRV vem subindo")

        if rec.nights_counted and not rec.short_nights:

            phrases.append("você vem dormindo bem")

        return tuple(phrases)

    @staticmethod
    def _recovery_flags(reading: BodyReading) -> list[str]:
        """Sinais concretos que sustentam o veredito (pro texto e pro debug)."""

        rec = reading.recovery
        flags: list[str] = []

        if rec.hrv_direction == FALLING and rec.hrv_recent is not None:

            flags.append(f"HRV caindo ({rec.hrv_recent:.0f})")

        if rec.rhr_direction == RISING and rec.rhr_recent is not None:

            flags.append(f"FC de repouso subindo ({rec.rhr_recent})")

        if rec.short_nights and rec.nights_counted:

            flags.append(f"{rec.short_nights} de {rec.nights_counted} noites < 6h")

        return flags
