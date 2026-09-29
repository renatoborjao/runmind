"""Lê a leitura do corpo de HOJE à luz das anteriores — transforma a foto num
filme. Puro/determinístico (nenhum IO, nenhuma IA): recebe o histórico de
snapshots + a leitura atual e devolve a trajetória PRONTA (movimento, streak de
alerta, e as frases pro atleta e pro cérebro). Igual ao resto da análise, a IA
só narra o que este analisador já concluiu — não recalcula.

Régua: os estados que pedem atenção (STRAINED, RECOVERY_FLAG) são "alerta". A
mensagem só ganha uma frase de trajetória quando há NOTÍCIA de verdade — entrou
em alerta, saiu do alerta, ou segue em alerta pela 2ª+ vez. Oscilação dentro do
verde fica quieta (nada de encher o atleta de ruído). Ver
[[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import (
    BODY_ABSORBING,
    BODY_BALANCED,
    BODY_BUILDING,
    BODY_FRESH,
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_FIRST,
    TRAJ_IMPROVED,
    TRAJ_PERSISTING,
    TRAJ_STEADY,
    TRAJ_WORSENED,
    BodyReadingSnapshot,
    BodyTrajectory,
)

# estados que pedem atenção (a carga não está sendo absorvida bem)
_ALERT = {BODY_STRAINED, BODY_RECOVERY_FLAG}

# quão bem o corpo está lidando com o treino — maior = melhor. Serve só pra
# decidir se de uma leitura pra outra MELHOROU ou PIOROU.
_RANK = {
    BODY_STRAINED: 0,
    BODY_RECOVERY_FLAG: 1,
    BODY_BUILDING: 2,      # sem histórico de carga — neutro
    BODY_ABSORBING: 3,
    BODY_BALANCED: 4,
    BODY_FRESH: 5,
}


def _weeks(n: int) -> str:

    return {1: "uma semana", 2: "duas semanas", 3: "três semanas"}.get(
        n, f"{n} semanas"
    )


class BodyTrajectoryAnalyzer:

    @staticmethod
    def of(
        history: list[BodyReadingSnapshot],
        reading: BodyReading,
        today,
        alert_since=None,
    ) -> BodyTrajectory:
        """`history` = snapshots ANTERIORES (antigo->novo), já sem o de hoje.
        `reading` = a leitura recém-calculada. `today` entra só pra assinatura
        simétrica com o resto (a comparação é por ordem, não por data).
        `alert_since` = início da sequência de dias em alerta RECONSTRUÍDA da
        série com a régua atual ([[RecoveryAlertRun]]); manda sobre as leituras
        gravadas (que misturam calibrações antigas) quando vem."""

        current = reading.body_state

        current_alert = current in _ALERT

        prior = [s for s in history if s.day < today]

        if not prior:

            return BodyTrajectory(
                movement=TRAJ_FIRST,
                alert_streak=1 if current_alert else 0,
                previous_state=None,
            )

        previous = prior[-1].body_state

        prev_alert = previous in _ALERT

        streak, since = BodyTrajectoryAnalyzer._alert_streak(
            prior, current_alert, today
        )

        # a série reconstruída com a régua de hoje é a autoridade do TEMPO em
        # alerta; as leituras gravadas só decidem a contagem
        if current_alert and alert_since is not None:

            since = min(alert_since, today)

        alert_days = (today - since).days + 1 if since else 0

        movement = BodyTrajectoryAnalyzer._movement(
            current, previous, current_alert, prev_alert, streak
        )

        athlete_note = BodyTrajectoryAnalyzer._athlete_note(
            movement, streak, current_alert, prev_alert,
            weeks_now=(today - since).days // 7 if since else 0,
            weeks_before=(prior[-1].day - since).days // 7 if since else 0,
        )

        fact = (
            f"Trajetória do corpo: agora {current}, na leitura anterior "
            f"{previous} ({movement})"
            + (
                f"; a tendência de recuperação está fora da faixa dele há "
                f"{alert_days} dias (desde {since:%d/%m}) — é a média de 7 "
                "dias, que muda devagar"
                if streak >= 2 and since
                else ""
            )
            + "."
        )

        return BodyTrajectory(
            movement=movement,
            alert_streak=streak,
            previous_state=previous,
            athlete_note=athlete_note,
            fact=fact,
            alert_days=alert_days,
            alert_since=since,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _alert_streak(
        prior: list[BodyReadingSnapshot],
        current_alert: bool,
        today,
    ) -> tuple[int, object | None]:
        """(quantas leituras SEGUIDAS estão em alerta, dia em que a sequência
        começou). (0, None) se a de hoje não é alerta — a sequência quebrou."""

        if not current_alert:

            return 0, None

        streak = 1

        since = today

        for snap in reversed(prior):

            if snap.body_state in _ALERT:

                streak += 1

                since = snap.day

            else:

                break

        return streak, since

    @staticmethod
    def _movement(
        current: str,
        previous: str,
        current_alert: bool,
        prev_alert: bool,
        streak: int,
    ) -> str:

        # segue em alerta pela 2ª+ vez: é o sinal mais importante (padrão, não
        # dia isolado) — tem prioridade sobre melhora/piora dentro do alerta
        if current_alert and prev_alert and streak >= 2:

            return TRAJ_PERSISTING

        rank_now = _RANK.get(current, 2)

        rank_before = _RANK.get(previous, 2)

        if rank_now > rank_before:

            return TRAJ_IMPROVED

        if rank_now < rank_before:

            return TRAJ_WORSENED

        return TRAJ_STEADY

    @staticmethod
    def _athlete_note(
        movement: str,
        streak: int,
        current_alert: bool,
        prev_alert: bool,
        weeks_now: int = 0,
        weeks_before: int = 0,
    ) -> str:
        """Só fala quando há NOTÍCIA: entrou em alerta, saiu do alerta, ou
        segue em alerta. A sequência longa NÃO é repetida todo dia (nem em
        "N leituras seguidas", que soa como N dias ruins): fala na 2ª leitura e
        de novo a cada SEMANA nova de alerta, em tempo. Melhora/piora DENTRO do
        verde fica muda (não vira ruído pro atleta)."""

        if movement == TRAJ_PERSISTING:

            if streak >= 3:

                # o mesmo recado todo dia é ruído: só quando virou uma semana nova
                if weeks_now > weeks_before and weeks_now >= 1:

                    return (
                        f"E já faz {_weeks(weeks_now)} com a recuperação fora "
                        "da faixa dele — virou padrão, não um dia isolado."
                    )

                return ""

            return (
                "E não foi só hoje: é a 2ª leitura seguida assim, vale levar a "
                "sério."
            )

        # melhora só é notícia quando SAIU do alerta
        if movement == TRAJ_IMPROVED and prev_alert and not current_alert:

            return "E melhorou desde a última leitura — o corpo está reagindo."

        # piora só é notícia quando ENTROU no alerta
        if movement == TRAJ_WORSENED and current_alert and not prev_alert:

            return "E é uma piora em relação à última leitura, fica de olho."

        return ""
