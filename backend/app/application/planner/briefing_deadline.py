from datetime import date, datetime, time, timedelta

from app.domain.entities.activity import Activity
from app.domain.value_objects.sports import is_run_sport

# Antecedência do aviso em relação ao horário habitual de treino: o atleta tem
# que ler o treino ANTES de sair, não na porta. (O notificador decide no último
# tick antes do prazo, então chega 20–25 min antes.)
LEAD = timedelta(minutes=20)

# Janela de hábito: ~10 semanas — recente o bastante pra seguir a rotina atual.
LOOKBACK_DAYS = 70

# Mínimo de dias do MESMO dia da semana pra confiar no hábito daquele dia;
# abaixo disso, usa o hábito geral (todos os dias).
MIN_SAME_WEEKDAY = 3

NOON = 12 * 60


class BriefingDeadline:
    """Até quando o 'bom dia' pode ESPERAR o sono da noite antes de sair sem ele.

    O sono é o gatilho ideal (o atleta acordou e o relógio sincronizou), mas o
    sync pode atrasar — e o treino não espera. O prazo é pessoal: o horário em
    que o atleta costuma COMEÇAR a treinar naquele dia da semana, menos a
    antecedência. Quem corre 05h20 na terça tem prazo ~05h00; quem treina à
    tarde/noite não tem hábito de manhã e segue esperando o sono até o teto.

    Puro: recebe as atividades e o dia; quem chama carrega o arquivo."""

    @staticmethod
    def compute(
        activities: list[Activity],
        day: date,
        *,
        floor: time,
        ceiling: time,
        default: time,
    ) -> time:
        """`floor`/`ceiling` limitam o prazo (janela do briefing); `default` é o
        prazo de quem ainda não tem histórico de corrida."""

        start = day - timedelta(days=LOOKBACK_DAYS)

        # 1 amostra por dia = a PRIMEIRA corrida do dia (é o início do treino;
        # colapsa também a mesma corrida vinda de Garmin e Strava)
        first_by_day: dict[date, int] = {}

        for activity in activities:

            if not is_run_sport(activity.sport):

                continue

            when = activity.start_date

            if not (start <= when.date() < day):

                continue

            minutes = when.hour * 60 + when.minute

            first_by_day[when.date()] = min(
                minutes, first_by_day.get(when.date(), minutes)
            )

        if not first_by_day:

            return default

        same = [
            m for d, m in first_by_day.items() if d.weekday() == day.weekday()
        ]

        sample = same if len(same) >= MIN_SAME_WEEKDAY else list(
            first_by_day.values()
        )

        morning = sorted(m for m in sample if m < NOON)

        # treinar de manhã não é o hábito (tarde/noite): o treino está longe,
        # dá pra esperar o sono até o teto
        if len(morning) < max(2, -(-len(sample) // 3)):

            return ceiling

        # quartil CEDO das manhãs: cobre os dias em que ele sai mais cedo
        habitual = morning[len(morning) // 4]

        deadline = (
            datetime.combine(day, time(habitual // 60, habitual % 60)) - LEAD
        ).time()

        return min(max(deadline, floor), ceiling)
