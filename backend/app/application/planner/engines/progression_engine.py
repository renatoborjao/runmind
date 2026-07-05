from app.domain.entities.runner_baseline import RunnerBaseline

# Consistência (0-100) que separa os ritmos de progressão.
HIGH_CONSISTENCY = 80
MID_CONSISTENCY = 50

# Teto de segurança: nunca passa muito do que o atleta já provou aguentar.
CAPACITY_CEILING = 1.10

# Semana de corte (deload) do ciclo 3:1.
DELOAD_FACTOR = 0.8

# Passos de subida (multiplicadores) por consistência. Com prova, o
# atleta pode subir um pouco mais; "Saúde" progride mais suave e estabiliza.
STEP_RACE = {"high": 1.10, "mid": 1.05, "low": 1.02}
STEP_HEALTH = {"high": 1.05, "mid": 1.03, "low": 1.02}

# "Não cumprida": semana em que o atleta fez menos da metade do plano.
# Regride só quando isso se repete (2+ semanas) — uma semana atípica
# isolada NÃO derruba o plano.
MISS_THRESHOLD = 0.5


class ProgressionEngine:
    """Decide o volume-alvo da próxima semana: parte do volume real
    recente e dá um passo guiado pela CONSISTÊNCIA e pela EXECUÇÃO das
    últimas semanas. Sempre evolui, mas com teto na capacidade provada."""

    @staticmethod
    def next_weekly_volume(
        baseline: RunnerBaseline,
        consistency: float,
        recent_adherence: list[float],
        has_race: bool,
        is_deload: bool = False,
    ) -> float:
        """`recent_adherence`: fração (0..1) das sessões cumpridas nas
        últimas semanas (cronológico, a mais recente por último). Vazio =
        sem semana anterior (1ª semana)."""

        anchor = baseline.weekly_km

        if anchor <= 0:

            return 0.0

        step = ProgressionEngine._step(
            baseline,
            consistency,
            recent_adherence,
            has_race,
        )

        target = anchor * step

        # nunca muito além da melhor semana real (evolução segura)
        ceiling = max(
            round(baseline.max_week_km * CAPACITY_CEILING, 1),
            anchor,
        )

        target = min(target, ceiling)

        if is_deload:

            target *= DELOAD_FACTOR

        return round(target, 1)

    @staticmethod
    def _step(
        baseline: RunnerBaseline,
        consistency: float,
        recent_adherence: list[float],
        has_race: bool,
    ) -> float:

        last = recent_adherence[-1] if recent_adherence else None

        # o loop semana-a-semana: a execução das últimas semanas manda.
        if last is not None and last < 1.0:

            last_two = recent_adherence[-2:]

            # regride SÓ com 2+ semanas seguidas não cumpridas
            if len(last_two) >= 2 and all(
                a < MISS_THRESHOLD for a in last_two
            ):

                return 0.90   # queda sustentada: recua pra recuperar

            return 1.0        # semana atípica isolada / parcial: segura

        # cumpriu tudo (ou 1ª semana): sobe conforme a consistência
        table = STEP_RACE if has_race else STEP_HEALTH

        if consistency >= HIGH_CONSISTENCY:

            step = table["high"]

        elif consistency >= MID_CONSISTENCY:

            step = table["mid"]

        else:

            step = table["low"]

        # tendência caindo: não força a subida
        if baseline.trend == "caindo":

            step = min(step, 1.0)

        return step
