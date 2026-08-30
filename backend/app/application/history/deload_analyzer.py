"""Deload PROATIVO — a semana de descarga que um bom treinador PLANEJA, não a que
ele improvisa quando o atleta já quebrou. Depois de ~3 semanas seguidas de carga
crescente, o corpo precisa de uma semana mais leve pra absorver e supercompensar
(o clássico 3:1). Sem isso o atleta marcha rumo ao overtraining e só freia
lesionado.

É o COMPLEMENTO preventivo do alerta de lesão (que é reativo — acende quando algo
já deu errado): aqui nada deu errado, é recuperação planejada. Puro/determinístico,
vira diretriz pra IA montar a semana leve. Ver [[project_analise_corpo_garmin]] e
[[injury_risk_analyzer]]."""

from dataclasses import dataclass

from app.domain.entities.body_reading import FALLING, RecoveryTrend

# semanas seguidas de carga que fecham um bloco (3 building -> a 4ª é descarga)
_BLOCK_WEEKS = 3

# com fadiga acumulando (recuperação caindo), antecipa a descarga
_FATIGUE_BLOCK_WEEKS = 2

# uma semana abaixo deste fração do pico recente é "recuo" (descarga anterior /
# semana leve), não carga — reinicia a contagem do bloco
_DIP_RATIO = 0.7

# dentro desta janela pra prova, quem cuida do recuo é o TAPER (não empilhar uma
# descarga de bloco por cima da afiação)
_TAPER_ZONE_WEEKS = 3

# descarga só dissipa fadiga de carga ELEVADA. Abaixo deste ACWR a carga aguda
# está <= a crônica: NÃO há sobrecarga pra descarregar — forçar leve só
# DESTREINA (bug do Maurício: descarga com ACWR 0.97 e semana já em queda).
_MIN_OVERLOAD_ACWR = 1.0


@dataclass(slots=True)
class DeloadDecision:

    due: bool
    building_weeks: int          # semanas seguidas de carga sem recuo
    reason: str


class DeloadAnalyzer:

    @staticmethod
    def assess(
        weekly_loads: list[float],
        recovery: RecoveryTrend,
        weeks_to_race: int | None = None,
        acwr: float | None = None,
    ) -> DeloadDecision:
        """Decide se a PRÓXIMA semana (a que estamos gerando) deve ser de
        descarga. Gatilho principal: tamanho do bloco de carga; a fadiga
        antecipa; o taper (perto da prova) desliga; e o ACWR trava — sem carga
        elevada, descarga só destreina."""

        streak = DeloadAnalyzer._consecutive_load_weeks(weekly_loads)

        # perto da prova o taper já alivia — não empilha descarga de bloco
        if weeks_to_race is not None and weeks_to_race <= _TAPER_ZONE_WEEKS:

            return DeloadDecision(False, streak, "taper cuida do recuo")

        # SEM SOBRECARGA não se descarrega nada: com o ACWR mostrando carga aguda
        # <= crônica, uma semana leve à força só APAGA forma (o atleta reclama
        # que "não evolui"). Descarga é pra dissipar overload — exige overload.
        if acwr is not None and acwr < _MIN_OVERLOAD_ACWR:

            return DeloadDecision(False, streak, "carga não está elevada")

        fatigued = (
            recovery.hrv_direction == FALLING
            or recovery.rhr_direction == FALLING
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
    """Diretriz COACH-facing pro plano: quando a descarga está na hora, a IA
    monta uma semana leve DE PROPÓSITO. Vazio quando não é hora — sem ruído."""

    if not decision.due:

        return ""

    return (
        f"SEMANA DE DESCARGA (recuperação PLANEJADA — {decision.reason}). Monte "
        "uma semana MAIS LEVE de propósito: reduza o volume ~35-45% e CORTE a "
        "intensidade (nada de tiros/limiar duro; rodagem leve, no máximo um "
        "toque de ritmo). Mantenha os MESMOS dias/frequência do atleta. NÃO é "
        "perda de forma — é quando a forma se CONSOLIDA (supercompensação); "
        "explique isso no propósito das sessões pra ele não achar que é recuo."
    )


def deload_chat_line(decision: DeloadDecision) -> str:
    """Linha compacta pro quadro do coach de conversa — pra ele saber (e saber
    explicar) por que a semana está mais leve. Vazio quando não é hora."""

    if not decision.due:

        return ""

    return (
        f"- Semana de descarga (recuperação planejada após {decision.reason}): "
        "plano mais leve DE PROPÓSITO, pra o corpo absorver e supercompensar — "
        "não é perda de forma."
    )
