"""Renomeia o treino no Strava com o nome do NOSSO plano ("Tempo · 6 km") no
lugar do genérico do Strava ("Corrida matinal"). Best-effort ponta a ponta:

- gate por canário (strava_rename_active_for) + exige activity:write no token;
- só treinos que CASAM com uma sessão do plano (nunca corrida avulsa/prova);
- localiza a atividade NO STRAVA por data+distância (o id que chega no evento
  pode ser do Garmin, não do Strava — o treino sincroniza Garmin→Strava);
- só sobrescreve nome GENÉRICO do Strava (respeita nome que o atleta pôs à mão);
- idempotente: se já está com o nome certo, não bate na API.

Ver [[project_tracker_tenis]] (roadmap de escrita no Strava) e
[[feedback_free_tools_preference]]."""

import re

from app.application.coach.writer.labels import plan_session_title
from app.core.config import get_settings
from app.infrastructure.integrations.strava.client import StravaClient

# nomes automáticos do Strava = "{período} {esporte}" — só esses a gente
# sobrescreve (nome próprio do atleta fica intacto). PT + EN.
_SPORT_CUES = ("corrida", "caminhada", "run", "walk", "ride", "pedal")
_TIME_CUES = (
    "matinal", "manhã", "manha", "tarde", "noturna", "noite", "meio-dia",
    "meio dia", "almoço", "almoco", "morning", "afternoon", "evening",
    "night", "lunch", "midday",
)

# tolerâncias de casamento com a atividade do Strava
_DIST_TOLERANCE = 0.03          # 3% de diferença de distância
_TIME_WINDOW_SECONDS = 12 * 3600  # mesma corrida por Garmin/Strava difere ~3h


class StravaActivityRenamer:

    @staticmethod
    async def rename_to_plan(profile: str, activity, planned_session) -> bool:
        """Renomeia (best-effort) a corrida no Strava pro nome da sessão do
        plano. Devolve True se renomeou; False em qualquer outro caso (gate,
        sem sessão, sem match, nome não-genérico, sem permissão, erro)."""

        try:

            if not get_settings().strava_rename_active_for(profile):

                return False

            if planned_session is None or activity is None:

                return False

            name = StravaActivityRenamer._plan_name(planned_session)

            if not name:

                return False

            client = StravaClient(profile)

            target = await StravaActivityRenamer._find_on_strava(client, activity)

            if target is None:

                return False

            # respeita nome que o atleta deu à mão — só troca o genérico
            if not StravaActivityRenamer._is_generic(target.name):

                return False

            if (target.name or "").strip() == name:

                return False  # já está certo (idempotente)

            return await client.update_activity(target.id, name)

        except Exception as e:

            print(f"Renomear Strava falhou p/ '{profile}': {e}")

            return False

    # ------------------------------------------------------------------

    @staticmethod
    def _plan_name(session) -> str:
        """Nome do treino = o MESMO que foi pro relógio (Garmin), via a fonte
        única `plan_session_title`. Vazio quando a sessão não tem tipo."""

        if not (getattr(session, "workout_type", "") or "").strip():

            return ""

        return plan_session_title(session)

    @staticmethod
    async def _find_on_strava(client: StravaClient, activity):
        """Acha a atividade correspondente NO Strava (por distância ~igual +
        janela de tempo) — o evento pode trazer o id do Garmin. O match mais
        próximo no tempo vence. None se nada casar."""

        recent = await client.get_last_activities(limit=15)

        target_dist = activity.distance or 0

        target_ts = activity.start_date.timestamp()

        best = None

        best_gap = None

        for cand in recent:

            if not cand.distance or not target_dist:

                continue

            if abs(cand.distance - target_dist) / target_dist > _DIST_TOLERANCE:

                continue

            gap = abs(cand.start_date.timestamp() - target_ts)

            if gap > _TIME_WINDOW_SECONDS:

                continue

            if best_gap is None or gap < best_gap:

                best, best_gap = cand, gap

        return best

    @staticmethod
    def _is_generic(name: str | None) -> bool:
        """O nome é um automático do Strava ('Corrida matinal' / 'Morning Run')?
        Só esses a gente sobrescreve. Nome vazio também conta como genérico."""

        text = (name or "").strip().lower()

        if not text:

            return True

        # remove pontuação leve pra casar "meio-dia"/"meio dia"
        norm = re.sub(r"[^\wçãáéíóúâêô -]", " ", text)

        has_sport = any(cue in norm for cue in _SPORT_CUES)

        has_time = any(cue in norm for cue in _TIME_CUES)

        return has_sport and has_time
