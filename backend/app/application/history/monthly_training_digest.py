"""Digest MENSAL do histórico real — a base pro coach responder pergunta de
período arbitrária ("quantos km em maio?", "como foi meu treino em junho?",
"corri mais em maio ou junho?"). O contexto de conversa já traz o AGREGADO de
vida (total), mas não a quebra por mês; sem ela o coach não sabia responder um
recorte e ou inventava ou se esquivava. Puro/determinístico: agrupa as corridas
por mês e rende uma tabela compacta. Ver [[project_analise_treino_hibrida]] e o
arquivo permanente (ActivityArchiveRepository)."""

from dataclasses import dataclass
from datetime import date

from app.domain.entities.activity import Activity
from app.domain.value_objects.sports import is_run_sport

# quantos meses mostrar (janela rolante) — cobre o ano corrente e o anterior
# recente sem inflar o contexto do chat
DEFAULT_MONTHS = 12

# distância mínima (m) pra a corrida contar no digest — fragmento/registro solto
# não é treino; alinha com o resto do sistema (RunnerMetrics)
_MIN_DISTANCE_M = 1000

_MONTH_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


@dataclass(slots=True)
class MonthStat:

    year: int
    month: int
    runs: int
    km: float
    longest_km: float
    avg_pace_sec: int | None  # segundos por km (do total do mês), None sem tempo


class MonthlyTrainingDigest:

    @staticmethod
    def build(
        activities: list[Activity],
        today: date,
        months: int = DEFAULT_MONTHS,
    ) -> list[MonthStat]:
        """Estatística por mês das CORRIDAS de verdade, do mês mais recente pro
        mais antigo, limitada aos últimos `months` meses com atividade."""

        buckets: dict[tuple[int, int], list[Activity]] = {}

        for act in activities:

            if not is_run_sport(act.sport):

                continue

            if (act.distance or 0) < _MIN_DISTANCE_M:

                continue

            key = (act.start_date.year, act.start_date.month)

            buckets.setdefault(key, []).append(act)

        stats = [
            MonthlyTrainingDigest._month_stat(year, month, acts)
            for (year, month), acts in buckets.items()
        ]

        # mais recente primeiro; corta na janela
        stats.sort(key=lambda s: (s.year, s.month), reverse=True)

        return stats[:months]

    @staticmethod
    def render(
        activities: list[Activity],
        today: date,
        months: int = DEFAULT_MONTHS,
    ) -> str:
        """Tabela compacta pro contexto do coach. Vazio quando não há corrida
        arquivada (o coach cai no que já tem — nada é inventado)."""

        stats = MonthlyTrainingDigest.build(activities, today, months)

        if not stats:

            return ""

        lines = [
            "HISTÓRICO POR MÊS (corridas reais arquivadas — responda perguntas "
            "de período SÓ com estes números, nunca invente um mês que não está "
            "aqui; mês ausente = sem corrida registrada):"
        ]

        for s in stats:

            pace = (
                f", pace médio {MonthlyTrainingDigest._pace(s.avg_pace_sec)}/km"
                if s.avg_pace_sec is not None
                else ""
            )

            plural = "corrida" if s.runs == 1 else "corridas"

            lines.append(
                f"- {_MONTH_PT[s.month]}/{s.year}: {s.runs} {plural}, "
                f"{s.km:.0f} km{pace}, maior {s.longest_km:.0f} km"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------

    @staticmethod
    def _month_stat(year: int, month: int, acts: list[Activity]) -> MonthStat:

        total_m = sum(a.distance or 0 for a in acts)

        total_time = sum(a.moving_time or 0 for a in acts)

        longest_m = max((a.distance or 0 for a in acts), default=0)

        # pace médio do mês = tempo total / distância total (não média de paces,
        # que enviesaria pros treinos curtos). Só quando há tempo e distância.
        avg_pace_sec = (
            round(total_time / (total_m / 1000))
            if total_m > 0 and total_time > 0
            else None
        )

        return MonthStat(
            year=year,
            month=month,
            runs=len(acts),
            km=round(total_m / 1000, 1),
            longest_km=round(longest_m / 1000, 1),
            avg_pace_sec=avg_pace_sec,
        )

    @staticmethod
    def _pace(sec_per_km: int) -> str:

        minutes, seconds = divmod(int(sec_per_km), 60)

        return f"{minutes}:{seconds:02d}"
