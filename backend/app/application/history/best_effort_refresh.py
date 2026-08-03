"""Atualiza a marca-d'água do VDOT contínuo do atleta: pega as corridas recentes
ainda não processadas, baixa os best_efforts do Strava (o trecho sustentado mais
rápido de cada uma), calcula o VDOT e sobe o máximo. Só corridas NOVAS (dedup por
id) e com teto por rodada (respeita o rate limit). Best-effort — falhar aqui
nunca derruba nada. Ver [[project_modelo_pace_vdot]] (âncora contínua)."""

from app.application.history.best_effort_vdot import BestEffortVdot
from app.domain.value_objects.sports import is_run_sport
from app.infrastructure.integrations.strava.client import StravaClient
from app.infrastructure.persistence.best_effort_vdot_store import (
    BestEffortVdotStore,
)


class BestEffortRefresh:

    @staticmethod
    async def refresh(profile: str, limit: int = 15) -> None:
        """Processa até `limit` corridas recentes ainda não vistas. Silencioso:
        sem token do Strava / falha de rede simplesmente não atualiza."""

        try:

            client = StravaClient(profile)

            activities = await client.get_last_activities(limit=30)

        except Exception as e:

            print(f"Best-effort refresh (lista) falhou p/ '{profile}': {e}")

            return

        store = BestEffortVdotStore()

        seen = store.processed_ids(profile)

        processed = 0

        for activity in activities:

            if processed >= limit:

                break

            if not is_run_sport(activity.sport) or activity.id in seen:

                continue

            try:

                efforts = await client.get_activity_best_efforts(activity.id)

                vdot = BestEffortVdot.from_efforts(efforts)

                store.update(profile, activity.id, vdot)

                processed += 1

            except Exception as e:

                print(
                    f"Best-effort refresh (detalhe {activity.id}) falhou "
                    f"p/ '{profile}': {e}"
                )
