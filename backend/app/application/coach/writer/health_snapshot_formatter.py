"""Painel FACTUAL de recuperação — os números da camada de saúde do Garmin
(sono, HRV, FC de repouso, stress, body battery, VO2máx) com seta de tendência.

Complementa a leitura do corpo (que dá o VEREDITO narrado, sem números crus):
aqui o atleta vê o dado concreto por trás do veredito. Determinístico, sem IA.
Ver [[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import FALLING, RISING, RecoveryTrend

# enums que a Garmin devolve em inglês -> rótulo pro atleta
_TRAINING_STATUS = {
    "PRODUCTIVE": "produtivo",
    "MAINTAINING": "mantendo a forma",
    "RECOVERY": "recuperação",
    "PEAKING": "no pico",
    "OVERREACHING": "excesso de carga",
    "UNPRODUCTIVE": "improdutivo",
    "DETRAINING": "destreino",
    "STRAINED": "sobrecarga",
}

_HRV_STATUS = {
    "BALANCED": "equilibrado",
    "UNBALANCED": "desequilibrado",
    "LOW": "baixo",
    "POOR": "ruim",
}


class HealthSnapshotFormatter:

    @staticmethod
    def panel(recovery: RecoveryTrend) -> str | None:
        """Painel compacto dos números de recuperação. None quando não há
        dado do Garmin (o chamador simplesmente não anexa nada). Quando o
        relógio computa prontidão/status/nota de sono, MOSTRA o número dele
        (mais autoritativo que o nosso derivado)."""

        if not recovery.has_data:

            return None

        lines: list[str] = []

        # números que a própria Garmin calcula vêm primeiro (mandam quando há)
        if recovery.readiness_score is not None:

            lines.append(
                f"• ✅ Prontidão (Garmin): {recovery.readiness_score}/100"
            )

        status = _TRAINING_STATUS.get(recovery.training_status or "")

        if status:

            lines.append(f"• 📊 Status de treino (Garmin): {status}")

        if recovery.sleep_avg_hours is not None:

            sleep = HealthSnapshotFormatter._hours(recovery.sleep_avg_hours)

            short = ""

            if recovery.nights_counted:

                short = (
                    f" · {recovery.short_nights} de "
                    f"{recovery.nights_counted} noites curtas"
                )

            # a NOTA de sono é da própria Garmin — quando vem, entra junto
            score = (
                f" · nota Garmin {recovery.sleep_score}/100"
                if recovery.sleep_score is not None
                else ""
            )

            lines.append(f"• 😴 Sono: {sleep}/noite{short}{score}")

        if recovery.hrv_recent is not None:

            arrow = HealthSnapshotFormatter._arrow(
                recovery.hrv_direction, good_word="bom sinal"
            )

            hrv = HealthSnapshotFormatter._num(recovery.hrv_recent)

            # o STATUS de HRV é da própria Garmin (equilibrado/desequilibrado)
            status = _HRV_STATUS.get(recovery.hrv_status or "")

            status_txt = f" · Garmin: {status}" if status else ""

            lines.append(f"• 💓 HRV: {hrv} ms{arrow}{status_txt}")

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
