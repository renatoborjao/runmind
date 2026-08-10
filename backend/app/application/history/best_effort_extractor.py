"""Extrai o MELHOR ESFORÇO CONTÍNUO de dentro de uma corrida, a partir dos
streams (distância acumulada + tempo decorrido) — a janela SUSTENTADA mais
rápida de cada distância-alvo (o "fastest 1 mile / 3k / 5k" que o Strava
calcula no servidor, feito por nós).

É a versão NATIVA (Garmin) da âncora contínua de VDOT: até aqui ela só existia
via `best_efforts` do Strava ([[best_effort_refresh]]). Com isto o teto de
capacidade sai direto do relógio — captura o tiro/tempo que a MÉDIA da corrida
dilui, sem depender do Strava (ver [[project_independencia_strava]]) e sem
esperar uma prova. Puro/determinístico. Ver [[project_modelo_pace_vdot]]."""

# distâncias-alvo (m): 1 milha pra cima. O BestEffortVdot já filtra pro que
# ancora bem o VDOT (≥3km, fallback ≥1600m); abaixo de 1600m é anaeróbico
# demais e superestimaria — por isso nem geramos janela mais curta que isso.
_TARGETS = (1609, 2000, 3000, 5000, 10000)


class BestEffortExtractor:

    @staticmethod
    def efforts(
        distance: list,
        time: list,
        targets: tuple[int, ...] = _TARGETS,
    ) -> list[dict]:
        """Pra cada distância-alvo, acha a janela CONTÍNUA mais rápida (menor
        tempo pra cobrir ≥ alvo) deslizando pelos streams. Devolve
        [{distance, elapsed_time}] no formato que [[best_effort_vdot]] consome.

        `distance` = metros acumulados; `time` = segundos decorridos (arrays
        paralelos). Robusto a tamanhos diferentes, a buracos (None) e a
        amostragem NÃO-uniforme (usa o tempo real de cada amostra, nunca supõe
        1s)."""

        points = BestEffortExtractor._clean(distance, time)

        if len(points) < 2:

            return []

        out = []

        for target in targets:

            window = BestEffortExtractor._fastest_window(points, target)

            if window is not None:

                out.append(window)

        return out

    @staticmethod
    def _clean(distance: list, time: list) -> list[tuple[float, float]]:
        """Pares (t, d) válidos e monotônicos: descarta None e amostras que
        recuam (jitter) — numa corrida a distância acumulada só cresce."""

        n = min(len(distance), len(time))

        points: list[tuple[float, float]] = []

        last_d = None

        last_t = None

        for i in range(n):

            d = distance[i]

            t = time[i]

            if d is None or t is None:

                continue

            d = float(d)

            t = float(t)

            # só avança: distância não pode recuar, tempo não pode voltar
            if (last_d is None or d >= last_d) and (last_t is None or t >= last_t):

                points.append((t, d))

                last_d = d

                last_t = t

        return points

    @staticmethod
    def _fastest_window(
        points: list[tuple[float, float]],
        target: int,
    ) -> dict | None:
        """Janela deslizante O(n): menor (t_j − t_i) com (d_j − d_i) ≥ target.
        Para cada início i, o PRIMEIRO j que cobre o alvo dá o tempo mínimo
        (esticar j além só adiciona tempo); e o j mínimo é monotônico em i, daí
        um único ponteiro pros dois laços."""

        best_time = None

        best_dist = None

        n = len(points)

        j = 0

        for i in range(n):

            if j < i:

                j = i

            while j < n and points[j][1] - points[i][1] < target:

                j += 1

            if j >= n:

                break

            dt = points[j][0] - points[i][0]

            dd = points[j][1] - points[i][1]

            if dt > 0 and (best_time is None or dt < best_time):

                best_time = dt

                best_dist = dd

        if best_time is None:

            return None

        return {"distance": best_dist, "elapsed_time": best_time}
