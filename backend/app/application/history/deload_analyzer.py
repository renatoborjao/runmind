"""Deload RESPOSTA — a semana mais leve que um bom treinador dá quando o corpo
PEDE, não a que cai no calendário. Descarga não é item de bloco ("3 sobe, 1
desce"): atleta que absorve a carga, cumpre o plano e recupera bem continua
EVOLUINDO — cortar volume nele só destreina (Maurício 19/10: descarga de 40% na
semana errada; Fernanda: ACWR 1,43 que era só rebote de uma semana parada).

A descarga só existe quando:
  1. o atleta está SENTINDO a carga — recuperação caindo (HRV / FC de repouso
     piorando) com a carga em alta, corpo "sobrecarregado", ou a forma recuando
     com a carga em alta; (se ele também parou de evoluir, entra na razão)
  2. fase final da prova — aí quem recua é o TAPER (e o pós-prova), não esta
     análise.

Recuperação caindo com carga BAIXA não é carga: é sono, vida ou doença, e quem
cuida disso é a leitura do corpo (descarga sem sobrecarga só destreina). Semanas
seguidas de carga (o "clássico 3:1") viram só INFORMAÇÃO, nunca gatilho.

É o COMPLEMENTO preventivo do alerta de lesão (reativo — acende quando algo já
deu errado). Puro/determinístico, vira diretriz pra IA montar a semana: ela
decide (descarregar, segurar ou seguir). Ver [[project_analise_corpo_garmin]],
[[injury_risk_analyzer]] e o espelho `push_room`."""

import re
from dataclasses import dataclass

from app.domain.entities.body_reading import BODY_STRAINED, FALLING, RecoveryTrend
from app.domain.entities.fitness_evolution import EVO_DECLINING, EVO_STABLE

# uma semana abaixo deste fração do pico recente é "recuo" (descarga anterior /
# semana leve), não carga — reinicia a contagem de semanas seguidas. 0.8 (era
# 0.7): o Maurício fez 47 km → 32 km (−33%) numa semana de recuo REAL, mas a
# CARGA caiu só 24% (343 → 261, razão 0.76) e a contagem não reiniciou. Semana
# 20% abaixo do pico já é semana leve.
_DIP_RATIO = 0.8

# o papel de uma semana NO BLOCO que o próprio coach desenhou é de descarga
_DELOAD_ROLE = re.compile(
    r"descarg|alivi|al[ií]vio|recupera|regenera|semana leve|deload", re.IGNORECASE
)

# dentro desta janela pra prova, quem cuida do recuo é o TAPER (não empilhar uma
# descarga por cima da afiação)
_TAPER_ZONE_WEEKS = 3

# depois de uma PROVA, o taper (antes) + a prova JÁ foram o recuo — a
# reconstrução dos primeiros dias não é um novo bloco de sobrecarga. Nesta janela
# pós-prova NÃO descarrega (senão empilha descanso sobre descanso e destreina).
# Bug do Renato/Maurício: prova em 23/08, taper (cargas 341,338) lido como bloco,
# tração de volta (652,691) lida como sobrecarga -> descarga falsa. Ver
# [[race_detector]].
_POST_RACE_GRACE_WEEKS = 3

# descarga só dissipa fadiga de carga ELEVADA. Abaixo deste ACWR a carga aguda
# está <= a crônica: NÃO há sobrecarga pra descarregar — forçar leve só
# DESTREINA (bug do Maurício: descarga com ACWR 0.97 e semana já em queda).
_MIN_OVERLOAD_ACWR = 1.0


@dataclass(slots=True)
class DeloadDecision:

    due: bool
    building_weeks: int          # semanas seguidas de carga sem recuo (informação)
    reason: str

    # o BLOCO previa descarga nesta semana, mas o corpo não a pede (recuperação
    # firme, forma sem recuar): o coach precisa saber que o papel do bloco NÃO
    # vale hoje (Maurício: o bloco de 05/10 pôs a descarga em 26/10, com o corpo
    # absorvendo — descarga ali só destreina)
    block_skipped: bool = False


def is_deload_role(role: str | None) -> bool:
    """O papel desta semana NO BLOCO é de descarga/alívio?"""

    return bool(_DELOAD_ROLE.search(role or ""))


def block_deload_position(
    weeks_plan: list[str] | None, index: int | None,
) -> tuple[bool, int | None]:
    """Onde a DESCARGA cai no bloco que o coach desenhou: (esta semana é a de
    descarga?, daqui a quantas semanas ela vem). `weeks_plan` = o papel de cada
    semana; `index` = a semana k (1-based) que estamos montando. Sem bloco:
    (False, None)."""

    if not weeks_plan or not index or not 1 <= index <= len(weeks_plan):

        return False, None

    this_week = bool(_DELOAD_ROLE.search(weeks_plan[index - 1] or ""))

    ahead = next(
        (
            j + 1 - index
            for j in range(index, len(weeks_plan))
            if _DELOAD_ROLE.search(weeks_plan[j] or "")
        ),
        None,
    )

    return this_week, ahead


def race_owns_the_load(
    weeks_to_race: int | None = None,
    weeks_since_race: int | None = None,
    taper_zone_weeks: int | None = None,
) -> str | None:
    """A prova (antes ou depois) é quem manda na carga? Devolve o motivo ou
    None. Perto da prova o TAPER já alivia; logo APÓS ela o taper + a prova já
    foram o recuo e a carga "subindo" é só a reconstrução. Nem a descarga nem o
    sinal de puxar mexem aqui.

    `taper_zone_weeks`: a zona de taper da PRÓXIMA prova pelo papel dela
    (preparatória = mini-polimento curto; de treino = nenhuma). None = o
    padrão, de prova principal."""

    zone = _TAPER_ZONE_WEEKS if taper_zone_weeks is None else taper_zone_weeks

    if weeks_to_race is not None and weeks_to_race <= zone:

        return "taper cuida do recuo"

    if weeks_since_race is not None and weeks_since_race <= _POST_RACE_GRACE_WEEKS:

        return "pós-prova (o taper/prova já foi o recuo)"

    return None


class DeloadAnalyzer:

    @staticmethod
    def assess(
        weekly_loads: list[float],
        recovery: RecoveryTrend,
        weeks_to_race: int | None = None,
        acwr: float | None = None,
        weeks_since_race: int | None = None,
        taper_zone_weeks: int | None = None,
        block_deload_this_week: bool = False,
        body_state: str | None = None,
        form: str | None = None,
    ) -> DeloadDecision:
        """Decide se a PRÓXIMA semana (a que estamos gerando) deve ser de
        descarga: só se o atleta está SENTINDO a carga. O taper e a janela
        PÓS-PROVA vêm antes e desligam; sem carga elevada, nada de descarga.

        `block_deload_this_week`: o bloco que o próprio coach desenhou pôs a
        descarga nesta semana (ver `block_deload_position`). É uma HIPÓTESE
        escrita semanas antes — só vale se o corpo a confirmar; senão o coach é
        avisado (`block_skipped`) e segue a progressão.

        `body_state` / `form`: o estado do corpo (BODY_*) e a direção da forma
        (EVO_*, None = sem leitura com lastro)."""

        streak = DeloadAnalyzer._consecutive_load_weeks(weekly_loads)

        owner = race_owns_the_load(weeks_to_race, weeks_since_race, taper_zone_weeks)

        if owner:

            return DeloadDecision(False, streak, owner)

        loaded = acwr is None or acwr >= _MIN_OVERLOAD_ACWR

        recovery_falling = (
            recovery.hrv_direction == FALLING or recovery.rhr_direction == FALLING
        )

        signs = []

        if body_state == BODY_STRAINED or (recovery_falling and loaded):

            signs.append("a recuperação está caindo com a carga em alta")

        if form == EVO_DECLINING and loaded:

            signs.append("a forma recuou com a carga em alta")

        if signs:

            if form == EVO_STABLE:

                signs.append("a forma parou de evoluir")

            reason = " e ".join(signs)

            if block_deload_this_week:

                reason = f"o bloco planejou a descarga e o corpo confirma: {reason}"

            return DeloadDecision(True, streak, reason)

        if block_deload_this_week:

            return DeloadDecision(
                False, streak,
                "o bloco previa a descarga, mas o corpo não a pede",
                block_skipped=True,
            )

        return DeloadDecision(False, streak, "sem sinal de cansaço")

    # ------------------------------------------------------------------

    @staticmethod
    def _consecutive_load_weeks(loads: list[float]) -> int:
        """Semanas de CARGA consecutivas terminando na mais recente. Uma semana
        de recuo (bem abaixo do pico anterior) ou zerada reinicia a contagem.
        Só INFORMAÇÃO: não dispara nada."""

        peak = 0.0

        streak = 0

        for load in loads:  # antigo -> novo

            prev_peak = peak

            peak = max(peak, load)

            if load <= 0:

                streak = 0

            elif prev_peak > 0 and load < _DIP_RATIO * prev_peak:

                # semana de recuo relativa a um pico anterior -> reinicia
                streak = 0

            else:

                streak += 1

        return streak


def deload_directive(decision: DeloadDecision) -> str:
    """Sinal COACH-facing pro plano: o corpo está pedindo descarga. É
    CONHECIMENTO, não ordem — a IA pesa com o resto do quadro e decide
    (descarregar, segurar ou seguir). Vazio quando não é hora — sem ruído."""

    if decision.block_skipped:

        return (
            "O BLOCO previa DESCARGA nesta semana, mas o corpo NÃO pede: sem "
            "sinal de cansaço (recuperação firme, forma sem recuar). Descarga "
            "sem motivo só DESTREINA — e o papel do bloco foi escrito semanas "
            "antes, sem saber como ele chegaria. Ele NÃO vale hoje: monte a "
            "semana pela progressão (o que ela acrescenta à evolução dele; se "
            "o dossiê mostra ESPAÇO PRA PUXAR, é hora de puxar) e REDEFINA "
            "\"block\" — a descarga vai pra quando o corpo pedir. Não escreva "
            "nada sobre 'descarga' na semana, a não ser que você mesmo decida "
            "aliviar por outro motivo do quadro (aí marque \"is_deload\" e "
            "explique)."
        )

    if not decision.due:

        return ""

    return (
        f"SINAL DE DESCARGA ({decision.reason}). Não é calendário: é o corpo "
        "pedindo. O que um bom treinador costuma fazer aqui: planejar uma "
        "semana MAIS LEVE de propósito (volume ~35-45% menor, sem tiros/limiar "
        "duro, no máximo um toque de ritmo, mesmos dias) — é quando a forma se "
        "CONSOLIDA (supercompensação). Pese com o resto do quadro (corpo, "
        "meta/fase, o que ele vem absorvendo) e DECIDA: descarregar, só "
        "segurar ou seguir. Se descarregar, marque \"is_deload\": true e "
        "escreva \"deload_why\": 1-2 frases em português simples, COM OS "
        "NÚMEROS DELE (os km das últimas semanas — sem jargão, nada de "
        "ACWR/carga aguda), dizendo por que esta semana é mais leve e o que "
        "ela prepara. É o que ele lê pra não achar que é recuo."
    )


def deload_chat_line(decision: DeloadDecision) -> str:
    """Linha compacta pro quadro do coach de conversa — pra ele saber (e saber
    explicar) por que a semana pode estar mais leve. Quem decide é a IA do
    plano, então a linha não afirma: aponta pras sessões. Vazio quando não é
    hora."""

    if not decision.due:

        return ""

    return (
        f"- Sinal de descarga ({decision.reason}): o plano da semana pode ter "
        "vindo mais leve DE PROPÓSITO (confira nas sessões) — se veio, é pra o "
        "corpo absorver e supercompensar, não é perda de forma."
    )
