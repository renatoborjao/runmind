"""CONTEXTO DO DIA pro post-mortem do treino: a CONDIÇÃO do atleta quando ele fez
a sessão — sono da noite anterior, prontidão, corpo/carga. Sem isto, a análise vê
"não bateu os paces" mas não o PORQUÊ; com isto, o coach conecta o resultado à
causa e reenquadra ("não é forma perdida, você dormiu 5h e vinha em carga alta").
Best-effort e compacto: só entra o que existir; atleta sem Garmin não gera nada.
Ver [[project_analise_treino_hibrida]] e [[project_analise_corpo_garmin]]."""

from datetime import date

from app.domain.entities.body_reading import (
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
)

# noite abaixo disso é sono CURTO — candidato forte a explicar um treino fraco
_SHORT_SLEEP_H = 6.0

# stress médio do dia a partir do qual vale mencionar (0-100 do Garmin)
_HIGH_STRESS = 50

# estados de corpo que EXPLICAM um treino abaixo do esperado (os "de atenção");
# corpo bom não é desculpa pra treino ruim, então não entra
_ATTENTION_STATES = {
    BODY_STRAINED: "sobrecarregado (carga alta + recuperação caindo)",
    BODY_RECOVERY_FLAG: "com recuperação em queda",
}


class DayContextReader:

    @staticmethod
    def facts(profile: str, activity_date: date) -> str:
        """Linha compacta com a condição do atleta no dia do treino. Vazio
        quando não há nada (sem Garmin / sem dado). Best-effort — nunca
        derruba a análise."""

        parts: list[str] = []

        DayContextReader._acute(profile, activity_date, parts)

        DayContextReader._accumulated(profile, parts)

        if not parts:

            return ""

        return (
            "CONTEXTO DO DIA (condição do atleta quando fez ESTE treino): "
            + "; ".join(parts)
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _acute(profile: str, activity_date: date, parts: list[str]) -> None:
        """Prontidão AGUDA do dia: sono da noite anterior, nível de prontidão,
        stress — do retrato diário do Garmin daquela data."""

        try:

            from app.infrastructure.persistence.garmin_health_repository import (
                GarminHealthRepository,
            )

            iso = activity_date.isoformat()

            health = next(
                (
                    h
                    for h in GarminHealthRepository().load(profile)
                    if h.date == iso
                ),
                None,
            )

            if health is None:

                return

            if health.sleep_hours is not None:

                tag = " (CURTO)" if health.sleep_hours < _SHORT_SLEEP_H else ""

                parts.append(
                    f"sono na noite anterior {health.sleep_hours:.1f}h{tag}"
                )

            if health.readiness_level:

                parts.append(f"prontidão do dia {health.readiness_level.lower()}")

            if health.stress_avg is not None and health.stress_avg >= _HIGH_STRESS:

                parts.append(f"stress do dia alto ({health.stress_avg})")

        except Exception as e:

            print(f"Contexto agudo do dia falhou p/ '{profile}': {e}")

    @staticmethod
    def _accumulated(profile: str, parts: list[str]) -> None:
        """Estado ACUMULADO: corpo em atenção (sobrecarga/recuperação caindo) e
        carga de bloco longo — o que o retrato de UM dia não mostra."""

        try:

            from app.application.coach.intelligence.body_reading_service import (
                BodyReadingService,
            )
            from app.application.history.deload_analyzer import DeloadAnalyzer

            reading, _ = BodyReadingService.read(profile, persist=False)

            state = _ATTENTION_STATES.get(reading.body_state)

            if state:

                parts.append(f"corpo {state}")

            decision = DeloadAnalyzer.assess(
                reading.load.weekly_loads, reading.recovery
            )

            if decision.due:

                parts.append(f"carga acumulada ({decision.reason})")

        except Exception as e:

            print(f"Contexto acumulado do dia falhou p/ '{profile}': {e}")
