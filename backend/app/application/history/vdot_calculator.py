"""VDOT (Jack Daniels) — a ciência que traduz um DESEMPENHO REAL do atleta em
ritmos de treino (E/M/T/I/R). Puro/determinístico, sem IA, sem chute.

O VDOT é um VO2máx "efetivo" estimado de uma corrida real: dado quanto o atleta
correu e em quanto tempo, sai a intensidade que o corpo dele sustentou. Dele
derivam os ritmos por %VO2máx — todos ancorados no que ele JÁ fez, logo
sustentáveis por definição (nunca um pace aspiracional que ele não aguenta).

Fórmulas do Daniels (domínio público, "Daniels' Running Formula"):
  %VO2máx(t) = 0.8 + 0.1894393·e^(−0.012778·t) + 0.2989558·e^(−0.1932605·t)
  VO2(v)     = −4.60 + 0.182258·v + 0.000104·v²        (v em m/min, t em min)
  VDOT       = VO2(v) / %VO2máx(t)

Ver [[project_pace_so_corrida]] e [[project_renato_perfil_real]]."""

import math

# coeficientes de VO2(v) — a curva custo-de-oxigênio por velocidade
_A = 0.000104
_B = 0.182258
_C = -4.60

# %VO2máx por FAIXA de treino (guia do Daniels). São as intensidades onde cada
# estímulo mora — o pace sai invertendo VO2(v) na fração·VDOT correspondente.
FRAC_EASY_SLOW = 0.62   # ponta lenta do fácil (recuperação/base bem tranquila)
FRAC_EASY_FAST = 0.72   # ponta rápida do fácil (ainda aeróbico, dá pra conversar)
FRAC_MARATHON = 0.82    # ritmo de prova longa / maratona
FRAC_THRESHOLD = 0.88   # limiar ("confortavelmente difícil", ~1h de prova)
FRAC_INTERVAL = 0.975   # intervalado / VO2máx (tiros de 3–5 min)
FRAC_REP = 1.05         # ritmo forte / repetição (tiros curtos, economia)


class VdotCalculator:

    @staticmethod
    def vdot(distance_m: float, seconds: float) -> float:
        """VDOT de um esforço real (distância em metros, tempo em segundos)."""

        if distance_m <= 0 or seconds <= 0:

            raise ValueError("distância e tempo precisam ser positivos")

        minutes = seconds / 60.0

        velocity = distance_m / minutes  # m/min

        pct = (
            0.8
            + 0.1894393 * math.exp(-0.012778 * minutes)
            + 0.2989558 * math.exp(-0.1932605 * minutes)
        )

        vo2 = _C + _B * velocity + _A * velocity * velocity

        return vo2 / pct

    @staticmethod
    def pace_min_km(vdot_value: float, fraction: float) -> float:
        """Ritmo (min/km) que o atleta sustenta na `fraction` do VDOT dele —
        inverte VO2(v) resolvendo a quadrática pra velocidade e converte a
        pace. `fraction` é uma das FRAC_* (fácil, limiar, VO2, etc.)."""

        target_vo2 = fraction * vdot_value

        # 0.000104·v² + 0.182258·v − (4.60 + target_vo2) = 0 → raiz positiva
        c = _C - target_vo2

        discriminant = _B * _B - 4 * _A * c

        velocity = (-_B + math.sqrt(discriminant)) / (2 * _A)  # m/min

        return 1000.0 / velocity  # min/km
