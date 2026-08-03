"""Forma-sob-fadiga: a cadência DESABA no fim do treino? Quando o atleta cansa e
a passada quebra (cadência cai, ele começa a arrastar/afundar no chão), o risco
de lesão sobe — é um dos sinais mais PRECOCES de que passou do ponto. Puro:
recebe a série de cadência do Strava e diz se houve queda relevante no fim.
Ver [[project_ideias_produto]] item 27 e o alerta de lesão (#6)."""

from statistics import median

# distância mínima pra a fadiga fazer sentido (num treino curto não há fade)
_MIN_DISTANCE_M = 6000

# amostras válidas mínimas pra arriscar a leitura
_MIN_SAMPLES = 60

# queda relativa da cadência do fim vs o começo que já conta como "quebra"
# (~4% ≈ ~7 passos/min em 170 — o atleta arrastando no fim)
_FADE_DROP = 0.04


class FormFatigueAnalyzer:

    @staticmethod
    def fades(cadence: list, distance: list | None = None) -> bool:
        """True se a cadência do ÚLTIMO quarto caiu ≥ _FADE_DROP vs a dos
        primeiros 60% — sinal de forma quebrando sob fadiga. Ignora amostras
        zeradas (parado/sem dado). False sem distância/amostras suficientes."""

        if distance and distance[-1] and distance[-1] < _MIN_DISTANCE_M:

            return False

        valid = [c for c in cadence if c and c > 0]

        if len(valid) < _MIN_SAMPLES:

            return False

        cut_early = int(len(valid) * 0.6)

        cut_late = int(len(valid) * 0.75)

        early = median(valid[:cut_early])

        late = median(valid[cut_late:])

        if early <= 0:

            return False

        return late < early * (1 - _FADE_DROP)
