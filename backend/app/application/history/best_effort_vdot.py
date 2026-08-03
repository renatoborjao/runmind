"""VDOT do melhor esforço CONTÍNUO (não da média da corrida). Os 'best_efforts'
do Strava dão o trecho sustentado mais rápido de cada corrida (1k/1milha/5k...);
deles sai um VDOT que reflete a CAPACIDADE real — captura o tempo/tiro que a
média dilui. Puro. Ver [[project_modelo_pace_vdot]] (âncora contínua)."""

from app.application.history.vdot_calculator import VdotCalculator

# só esforços SUSTENTADOS ancoram bem o VDOT: <1600m (400m/800m) é anaeróbico
# demais e superestima; preferimos ≥3km, com fallback pra 1 milha.
_MIN_SUSTAINED = 3000
_MIN_FALLBACK = 1600
_MAX = 10000


class BestEffortVdot:

    @staticmethod
    def from_efforts(efforts: list[dict]) -> float | None:
        """Maior VDOT entre os melhores esforços sustentados (≥3km; se não
        houver, ≥1 milha). None sem esforço utilizável."""

        return BestEffortVdot._best(efforts, _MIN_SUSTAINED) or BestEffortVdot._best(
            efforts, _MIN_FALLBACK
        )

    @staticmethod
    def _best(efforts: list[dict], min_dist: int) -> float | None:

        vdots = []

        for e in efforts:

            dist = e.get("distance") or 0

            secs = e.get("elapsed_time") or e.get("moving_time") or 0

            if min_dist <= dist <= _MAX and secs > 0:

                try:

                    vdots.append(VdotCalculator.vdot(dist, secs))

                except Exception:

                    continue

        return max(vdots) if vdots else None
