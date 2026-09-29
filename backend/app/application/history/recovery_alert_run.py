"""Há quanto tempo o corpo está em alerta — derivado da SÉRIE de saúde do Garmin
com a régua ATUAL, não das leituras gravadas.

As leituras gravadas (snapshots) nasceram de calibrações diferentes: antes de
27/09 a recuperação era lida semana × semana e o atleta passava 75-80% do tempo
"em alerta". Contar a sequência nelas mistura réguas — o Renato ouviu "16ª
leitura seguida" com o começo em 30/08, quando pela régua de hoje o alerta só
começa em 04/09 (e a noite ótima da segunda não pesava nada nessa conta). Aqui a
sequência é RECONSTRUÍDA dia a dia com [[RecoveryTrendAnalyzer.is_declining]]: é
a mesma definição do veredito do corpo e se corrige sozinha a cada recalibração.

Alerta ≡ recuperação piorando (STRAINED e RECOVERY_FLAG são as duas caras dela;
com o histórico de carga curto o veredito também segue a recuperação)."""

from datetime import date, timedelta

from app.application.history.recovery_trend_analyzer import (
    RecoveryTrendAnalyzer,
)

# não vasculha o passado inteiro: 90 dias já é "faz muito tempo"
_MAX_LOOKBACK_DAYS = 90


class RecoveryAlertRun:

    @staticmethod
    def since(series, today: date) -> date | None:
        """Primeiro dia da sequência CONTÍNUA de dias em alerta que termina em
        `today`, ou None se hoje não está em alerta. `series` = DailyHealth
        antigo→novo."""

        if not series:

            return None

        start: date | None = None

        day = today

        for _ in range(_MAX_LOOKBACK_DAYS):

            trend = RecoveryTrendAnalyzer.analyze(series, reference_date=day)

            # sem NENHUM dado até aquele dia, não há o que afirmar
            if not trend.days_covered or not RecoveryTrendAnalyzer.is_declining(
                trend
            ):

                break

            start = day

            day -= timedelta(days=1)

        return start

    @staticmethod
    def since_for_profile(profile: str, today: date) -> date | None:
        """Best-effort: falha aqui nunca derruba a leitura (cai na contagem das
        leituras gravadas)."""

        try:

            from app.infrastructure.persistence.garmin_health_repository import (
                GarminHealthRepository,
            )

            return RecoveryAlertRun.since(
                GarminHealthRepository().load(profile), today
            )

        except Exception as e:  # noqa: BLE001

            print(f"Sequência de alerta indisponível p/ '{profile}': {e}")

            return None
