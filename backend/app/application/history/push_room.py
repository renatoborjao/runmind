"""ESPAÇO PRA PUXAR — o espelho do sinal de descarga. A descarga diz "o corpo
está pedindo pra aliviar"; este diz "o corpo está respondendo, PUXE". Sem ele o
coach só via os freios (passo de +5-10%, "segurança primeiro") e ficava na zona
de conforto: repetia a semana, o longão parava, o pace não variava.

Acende quando TUDO isto vale: o atleta cumpriu o plano (as últimas semanas), a
recuperação está firme (HRV e FC de repouso sem piorar), o corpo não está
sobrecarregado nem com a recuperação em queda, a forma não recuou, a carga não
disparou, não há risco de lesão nem doença em aberto — e a prova não é quem
manda na carga (taper / pós-prova).

Puro/determinístico: vira FATO + CONHECIMENTO pra IA (ela decide a dose e a
forma). O único teto que a diretriz mantém é o de SALTO — onde corredor amador
se machuca e o HRV não avisa. Ver [[deload_analyzer]] e [[feedback_ia_decide_sem_regras]]."""

from dataclasses import dataclass

from app.application.history.deload_analyzer import race_owns_the_load
from app.domain.entities.body_reading import (
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    FALLING,
    RecoveryTrend,
)
from app.domain.entities.fitness_evolution import EVO_DECLINING

# quanto do plano ele cumpriu, em média, nas últimas semanas com plano
_MIN_ADHERENCE = 0.9

# acima disto a carga aguda já subiu rápido sobre a crônica: não é hora de
# empilhar mais (o ACWR passa de 1.3 = fora da faixa saudável de rampa)
_MAX_ACWR = 1.3


@dataclass(slots=True)
class PushRoom:

    open: bool
    reason: str
    adherence: float | None = None   # média cumprida nas últimas semanas (0-1)
    weeks: int = 0                   # quantas semanas entraram na média


class PushRoomAnalyzer:

    @staticmethod
    def assess(
        adherence: list[float],
        recovery: RecoveryTrend,
        body_state: str | None = None,
        form: str | None = None,
        acwr: float | None = None,
        weeks_to_race: int | None = None,
        weeks_since_race: int | None = None,
        taper_zone_weeks: int | None = None,
        injury_risk: bool = False,
        ill: bool = False,
    ) -> PushRoom:
        """Há folga REAL pra progredir esta semana? `adherence` = fração do
        plano cumprida em cada semana recente (a mais recente por último)."""

        if ill:

            return PushRoom(False, "doença em aberto")

        owner = race_owns_the_load(weeks_to_race, weeks_since_race, taper_zone_weeks)

        if owner:

            return PushRoom(False, owner)

        if not adherence:

            return PushRoom(False, "sem execução recente pra provar a folga")

        mean = sum(adherence) / len(adherence)

        if mean < _MIN_ADHERENCE:

            return PushRoom(
                False, "ainda não vem cumprindo o plano", mean, len(adherence),
            )

        if (
            recovery.hrv_direction == FALLING
            or recovery.rhr_direction == FALLING
            or body_state in (BODY_STRAINED, BODY_RECOVERY_FLAG)
        ):

            return PushRoom(
                False, "a recuperação está caindo", mean, len(adherence),
            )

        if form == EVO_DECLINING:

            return PushRoom(False, "a forma recuou", mean, len(adherence))

        if acwr is not None and acwr > _MAX_ACWR:

            return PushRoom(
                False, "a carga já subiu rápido", mean, len(adherence),
            )

        if injury_risk:

            return PushRoom(False, "risco de lesão", mean, len(adherence))

        return PushRoom(
            True, "cumpre o plano, recupera bem e a carga está sob controle",
            mean, len(adherence),
        )


def push_room_directive(room: PushRoom, numbers: str = "") -> str:
    """Sinal COACH-facing pro plano: há folga pra puxar. É CONHECIMENTO, não
    ordem — a IA decide a dose e a forma. Vazio quando não há folga (sem
    ruído). `numbers` = os km reais do atleta, já em português."""

    if not room.open:

        return ""

    pct = round((room.adherence or 0) * 100)

    span = (
        f"nas últimas {room.weeks} semanas" if room.weeks > 1 else "na última semana"
    )

    return (
        f"ESPAÇO PRA PUXAR — o corpo está respondendo: cumpriu {pct}% do plano "
        f"{span}, a recuperação está firme e a forma não recuou.{numbers} Isso é "
        "folga REAL pra progredir, não pra repetir a semana anterior: o passo-"
        "padrão é ~+10% de volume (até ~15% quando tudo está verde), ancorado "
        "no que o atleta REALMENTE correu nas semanas fechadas — se correu "
        "acima do plano, foi o plano que ficou baixo — e/ou mais QUALIDADE em "
        "TODOS os tipos de treino, não só no longão, sempre rumo à meta do "
        "atleta: o forte chega mais perto do ritmo-alvo ou ganha série maior, "
        "o moderado alonga, o longão ganha km OU qualidade, e o leve continua "
        "leve DE VERDADE (a qualidade dele é a FC baixa, as acelerações, a "
        "cadência — nunca vira mais um forte). Ser conservador aqui é desperdiçar a "
        "janela em que o atleta evolui. O único teto é o de SALTO: nada de semana "
        "+25% sobre a anterior nem longão muito acima do maior recente (é onde "
        "corredor amador se machuca e o HRV não avisa). A dose e a forma são "
        "suas."
    )
