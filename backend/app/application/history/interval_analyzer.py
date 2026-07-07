import statistics

from app.domain.entities.interval_analysis import IntervalAnalysis

# Duração mínima (s) de um bloco pra não ser ruído de GPS.
MIN_BLOCK_SECONDS = 20

# Um tiro é um bloco de esforço curto: entre estes limites de distância.
# Acima do teto cai o AQUECIMENTO contínuo (não é tiro); abaixo do piso é
# ruído.
REP_MIN_METERS = 100
REP_MAX_METERS = 700

# Nº mínimo de tiros pra chamar de intervalado.
MIN_REPS = 3

# Portão de intensidade: oscilar de velocidade não basta (corrida-caminhada
# e rodagem com pausas também oscilam). Só é TIRO se houver resposta de FC
# de verdade (pico bem acima da recuperação) OU os trechos forem bem mais
# rápidos que a média do treino.
MIN_HR_SWING = 12  # bpm entre pico médio e recuperação média

MIN_PACE_CONTRAST = 0.12  # tiros ao menos 12% mais rápidos que a média


class IntervalAnalyzer:
    """Acha os tiros no stream (velocidade + FC) e mede a resposta de FC.
    Retorna None quando não há stream utilizável ou o treino não tem cara
    de intervalado — aí o resto do sistema segue pelos splits/km."""

    @staticmethod
    def analyze(
        velocity: list,
        heartrate: list,
        distance: list,
    ) -> IntervalAnalysis | None:

        if not velocity or not distance:

            return None

        moving = [v for v in velocity if v and v > 0.5]

        if len(moving) < 60:

            return None

        threshold = IntervalAnalyzer._threshold(moving)

        blocks = IntervalAnalyzer._blocks(velocity, threshold)

        reps = []

        recoveries = []

        for index, block in enumerate(blocks):

            is_work, start, end = block

            follows_recovery = (
                index + 1 < len(blocks)
                and not blocks[index + 1][0]
            )

            if is_work:

                meters = distance[end - 1] - distance[start]

                if (
                    follows_recovery
                    and REP_MIN_METERS <= meters <= REP_MAX_METERS
                ):

                    reps.append(
                        IntervalAnalyzer._rep(
                            velocity, heartrate, distance, start, end,
                        )
                    )

            elif reps:

                # recuperação depois do primeiro tiro
                recoveries.append((start, end))

        if len(reps) < MIN_REPS:

            return None

        peaks = [rep["peak_hr"] for rep in reps if rep["peak_hr"]]

        avg_peak_hr = int(round(statistics.mean(peaks))) if peaks else None

        recovery_hr = IntervalAnalyzer._recovery_hr(heartrate, recoveries)

        avg_rep_pace = round(
            statistics.mean(rep["pace"] for rep in reps),
            2,
        )

        # portão de intensidade: separa TIRO de corrida-caminhada/rodagem
        if not IntervalAnalyzer._is_real_effort(
            avg_rep_pace,
            avg_peak_hr,
            recovery_hr,
            moving,
        ):

            return None

        return IntervalAnalysis(
            rep_count=len(reps),
            avg_rep_pace=avg_rep_pace,
            avg_peak_hr=avg_peak_hr,
            avg_recovery_hr=recovery_hr,
            reps=reps,
        )

    @staticmethod
    def _is_real_effort(
        avg_rep_pace: float,
        avg_peak_hr: int | None,
        recovery_hr: int | None,
        moving: list[float],
    ) -> bool:
        """Tiro de verdade: FC de pico bem acima da recuperação OU trechos
        bem mais rápidos que a média do treino. Sem isso, é só oscilação de
        run-walk / pausa — não intervalado."""

        if (
            avg_peak_hr is not None
            and recovery_hr is not None
            and (avg_peak_hr - recovery_hr) >= MIN_HR_SWING
        ):

            return True

        overall_pace = (1000 / statistics.mean(moving)) / 60

        pace_contrast = (overall_pace - avg_rep_pace) / overall_pace

        return pace_contrast >= MIN_PACE_CONTRAST

    @staticmethod
    def _threshold(
        moving: list[float],
    ) -> float:
        """Ponto médio entre o ritmo de recuperação (p20) e o de esforço
        (p75): separa tiro de pausa mesmo com o velocity_smooth achatado."""

        quantiles = statistics.quantiles(moving, n=100)

        p20 = quantiles[19]

        p75 = quantiles[74]

        return (p20 + p75) / 2

    @staticmethod
    def _blocks(
        velocity: list,
        threshold: float,
    ) -> list[list]:
        """Segmenta em blocos [is_work, start, end], fundindo blocos curtos
        (ruído) no anterior."""

        flags = [bool(v and v >= threshold) for v in velocity]

        blocks = []

        i = 0

        n = len(flags)

        while i < n:

            j = i

            while j < n and flags[j] == flags[i]:

                j += 1

            blocks.append([flags[i], i, j])

            i = j

        return IntervalAnalyzer._merge_short(blocks)

    @staticmethod
    def _merge_short(
        blocks: list[list],
    ) -> list[list]:

        changed = True

        while changed and len(blocks) > 1:

            changed = False

            for k, block in enumerate(blocks):

                if (block[2] - block[1]) >= MIN_BLOCK_SECONDS:

                    continue

                if k > 0:

                    blocks[k - 1][2] = block[2]

                else:

                    blocks[k + 1][1] = block[1]

                del blocks[k]

                changed = True

                break

        return blocks

    @staticmethod
    def _rep(
        velocity: list,
        heartrate: list,
        distance: list,
        start: int,
        end: int,
    ) -> dict:

        speeds = [v for v in velocity[start:end] if v]

        avg_speed = statistics.mean(speeds)

        hrs = [h for h in heartrate[start:end] if h] if heartrate else []

        return {
            "distance_m": int(round(distance[end - 1] - distance[start])),
            "pace": round((1000 / avg_speed) / 60, 2),
            "peak_hr": int(max(hrs)) if hrs else None,
        }

    @staticmethod
    def _recovery_hr(
        heartrate: list,
        recoveries: list[tuple[int, int]],
    ) -> int | None:

        if not heartrate or not recoveries:

            return None

        values = []

        for start, end in recoveries:

            values += [h for h in heartrate[start:end] if h]

        if not values:

            return None

        return int(round(statistics.mean(values)))
