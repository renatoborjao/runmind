"""Auto-calibração do pace: o coach mede o PRÓPRIO erro de previsão (ritmo
prescrito × ritmo que o atleta sustentou nos tiros) e ajusta o alvo. Fecha o loop
de aprendizado de forma MENSURÁVEL e serve a regra de ouro do Renato — não
prescrever mais rápido do que o atleta aguenta (mata o cara / arrisca lesão), nem
deixar folga demais quando ele já supera com sobra.

Puro/determinístico. Extrai o erro dos blocos de QUALIDADE (tiros) da comparação
bloco-a-bloco e destila um viés sistemático. Ver [[pace_calibration_store]] e
[[project_modelo_pace_vdot]]."""

from dataclasses import dataclass
from statistics import median

# só blocos de tiro (qualidade) — é onde "prescrever rápido demais" machuca; a
# rodagem correr mais devagar que o teto é esperado, não é erro de previsão
_QUALITY_KINDS = {"interval"}

# viés (s/km) a partir do qual vale ajustar — abaixo disso é ruído normal
_MEANINGFUL_BIAS = 5.0

# amostras mínimas pra confiar num padrão (um dia ruim não é tendência)
_MIN_SAMPLES = 4


@dataclass(slots=True)
class CalibrationVerdict:

    bias_sec: float          # + = corre mais DEVAGAR que o prescrito (alvo agressivo)
    samples: int
    adjust: bool             # há viés sistemático relevante?


class PaceCalibrationAnalyzer:

    @staticmethod
    def deltas_from_blocks(blocks) -> list[float]:
        """Erro por bloco de qualidade: executado − teto prescrito (s/km).
        + = correu mais devagar que o alvo; − = mais rápido. Ignora bloco sem
        alvo de pace ou sem execução."""

        out: list[float] = []

        for block in blocks:

            if getattr(block, "kind", "") not in _QUALITY_KINDS:

                continue

            target = PaceCalibrationAnalyzer._sec(block.pace_max)

            if target is None or not block.executed_pace:

                continue

            out.append(block.executed_pace * 60 - target)

        return out

    @staticmethod
    def assess(deltas: list[float]) -> CalibrationVerdict:

        if len(deltas) < _MIN_SAMPLES:

            return CalibrationVerdict(0.0, len(deltas), adjust=False)

        bias = median(deltas)

        return CalibrationVerdict(
            bias_sec=round(bias, 1),
            samples=len(deltas),
            adjust=abs(bias) >= _MEANINGFUL_BIAS,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _sec(pace: str | None) -> int | None:
        """'5:55' -> 355. None se vazio/inválido."""

        if not pace or ":" not in str(pace):

            return None

        try:

            minutes, seconds = str(pace).split(":")

            return int(minutes) * 60 + int(seconds)

        except (ValueError, TypeError):

            return None


def calibration_directive(verdict: CalibrationVerdict) -> str:
    """Diretriz pro plano: ajusta o alvo de qualidade ao que o atleta SUSTENTA,
    com evidência real. Vazio quando não há viés sistemático."""

    if not verdict.adjust:

        return ""

    secs = abs(round(verdict.bias_sec))

    if verdict.bias_sec > 0:

        return (
            f"CALIBRAÇÃO DE PACE (evidência real: {verdict.samples} tiros): o "
            f"atleta vem correndo os tiros ~{secs}s/km MAIS DEVAGAR que o ritmo "
            "prescrito — o alvo de qualidade está agressivo demais. Prescreva a "
            "qualidade no ritmo que ele SUSTENTA hoje (afrouxe o alvo ~"
            f"{secs}s/km). Regra de ouro: ritmo que ele não sustenta não treina "
            "— só cansa e arrisca lesão."
        )

    return (
        f"CALIBRAÇÃO DE PACE (evidência real: {verdict.samples} tiros): o atleta "
        f"vem batendo os tiros ~{secs}s/km MAIS RÁPIDO que o prescrito, com "
        "folga — dá pra APERTAR um pouco o ritmo-alvo de qualidade (progressão "
        "com critério, um passo por vez), que ele comporta."
    )
