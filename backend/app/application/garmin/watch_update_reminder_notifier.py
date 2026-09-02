"""Rede de segurança do relógio: o atleta pediu uma mudança no treino
(mudar ritmo, mover, encurtar), o coach ofereceu mandar a versão nova pro Garmin
("responde *sim*") — e ele NÃO respondeu (nem sim nem não; só seguiu a vida). A
mudança ficou salva no plano, mas o RELÓGIO seguiu com a versão antiga, e isso
se perderia calado até a oferta expirar (48h). O atleta muitas vezes nem sabe
que faltou confirmar.

Aqui o coach VOLTA e cobra — UMA vez por oferta (orientar-não-repetir): "ó, o
ajuste que você pediu no [longão de sábado] ainda não subiu pro teu relógio,
quer que eu mande? responde sim". Só dispara quando o relógio está DE FATO
desatualizado (confere o plano atual contra o snapshot do que foi empurrado);
se já sincronizou por outro caminho, encerra a oferta em silêncio.

Roda de hora em hora; cada _notify_one decide se é o horário local e se a oferta
já teve tempo de ser respondida no fluxo natural. Passa pelo governador de
proativos ([[ProactiveGovernor]]) como extra. Ver [[GarminOfferStore]] e
[[feedback_conversa_viva]] (falha nunca vira silêncio)."""

from app.application.notifications.coach_outbox import CoachOutbox
from app.application.planner.weekly_plan_matcher import WeeklyPlanMatcher
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.application.use_cases.load_training_history import (
    LoadTrainingHistory,
)
from app.core.clock import now_in, today_local, use_athlete_timezone
from app.core.weekdays import weekday_label
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.runner_profile import RunnerProfile
from app.domain.entities.training_plan import TrainingPlan
from app.infrastructure.integrations.garmin.garmin_client import GarminClient
from app.infrastructure.integrations.garmin.garmin_offer_store import (
    GarminOfferStore,
)
from app.infrastructure.integrations.garmin.one_off_offer_store import (
    OneOffOfferStore,
)
from app.infrastructure.persistence.pushed_plan_store import PushedPlanStore
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

# janela de horas locais em que o lembrete pode sair (nada de ping às 3h)
_MIN_HOUR = 8
_MAX_HOUR = 21

# quanto a oferta precisa ter "descansado" antes de cobrar: dá tempo do atleta
# responder "sim" no próprio fluxo da conversa antes de a gente insistir
_REMIND_AFTER_SECONDS = 3 * 3600

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class WatchUpdateReminderNotifier:

    @staticmethod
    async def notify_all() -> None:

        for profile in RunnerProfileRepository().list_all():

            try:

                await WatchUpdateReminderNotifier._notify_one(profile)

            except Exception as e:

                print(f"Falha no lembrete de relógio de '{profile}': {e}")

    @staticmethod
    async def _notify_one(profile: str) -> None:

        weekly_due = GarminOfferStore.reminder_due(
            profile, _REMIND_AFTER_SECONDS
        )

        oneoff_due = OneOffOfferStore.reminder_due(
            profile, _REMIND_AFTER_SECONDS
        )

        # nenhuma oferta pendente madura o bastante pra cobrar
        if not weekly_due and not oneoff_due:

            return

        # relógio desconectado no meio-tempo: não há o que sincronizar
        if not GarminClient.is_connected(profile):

            GarminOfferStore.clear(profile)

            OneOffOfferStore.clear(profile)

            return

        runner = LoadRunnerProfile.execute(profile)

        use_athlete_timezone(runner.timezone)

        if not (_MIN_HOUR <= now_in(runner.timezone).hour <= _MAX_HOUR):

            return

        external = getattr(runner, "external_coach", False)

        # 1) mudança na SEMANA (não se aplica a treinador externo — o plano é
        # do treinador dele). Um envio por tick; se mandou aqui, o avulso fica
        # pro próximo (não empilha ping).
        if weekly_due and not external:

            if await WatchUpdateReminderNotifier._remind_weekly(profile, runner):

                return

        elif weekly_due and external:

            GarminOfferStore.clear(profile)  # oferta órfã: externo não tem plano nosso

        # 2) treino AVULSO pendente (vale inclusive p/ treinador externo — o
        # avulso é NOSSO). Independe do snapshot do plano (é sessão à parte).
        if oneoff_due:

            await WatchUpdateReminderNotifier._remind_one_off(profile, runner)

    @staticmethod
    async def _remind_weekly(profile: str, runner: RunnerProfile) -> bool:
        """Lembra da mudança na semana se o relógio está mesmo defasado num
        treino futuro. Devolve True se mandou o lembrete."""

        current = WeeklyPlanRepository().load(profile)

        pushed = PushedPlanStore.load(profile)

        if current is None or pushed is None:

            return False

        # dias JÁ TREINADOS não precisam de push — cobrar pra subir um treino
        # que o atleta já correu não faz sentido (bug do Renato: cutucou a
        # quarta que ele já tinha feito, depois de o plano mudar). Best-effort:
        # sem histórico, não pula nada.
        done_days: set[str] = set()

        try:

            history = await LoadTrainingHistory.execute(profile=profile)

            done_days = {
                d.lower()
                for d in WeeklyPlanMatcher.fulfilled_days(
                    current, history.activities
                )
            }

        except Exception as e:

            print(f"Lembrete relógio: histórico falhou p/ '{profile}': {e}")

        stale = WatchUpdateReminderNotifier._stale_days(
            current, pushed, done_days
        )

        # o relógio já está em dia (sincronizou por outro caminho): encerra a
        # oferta sem incomodar — a falha se resolveu sozinha
        if not stale:

            GarminOfferStore.clear(profile)

            return False

        await CoachOutbox.send(
            runner,
            WatchUpdateReminderNotifier._message(runner.name, stale),
            profile=profile,
            kind="watch_update_reminder",
        )

        # UM lembrete por oferta; a oferta segue válida pro "sim" seguinte
        GarminOfferStore.mark_reminded(profile)

        return True

    @staticmethod
    async def _remind_one_off(profile: str, runner: RunnerProfile) -> None:
        """Lembra do treino avulso montado que não foi confirmado pro relógio."""

        on_date = OneOffOfferStore.pending_date(profile)

        # data passada / inválida: não adianta cobrar o relógio
        if on_date is None or on_date < today_local():

            OneOffOfferStore.clear(profile)

            return

        await CoachOutbox.send(
            runner,
            WatchUpdateReminderNotifier._one_off_message(runner.name, on_date),
            profile=profile,
            kind="watch_update_reminder",
        )

        OneOffOfferStore.mark_reminded(profile)

    @staticmethod
    def _stale_days(
        current: TrainingPlan,
        pushed: TrainingPlan,
        done_days: set[str] | None = None,
    ) -> list[str]:
        """Dias FUTUROS e AINDA NÃO TREINADOS cujo treino no plano atual difere
        do que está no relógio (snapshot empurrado) — ou que nem existiam no
        snapshot. É o que o atleta veria desatualizado no Garmin."""

        done = done_days or set()

        pushed_by_day = {s.day.lower(): s for s in pushed.sessions}

        today = today_local()

        stale = []

        for session in current.sessions:

            # já treinou esse dia: não faz sentido cobrar o push de um treino
            # que já foi feito (mesmo que o plano tenha mudado depois)
            if session.day.lower() in done:

                continue

            when = WatchUpdateReminderNotifier._session_date(current, session)

            # dia que já passou não adianta re-enviar
            if when is not None and when < today:

                continue

            other = pushed_by_day.get(session.day.lower())

            if other is None or WatchUpdateReminderNotifier._fingerprint(
                session
            ) != WatchUpdateReminderNotifier._fingerprint(other):

                stale.append(weekday_label(session.day))

        return stale

    @staticmethod
    def _session_date(plan: TrainingPlan, session: PlannedSession):

        offset = _WEEKDAY_INDEX.get(session.day.lower())

        if offset is None:

            return None

        from datetime import timedelta

        return plan.week_start + timedelta(days=offset)

    @staticmethod
    def _fingerprint(session: PlannedSession) -> tuple:

        return (
            session.workout_type,
            session.planned_distance_km,
            session.target_pace_min,
            session.target_pace_max,
            session.structure,
        )

    @staticmethod
    def _message(name: str, stale_days: list[str]) -> str:

        if len(stale_days) == 1:

            what = f"o ajuste que você pediu no treino de {stale_days[0]}"

        else:

            dias = ", ".join(stale_days[:-1]) + f" e {stale_days[-1]}"

            what = f"os ajustes que você pediu nos treinos de {dias}"

        return (
            f"Ei, {name}! Só pra não passar batido: {what} ficou salvo aqui, "
            "mas ainda **não subiu pro seu relógio** — faltou confirmar. Quer "
            "que eu mande a versão atualizada pro seu Garmin agora? Responde "
            "*sim* que eu envio. ⌚"
        )

    @staticmethod
    def _one_off_message(name: str, on_date) -> str:

        return (
            f"Ei, {name}! Aquele treino avulso de {on_date:%d/%m} que eu montei "
            "ficou aqui na conversa, mas **não chegou a ir pro seu relógio** — "
            "faltou confirmar. Quer que eu mande pro seu Garmin? Responde *sim* "
            "que eu envio. ⌚"
        )
