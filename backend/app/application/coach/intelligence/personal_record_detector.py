"""Celebração de PR/marcos: depois de cada treino concluído, verifica se o
atleta bateu um recorde real (corrida mais longa, treino mais rápido numa
faixa de distância, marco de km acumulado, semana de maior volume) e devolve
UMA mensagem comemorativa (ou None). NUNCA muda o plano — é puro
reconhecimento, igual pra atleta RunMind ou de treinador externo.

Fonte dos dados = SEMPRE Strava, nunca Garmin — mesmo pra quem tem Garmin
conectado (a análise detalhada do treino em si — splits, tiros — continua via
Garmin, isso não muda). Hoje Strava é obrigatório no onboarding pra todo
atleta, então é o único "livro de recordes" único e consistente entre todos;
quem por algum motivo não tem Strava conectado simplesmente não recebe
celebração (silêncio, não erro).

Cold start: sem uma base prévia, TUDO seria "recorde" na primeira comparação.
`seed()` resolve isso na hora da conexão do Strava (onboarding ou late
connector) — carrega o histórico real e estabelece a base ANTES do primeiro
treino de verdade, pra ele já poder comparar (e comemorar) direito. Sem essa
chamada explícita, `after_feedback` também semeia sozinho na primeira vez
que rodar — mas aí o primeiro treino processado é sempre "gasto" só
semeando, nunca comemorando."""

from app.application.history.runner_metrics import (
    RUN_MIN_DISTANCE_KM,
    WALK_PACE_CUTOFF,
)
from app.application.history.weekly_buckets import group_by_week
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.activity import Activity
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import is_foot_sport
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)
from app.infrastructure.storage.token_store import TokenStore

_LONGEST_MIN_KM = 3.0

# esportes que contam como CORRIDA de verdade pra corrida-mais-longa e
# pace-PR — caminhada/trilha caminhada (Walk/Hike) entram no volume total,
# mas não competem por recorde de corrida.
_RUN_SPORTS = {"Run", "TrailRun", "VirtualRun"}

_BANDS = [
    (3.0, 5.0, "3-5"),
    (5.0, 8.0, "5-8"),
    (8.0, 12.0, "8-12"),
    (12.0, 18.0, "12-18"),
    (18.0, None, "18+"),
]

# margem mínima pra contar como PR de pace (evita disparo por ruído de GPS
# ou micro-melhora imperceptível): ~3s/km
_PACE_MARGIN_MIN_KM = 0.05

_KM_MILESTONES = [100, 250, 500, 1000, 1500, 2000, 3000, 5000]

# quantas atividades recentes buscar no Strava (o máximo por página da API);
# cobre "vida" na prática pro público atual do produto sem paginar.
_STRAVA_HISTORY_LIMIT = 200


class PersonalRecordDetector:

    @staticmethod
    async def seed(profile: str) -> None:
        """Estabelece a base de recordes a partir do histórico REAL do
        Strava, sem esperar um treino ser processado pelo RunMind. Chamado
        na conexão do Strava (onboarding e late connector). Não sobrescreve
        quem já tem base (reconexão não reseta o que já foi conquistado)."""

        if PersonalRecordRepository().load(profile).get("seeded"):

            return

        history = await PersonalRecordDetector._load_strava_history(profile)

        if history is None:

            return

        PersonalRecordRepository().save(
            profile,
            PersonalRecordDetector._seed(history),
        )

    @staticmethod
    async def after_feedback(
        runner: RunnerProfile,
    ) -> str | None:

        history = await PersonalRecordDetector._load_strava_history(
            runner.id,
        )

        if history is None:

            return None

        # a API do Strava devolve mais recente primeiro
        current = history.activities[0]

        repo = PersonalRecordRepository()

        records = repo.load(runner.id)

        if not records.get("seeded"):

            repo.save(
                runner.id,
                PersonalRecordDetector._seed(history),
            )

            return None

        wins: list[str] = []

        dist_km = current.distance / 1000

        # -- corrida mais longa ------------------------------------------
        longest_km = records.get("longest_km", 0.0)

        if (
            current.sport in _RUN_SPORTS
            and dist_km >= _LONGEST_MIN_KM
            and dist_km > longest_km
        ):

            wins.append(
                f"🏆 sua corrida mais longa até hoje: {dist_km:.1f} km!"
            )

            records["longest_km"] = round(dist_km, 2)

        # -- treino mais rápido na faixa -----------------------------------
        pace = PersonalRecordDetector._pace(current)

        band = PersonalRecordDetector._band(dist_km)

        if (
            current.sport in _RUN_SPORTS
            and band is not None
            and pace is not None
            and dist_km >= RUN_MIN_DISTANCE_KM
            and pace <= WALK_PACE_CUTOFF
        ):

            pace_by_band = records.setdefault("pace_by_band", {})

            best = pace_by_band.get(band)

            if best is None or best - pace >= _PACE_MARGIN_MIN_KM:

                wins.append(
                    "⚡ seu treino mais rápido na faixa de "
                    f"{band} km: pace {PaceFormatter.format(pace)}/km!"
                )

                pace_by_band[band] = round(pace, 2)

        # -- marco de km acumulado ------------------------------------------
        total_km = history.total_distance / 1000

        milestone_before = records.get("total_km_milestone", 0)

        crossed = [
            m for m in _KM_MILESTONES
            if milestone_before < m <= total_km
        ]

        if crossed:

            milestone = max(crossed)

            wins.append(f"🎉 você passou de {milestone} km com o RunMind!")

            records["total_km_milestone"] = milestone

        # -- semana de maior volume ------------------------------------------
        week_result = PersonalRecordDetector._week_record(
            history,
            records,
        )

        if week_result:

            wins.append(week_result)

        repo.save(runner.id, records)

        if not wins:

            return None

        return PersonalRecordDetector._message(runner.name, wins)

    @staticmethod
    async def _load_strava_history(profile: str) -> TrainingHistory | None:

        if TokenStore(profile).load() is None:

            return None

        activities = await StravaClient(profile).get_last_activities(
            limit=_STRAVA_HISTORY_LIMIT,
        )

        activities = [a for a in activities if is_foot_sport(a.sport)]

        if not activities:

            return None

        return TrainingHistory(activities=activities)

    @staticmethod
    def _seed(history: TrainingHistory) -> dict:

        records: dict = {"seeded": True}

        runs = [
            a for a in history.activities
            if a.sport in _RUN_SPORTS and a.distance / 1000 >= _LONGEST_MIN_KM
        ]

        if runs:

            records["longest_km"] = round(
                max(a.distance for a in runs) / 1000,
                2,
            )

        pace_by_band: dict[str, float] = {}

        for activity in history.activities:

            dist_km = activity.distance / 1000

            pace = PersonalRecordDetector._pace(activity)

            band = PersonalRecordDetector._band(dist_km)

            if (
                activity.sport not in _RUN_SPORTS
                or band is None
                or pace is None
                or dist_km < RUN_MIN_DISTANCE_KM
                or pace > WALK_PACE_CUTOFF
            ):

                continue

            if band not in pace_by_band or pace < pace_by_band[band]:

                pace_by_band[band] = round(pace, 2)

        if pace_by_band:

            records["pace_by_band"] = pace_by_band

        total_km = history.total_distance / 1000

        crossed = [m for m in _KM_MILESTONES if m <= total_km]

        if crossed:

            records["total_km_milestone"] = max(crossed)

        buckets = group_by_week(history.activities)

        if buckets:

            best_key = max(buckets)

            best_km = sum(
                a.distance for a in buckets[best_key]
            ) / 1000

            records["best_week_km"] = round(best_km, 2)

            records["best_week_key"] = f"{best_key[0]}-W{best_key[1]:02d}"

        return records

    @staticmethod
    def _week_record(
        history: TrainingHistory,
        records: dict,
    ) -> str | None:

        buckets = group_by_week(history.activities)

        if not buckets:

            return None

        current_key = max(buckets)

        current_km = sum(
            a.distance for a in buckets[current_key]
        ) / 1000

        current_key_str = f"{current_key[0]}-W{current_key[1]:02d}"

        best_km = records.get("best_week_km", 0.0)

        best_key = records.get("best_week_key")

        if current_km <= best_km:

            return None

        # bate o recorde de sempre; a mensagem só sai UMA vez por semana —
        # runs seguintes na MESMA semana continuam atualizando o valor por
        # baixo dos panos, sem repetir a comemoração.
        already_this_week = current_key_str == best_key

        records["best_week_km"] = round(current_km, 2)

        records["best_week_key"] = current_key_str

        if already_this_week:

            return None

        return f"📈 sua semana de maior volume: {current_km:.1f} km!"

    @staticmethod
    def _pace(activity: Activity) -> float | None:

        if activity.average_speed <= 0:

            return None

        return (1000 / activity.average_speed) / 60

    @staticmethod
    def _band(dist_km: float) -> str | None:

        for low, high, label in _BANDS:

            if high is None:

                if dist_km >= low:

                    return label

            elif low <= dist_km < high:

                return label

        return None

    @staticmethod
    def _message(name: str, wins: list[str]) -> str:

        if len(wins) == 1:

            return f"{name}, {wins[0]}"

        lines = "\n".join(f"- {w}" for w in wins)

        return f"{name}, você bateu {len(wins)} recordes hoje:\n{lines}"
