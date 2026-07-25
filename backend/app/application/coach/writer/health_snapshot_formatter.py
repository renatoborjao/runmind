"""Painel FACTUAL de recuperação — os números da camada de saúde do Garmin
(sono, HRV, FC de repouso, stress, body battery, VO2máx) com seta de tendência.

Complementa a leitura do corpo (que dá o VEREDITO narrado, sem números crus):
aqui o atleta vê o dado concreto por trás do veredito. Determinístico, sem IA.
Ver [[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import FALLING, RISING, RecoveryTrend


class HealthSnapshotFormatter:

    @staticmethod
    def panel(recovery: RecoveryTrend) -> str | None:
        """Painel compacto dos números de recuperação. None quando não há
        dado do Garmin (o chamador simplesmente não anexa nada)."""

        if not recovery.has_data:

            return None

        lines: list[str] = []

        if recovery.sleep_avg_hours is not None:

            sleep = HealthSnapshotFormatter._hours(recovery.sleep_avg_hours)

            short = ""

            if recovery.nights_counted:

                short = (
                    f" · {recovery.short_nights} de "
                    f"{recovery.nights_counted} noites curtas"
                )

            lines.append(f"• 😴 Sono: {sleep}/noite{short}")

        if recovery.hrv_recent is not None:

            arrow = HealthSnapshotFormatter._arrow(
                recovery.hrv_direction, good_word="bom sinal"
            )

            hrv = HealthSnapshotFormatter._num(recovery.hrv_recent)

            lines.append(f"• 💓 HRV: {hrv} ms{arrow}")

        if recovery.rhr_recent is not None:

            arrow = HealthSnapshotFormatter._arrow(
                recovery.rhr_direction, good_word="bom sinal"
            )

            lines.append(f"• ❤️ FC de repouso: {recovery.rhr_recent} bpm{arrow}")

        if recovery.stress_avg is not None:

            lines.append(f"• 🧠 Stress médio: {recovery.stress_avg}")

        if recovery.body_battery_recent is not None:

            sign = "+" if recovery.body_battery_recent >= 0 else ""

            lines.append(
                f"• 🔋 Body Battery: {sign}{recovery.body_battery_recent}/dia"
            )

        if recovery.vo2max is not None:

            vo2 = HealthSnapshotFormatter._num(recovery.vo2max)

            lines.append(f"• 🫁 VO₂máx: {vo2}")

        if not lines:

            return None

        return "\n".join(["📊 Sua recuperação (tendência recente)", *lines])

    # ------------------------------------------------------------------

    @staticmethod
    def _arrow(direction: str, good_word: str) -> str:
        """Seta + leitura da tendência, sempre em POV de RECUPERAÇÃO: o
        analisador entrega RISING = melhorando, FALLING = piorando (já
        normaliza que HRV subir e FC-repouso cair são ambos 'melhora')."""

        if direction == RISING:

            return f" ↗️ {good_word}"

        if direction == FALLING:

            return " ↘️ atenção"

        return " → estável"

    @staticmethod
    def _num(value: float) -> str:
        """Mostra inteiro quando é redondo (52.0 -> '52'), senão 1 casa."""

        return str(int(value)) if float(value).is_integer() else f"{value:.1f}"

    @staticmethod
    def _hours(hours: float) -> str:
        """6.2 -> '6h12'."""

        whole = int(hours)

        minutes = round((hours - whole) * 60)

        if minutes == 60:

            whole += 1

            minutes = 0

        return f"{whole}h{minutes:02d}"
