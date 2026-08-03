"""Atualiza os INSIGHTS por corrida que dependem do detalhe do Strava (não vêm
no arquivo): (1) o VDOT do melhor esforço CONTÍNUO (best_efforts) — a âncora
contínua do pace; (2) a FORMA-SOB-FADIGA (a cadência quebrou no fim?) — sinal
precoce de risco de lesão. Pega as corridas recentes ainda não vistas por CADA
sinal, baixa o detalhe e atualiza. Só corridas NOVAS (dedup por id) e com teto
por rodada (rate limit). Best-effort. Ver [[project_modelo_pace_vdot]]."""

from app.application.history.best_effort_vdot import BestEffortVdot
from app.application.history.form_fatigue_analyzer import FormFatigueAnalyzer
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.best_effort_vdot_store import (
    BestEffortVdotStore,
)
from app.infrastructure.persistence.form_fatigue_store import FormFatigueStore


class BestEffortRefresh:

    @staticmethod
    async def refresh(profile: str, limit: int = 15) -> None:
        """Processa até `limit` corridas recentes ainda não vistas. Silencioso:
        sem token do Strava / falha de rede simplesmente não atualiza."""

        try:

            client = StravaClient(profile)

            activities = await client.get_last_activities(limit=30)

        except Exception as e:

            print(f"Insight refresh (lista) falhou p/ '{profile}': {e}")

            return

        vdot_store = BestEffortVdotStore()

        fade_store = FormFatigueStore()

        vdot_seen = vdot_store.processed_ids(profile)

        fade_seen = fade_store.processed_ids(profile)

        processed = 0

        for activity in activities:

            if processed >= limit:

                break

            if not is_run_sport(activity.sport):

                continue

            did = False

            if activity.id not in vdot_seen:

                did = await BestEffortRefresh._do_vdot(
                    client, vdot_store, profile, activity.id
                ) or did

            if activity.id not in fade_seen:

                did = await BestEffortRefresh._do_fade(
                    client, fade_store, profile, activity.id
                ) or did

            if did:

                processed += 1

    @staticmethod
    async def _do_vdot(client, store, profile, activity_id) -> bool:

        try:

            efforts = await client.get_activity_best_efforts(activity_id)

            store.update(profile, activity_id, BestEffortVdot.from_efforts(efforts))

            return True

        except Exception as e:

            print(f"Best-effort (detalhe {activity_id}) falhou p/ '{profile}': {e}")

            return False

    @staticmethod
    async def _do_fade(client, store, profile, activity_id) -> bool:

        try:

            streams = await client.get_activity_streams(activity_id)

            faded = FormFatigueAnalyzer.fades(
                streams.get("cadence") or [], streams.get("distance") or [],
            )

            store.record(profile, activity_id, faded)

            return True

        except Exception as e:

            print(f"Forma-sob-fadiga ({activity_id}) falhou p/ '{profile}': {e}")

            return False
