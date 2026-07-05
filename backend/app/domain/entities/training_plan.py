from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.domain.entities.planned_session import PlannedSession

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(slots=True)
class TrainingPlan:
    """
    Plano completo de treinamento.

    Nesta versão representa uma única semana de treino.
    """

    athlete_name: str

    objective: str

    phase: str

    weekly_volume: float

    running_days: list[str]

    week_start: date

    sessions: list[PlannedSession] = field(
        default_factory=list
    )

    # "runmind" = gerado pelo sistema; "externo" = plano de treinador
    # humano enviado pelo corredor (nunca ajustado automaticamente)
    source: str = "runmind"

    # semana de corte (deload) do ciclo 3:1 — volume reduzido pra assimilar
    is_deload: bool = False

    # a IA revisora já passou por este plano (marca alertas de realidade
    # nas sessões); evita reprocessar a mesma semana a cada entrega
    reviewed: bool = False

    # Objetivo/foco da semana narrado pela IA-treinadora (ex.: "ganhar
    # velocidade rumo ao sub-50 sem inflar volume").
    weekly_objective: str = ""

    def session_date(
        self,
        session: PlannedSession,
    ) -> date:
        """
        Data real (calendário) de uma sessão, a partir do dia da
        semana (ex: "Monday") e da segunda-feira desta semana
        (`week_start`).
        """

        offset = _WEEKDAY_INDEX.get(
            session.day.lower(),
            0,
        )

        return self.week_start + timedelta(days=offset)

    def find_best_session(
        self,
        executed_distance: float,
    ) -> PlannedSession | None:
        """
        Mantido para compatibilidade com a versão atual.
        """

        if not self.sessions:

            return None

        return min(

            self.sessions,

            key=lambda session: abs(

                (session.planned_distance_km or 0)

                - executed_distance

            ),

        )

    def next_session_after(
        self,
        reference: date,
    ) -> PlannedSession | None:
        """
        Próxima sessão do plano com data estritamente
        posterior à referência.
        """

        upcoming = sorted(
            self.sessions,
            key=lambda session: self.session_date(session),
        )

        for session in upcoming:

            if self.session_date(session) > reference:

                return session

        return None

    def find_session_by_day(
        self,
        day: str,
    ) -> PlannedSession | None:
        """
        Retorna o treino planejado para o dia da semana.
        """

        for session in self.sessions:

            if session.day.lower() == day.lower():

                return session

        return None