"""Celebração de PR/marcos: depois de cada treino concluído, verifica se o
atleta bateu um recorde REAL de corredor (corrida mais longa, treino mais
rápido numa faixa de distância) e devolve UMA mensagem comemorativa (ou
None). NUNCA muda o plano — é puro reconhecimento, igual pra atleta RunMind
ou de treinador externo.

Decisão do Renato: "km acumulado" e "semana de maior volume" NÃO são
recordes de corredor de verdade (ninguém comemora "passei de 500km" como
comemora um PR de tempo) — continuam sendo RASTREADOS (o recap mensal usa
essas duas métricas), mas não geram mais mensagem depois de cada treino.

Fonte dos dados = SEMPRE Strava, nunca Garmin — mesmo pra quem tem Garmin
conectado (a análise detalhada do treino em si — splits, tiros — continua via
Garmin, isso não muda). Hoje Strava é obrigatório no onboarding pra todo
atleta, então é o único "livro de recordes" único e consistente entre todos;
quem por algum motivo não tem Strava conectado simplesmente não recebe
celebração (silêncio, não erro).

Verificação ao vivo busca só um punhado de atividades recentes (não as 200
inteiras) — os dois recordes de verdade (corrida mais longa, pace por faixa)
só precisam da atividade mais nova comparada com o que já está gravado; os
dois contadores agregados (km acumulado, semana atual) são incrementados em
cima do valor já persistido, nunca resomados do zero.

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
from app.application.history.weekly_buckets import (
    activity_date,
    group_by_week,
)
from app.application.planner.pace_formatter import PaceFormatter
from app.domain.entities.activity import Activity
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.sports import RUN_SPORTS, is_foot_sport
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.personal_record_repository import (
    PersonalRecordRepository,
)
from app.infrastructure.storage.token_store import TokenStore

_LONGEST_MIN_KM = 3.0

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

# quantas atividades recentes buscar no Strava pro COLD-START (seed): o
# máximo por página da API, cobre "vida" na prática pro público atual do
# produto sem paginar.
_STRAVA_HISTORY_LIMIT = 200

# quantas atividades recentes buscar no caminho AO VIVO (after_feedback):
# só precisa achar a atividade mais nova que seja de pé (corrida/caminhada);
# folga pequena cobre o caso raro de outro esporte ter sido sincronizado
# entre o treino e o processamento, sem pagar o custo de buscar 200.
_RECENT_ACTIVITY_LOOKBACK = 5


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
            PersonalRecordDetector.compute_bests(history),
        )

    @staticmethod
    async def after_feedback(
        runner: RunnerProfile,
    ) -> str | None:

        current = await PersonalRecordDetector._load_current_activity(
            runner.id,
        )

        if current is None:

            return None

        repo = PersonalRecordRepository()

        records = repo.load(runner.id)

        if not records.get("seeded"):

            history = await PersonalRecordDetector._load_strava_history(
                runner.id,
            )

            if history is None:

                return None

            repo.save(
                runner.id,
                PersonalRecordDetector.compute_bests(history),
            )

            return None

        wins: list[str] = []

        dist_km = current.distance / 1000

        current_date = activity_date(current).isoformat()

        # -- corrida mais longa ------------------------------------------
        longest_km = records.get("longest_km", 0.0)

        if (
            current.sport in RUN_SPORTS
            and dist_km >= _LONGEST_MIN_KM
            and dist_km > longest_km
        ):

            wins.append(
                f"🏆 sua corrida mais longa até hoje: {dist_km:.1f} km!"
            )

            records["longest_km"] = round(dist_km, 2)

            records["longest_km_date"] = current_date

        # -- treino mais rápido na faixa -----------------------------------
        pace = PersonalRecordDetector._pace(current)

        band = PersonalRecordDetector._band(dist_km)

        if (
            current.sport in RUN_SPORTS
            and band is not None
            and pace is not None
            and dist_km >= RUN_MIN_DISTANCE_KM
            and pace <= WALK_PACE_CUTOFF
        ):

            pace_by_band = records.setdefault("pace_by_band", {})

            pace_by_band_dates = records.setdefault("pace_by_band_dates", {})

            best = pace_by_band.get(band)

            if best is None or best - pace >= _PACE_MARGIN_MIN_KM:

                wins.append(
                    "⚡ seu treino mais rápido na faixa de "
                    f"{band} km: pace {PaceFormatter.format(pace)}/km!"
                )

                pace_by_band[band] = round(pace, 2)

                pace_by_band_dates[band] = current_date

        # -- km acumulado + semana atual (NUNCA celebrados aqui — só
        # alimentam o recap mensal; guard por id evita contar a mesma
        # atividade 2x se o webhook/poller reprocessar) -------------------
        if records.get("last_accumulated_activity_id") != current.id:

            PersonalRecordDetector._accumulate_total_km(
                records, dist_km, current_date,
            )

            PersonalRecordDetector._accumulate_current_week(
                records, current, dist_km,
            )

            records["last_accumulated_activity_id"] = current.id

        repo.save(runner.id, records)

        if not wins:

            return None

        return PersonalRecordDetector._message(runner.name, wins)

    @staticmethod
    async def _load_current_activity(profile: str) -> Activity | None:
        """Busca só um punhado de atividades recentes (não as 200 do
        cold-start) e devolve a mais nova que seja de pé — o suficiente pro
        caminho ao vivo, que só compara/incrementa contra o que já está
        gravado, nunca resoma o histórico inteiro."""

        if TokenStore(profile).load() is None:

            return None

        activities = await StravaClient(profile).get_last_activities(
            limit=_RECENT_ACTIVITY_LOOKBACK,
        )

        return next(
            (a for a in activities if is_foot_sport(a.sport)),
            None,
        )

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
    def _accumulate_total_km(
        records: dict,
        dist_km: float,
        current_date: str,
    ) -> None:
        """Km acumulado: soma incremental (nunca resoma do Strava). Fica
        gravado só pro recap mensal usar — não é celebrado aqui."""

        total = records.get("total_km_accumulated", 0.0) + dist_km

        records["total_km_accumulated"] = round(total, 2)

        milestone_before = records.get("total_km_milestone", 0)

        crossed = [
            m for m in _KM_MILESTONES
            if milestone_before < m <= total
        ]

        if crossed:

            records["total_km_milestone"] = max(crossed)

            # só datado no caminho AO VIVO — cruzar um marco acumulado não
            # tem "dono" de uma atividade só; no seed não dá pra atribuir
            # direito, então melhor não datar do que datar errado.
            records["total_km_milestone_date"] = current_date

    @staticmethod
    def _accumulate_current_week(
        records: dict,
        current: Activity,
        dist_km: float,
    ) -> None:
        """Semana atual: soma incremental por semana ISO (nunca resoma do
        Strava); atualiza o recorde de sempre em silêncio quando bate. Fica
        gravado só pro recap mensal usar — não é celebrado aqui."""

        week_key = activity_date(current).isocalendar()[:2]

        week_key_str = f"{week_key[0]}-W{week_key[1]:02d}"

        if records.get("current_week_key") == week_key_str:

            records["current_week_km"] = round(
                records.get("current_week_km", 0.0) + dist_km, 2,
            )

        else:

            records["current_week_key"] = week_key_str

            records["current_week_km"] = round(dist_km, 2)

        if records["current_week_km"] > records.get("best_week_km", 0.0):

            records["best_week_km"] = records["current_week_km"]

            records["best_week_key"] = week_key_str

    @staticmethod
    def compute_bests(history: TrainingHistory) -> dict:
        """Calcula as melhores marcas a partir de um histórico — usado tanto
        pro cold-start (`seed`/primeira chamada de `after_feedback`) quanto
        pelo recap mensal, que compara os bests até o fim de um mês vs até o
        fim do anterior pra saber o que foi batido NAQUELE mês."""

        records: dict = {"seeded": True}

        runs = [
            a for a in history.activities
            if a.sport in RUN_SPORTS and a.distance / 1000 >= _LONGEST_MIN_KM
        ]

        if runs:

            longest = max(runs, key=lambda a: a.distance)

            records["longest_km"] = round(longest.distance / 1000, 2)

            records["longest_km_date"] = activity_date(longest).isoformat()

        pace_by_band: dict[str, float] = {}

        pace_by_band_dates: dict[str, str] = {}

        for activity in history.activities:

            dist_km = activity.distance / 1000

            pace = PersonalRecordDetector._pace(activity)

            band = PersonalRecordDetector._band(dist_km)

            if (
                activity.sport not in RUN_SPORTS
                or band is None
                or pace is None
                or dist_km < RUN_MIN_DISTANCE_KM
                or pace > WALK_PACE_CUTOFF
            ):

                continue

            if band not in pace_by_band or pace < pace_by_band[band]:

                pace_by_band[band] = round(pace, 2)

                pace_by_band_dates[band] = activity_date(activity).isoformat()

        if pace_by_band:

            records["pace_by_band"] = pace_by_band

            records["pace_by_band_dates"] = pace_by_band_dates

        total_km = history.total_distance / 1000

        # contador incremental (pro caminho ao vivo nunca mais precisar
        # resomar do Strava) — a base é literalmente o total já conhecido
        records["total_km_accumulated"] = round(total_km, 2)

        crossed = [m for m in _KM_MILESTONES if m <= total_km]

        if crossed:

            records["total_km_milestone"] = max(crossed)

        buckets = group_by_week(history.activities)

        if buckets:

            # semana mais recente = ponto de partida do contador "em
            # andamento" (current_week_km), que o caminho ao vivo só
            # incrementa a partir daqui, nunca resoma do zero
            latest_key = max(buckets)

            latest_km = sum(
                a.distance for a in buckets[latest_key]
            ) / 1000

            records["current_week_km"] = round(latest_km, 2)

            records["current_week_key"] = (
                f"{latest_key[0]}-W{latest_key[1]:02d}"
            )

            # recorde de sempre = a semana de MAIOR volume no histórico
            # todo, não necessariamente a mais recente
            best_key = max(
                buckets, key=lambda k: sum(a.distance for a in buckets[k]),
            )

            best_km = sum(
                a.distance for a in buckets[best_key]
            ) / 1000

            records["best_week_km"] = round(best_km, 2)

            records["best_week_key"] = f"{best_key[0]}-W{best_key[1]:02d}"

        return records

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
