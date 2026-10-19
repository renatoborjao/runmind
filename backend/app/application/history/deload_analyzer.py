"""Deload PROATIVO — a semana de descarga que um bom treinador PLANEJA, não a que
ele improvisa quando o atleta já quebrou. Depois de ~3 semanas seguidas de carga
crescente, o corpo precisa de uma semana mais leve pra absorver e supercompensar
(o clássico 3:1). Sem isso o atleta marcha rumo ao overtraining e só freia
lesionado.

É o COMPLEMENTO preventivo do alerta de lesão (que é reativo — acende quando algo
já deu errado): aqui nada deu errado, é recuperação planejada. Puro/determinístico,
vira diretriz pra IA montar a semana leve. Ver [[project_analise_corpo_garmin]] e
[[injury_risk_analyzer]]."""

import re
from dataclasses import dataclass

from app.domain.entities.body_reading import FALLING, RecoveryTrend

# semanas seguidas de carga que fecham um bloco (3 building -> a 4ª é descarga)
_BLOCK_WEEKS = 3

# com fadiga acumulando (recuperação caindo), antecipa a descarga
_FATIGUE_BLOCK_WEEKS = 2

# uma semana abaixo deste fração do pico recente é "recuo" (descarga anterior /
# semana leve), não carga — reinicia a contagem do bloco. 0.8 (era 0.7): o
# Maurício fez 47 km → 32 km (−33%) numa semana de recuo REAL, mas a CARGA caiu só
# 24% (343 → 261, razão 0.76) e a contagem não reiniciou — o analisador leu 4
# semanas seguidas, mandou descarga de 40% na 3ª semana de um bloco de 4 e o plano
# perdeu o treino-chave dela (19/10). Semana 20% abaixo do pico já é semana leve.
_DIP_RATIO = 0.8

# o papel de uma semana NO BLOCO que o próprio coach desenhou é de descarga
_DELOAD_ROLE = re.compile(
    r"descarg|alivi|al[ií]vio|recupera|regenera|semana leve|deload", re.IGNORECASE
)

# dentro desta janela pra prova, quem cuida do recuo é o TAPER (não empilhar uma
# descarga de bloco por cima da afiação)
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
    building_weeks: int          # semanas seguidas de carga sem recuo
    reason: str

    # o BLOCO previa descarga nesta semana, mas o quadro não a sustenta (sem
    # carga elevada e sem recuperação caindo): o coach precisa saber que o papel
    # do bloco NÃO vale hoje (Maurício: o bloco de 05/10 pôs a descarga em 26/10,
    # depois de uma semana já mais leve — descarga ali só destreina)
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
        block_deload_in_weeks: int | None = None,
    ) -> DeloadDecision:
        """Decide se a PRÓXIMA semana (a que estamos gerando) deve ser de
        descarga. Gatilho principal: tamanho do bloco de carga; a fadiga
        antecipa; o taper (perto da prova) e a janela PÓS-PROVA desligam; e o
        ACWR trava — sem carga elevada, descarga só destreina.

        `taper_zone_weeks`: a zona de taper da PRÓXIMA prova pelo papel dela
        (preparatória = mini-polimento curto; de treino = nenhuma). None = o
        padrão, de prova principal.

        `block_deload_this_week` / `block_deload_in_weeks`: onde o BLOCO que o
        próprio coach desenhou põe a descarga (ver `block_deload_position`). A
        descarga é planejada no desenho do bloco; o sinal de carga não a antecipa
        por conta própria — só a fadiga (recuperação caindo) antecipa."""

        streak = DeloadAnalyzer._consecutive_load_weeks(weekly_loads)

        zone = (
            _TAPER_ZONE_WEEKS if taper_zone_weeks is None else taper_zone_weeks
        )

        # perto da prova o taper já alivia — não empilha descarga de bloco
        if weeks_to_race is not None and weeks_to_race <= zone:

            return DeloadDecision(False, streak, "taper cuida do recuo")

        # logo APÓS a prova: o taper + a prova já foram o recuo. A carga
        # "subindo" que o histórico mostra é só a reconstrução — não descarrega
        # (o ACWR vem inflado porque o taper puxou a crônica pra baixo).
        if (
            weeks_since_race is not None
            and weeks_since_race <= _POST_RACE_GRACE_WEEKS
        ):

            return DeloadDecision(
                False, streak, "pós-prova (o taper/prova já foi o recuo)"
            )

        fatigued = (
            recovery.hrv_direction == FALLING
            or recovery.rhr_direction == FALLING
        )

        # A DESCARGA QUE O BLOCO PLANEJOU é condicional: o papel foi escrito
        # semanas antes, sem saber como o atleta chegaria. Vale com carga ELEVADA
        # ou com a recuperação CAINDO; sem isso o bloco não se aplica hoje (semana
        # leve sobre semana já leve só destreina) e o coach segue a progressão.
        if block_deload_this_week:

            if fatigued or acwr is None or acwr >= _MIN_OVERLOAD_ACWR:

                return DeloadDecision(
                    True, streak,
                    "o bloco planejado põe a descarga nesta semana"
                    + (" e a recuperação está caindo" if fatigued else ""),
                )

            return DeloadDecision(
                False, streak,
                "o bloco previa a descarga, mas a carga não está elevada",
                block_skipped=True,
            )

        # SEM SOBRECARGA não se descarrega nada: com o ACWR mostrando carga aguda
        # <= crônica, uma semana leve à força só APAGA forma (o atleta reclama
        # que "não evolui"). Descarga é pra dissipar overload — exige overload.
        if acwr is not None and acwr < _MIN_OVERLOAD_ACWR:

            return DeloadDecision(False, streak, "carga não está elevada")

        # o bloco desenhado pelo coach manda no CALENDÁRIO da descarga: se ela já
        # está planejada pra daqui a N semanas, esta semana segue o papel dela
        # (Maurício 19/10: a semana 3 era o simulado no ritmo-alvo e a descarga
        # era a 4 — o sinal de carga trocou uma pela outra)
        if not fatigued and block_deload_in_weeks:

            return DeloadDecision(
                False, streak,
                f"o bloco já planeja a descarga daqui a {block_deload_in_weeks} "
                f"semana{'s' if block_deload_in_weeks > 1 else ''}",
            )

        threshold = _FATIGUE_BLOCK_WEEKS if fatigued else _BLOCK_WEEKS

        if streak >= threshold:

            reason = (
                f"{streak} semanas seguidas de carga"
                + (" + recuperação caindo" if fatigued else "")
            )

            return DeloadDecision(True, streak, reason)

        return DeloadDecision(False, streak, "bloco ainda curto")

    # ------------------------------------------------------------------

    @staticmethod
    def _consecutive_load_weeks(loads: list[float]) -> int:
        """Semanas de CARGA consecutivas terminando na mais recente. Uma semana
        de recuo (bem abaixo do pico anterior) ou zerada reinicia a contagem —
        assim, logo após uma descarga o bloco recomeça do zero (auto-regula)."""

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
    """Sinal COACH-facing pro plano: o bloco de carga está no ponto de descarga.
    É CONHECIMENTO, não ordem — a IA pesa com o resto do quadro e decide
    (descarregar, segurar ou seguir). Vazio quando não é hora — sem ruído."""

    if decision.block_skipped:

        return (
            "O BLOCO previa DESCARGA nesta semana, mas o quadro NÃO mostra "
            "carga elevada nem recuperação caindo — e descarga sem sobrecarga só "
            "DESTREINA (semana leve em cima de semana já leve). O papel de "
            "descarga do bloco NÃO vale hoje: monte a semana pela progressão "
            "(o que ela acrescenta à evolução dele) e REDEFINA \"block\" — a "
            "descarga vai pra quando a carga pedir. Não escreva nada sobre "
            "'descarga' na semana, a não ser que você mesmo decida aliviar por "
            "outro motivo do quadro (aí marque \"is_deload\" e explique)."
        )

    if not decision.due:

        return ""

    return (
        f"SINAL DE DESCARGA ({decision.reason}). O que um bom treinador costuma "
        "fazer aqui: planejar uma semana MAIS LEVE de propósito (volume ~35-45% "
        "menor, sem tiros/limiar duro, no máximo um toque de ritmo, mesmos "
        "dias) — é quando a forma se CONSOLIDA (supercompensação). Pese com o "
        "resto do quadro (corpo, meta/fase, o que ele vem absorvendo) e DECIDA: "
        "descarregar, só segurar ou seguir. Se descarregar, marque "
        "\"is_deload\": true e escreva \"deload_why\": 1-2 frases em português "
        "simples, COM OS NÚMEROS DELE (os km das últimas semanas — sem jargão, "
        "nada de ACWR/carga aguda), dizendo por que esta semana é mais leve e "
        "o que ela prepara. É o que ele lê pra não achar que é recuo."
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
