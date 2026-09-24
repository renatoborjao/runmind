"""Janela da noite do relógio: o Garmin fecha o dia pela data UTC. No Brasil
(UTC-3), das 21h à meia-noite o "hoje" do atleta já é "ontem" pro Garmin —
treino agendado/reenviado pra hoje nesse horário NÃO desce pro relógio (nem em
Programados, nem em Treinos). Confirmado no FR165 do Renato: 22h falhou
(23/09), de dia funcionou (24/09). Ver [[project_mover_pra_hoje_relogio]]."""

from datetime import datetime, timezone

from app.core.clock import today_local

LATE_TODAY_NOTE = (
    "A essa hora o Garmin já fechou o dia de hoje, então esse treino não "
    "desce pro relógio hoje. Se for correr, começa uma corrida livre no "
    "relógio que eu comparo com o plano do mesmo jeito. 👊"
)


def watch_day_closed() -> bool:
    """True quando a data UTC (a do Garmin) já passou do 'hoje' do atleta."""

    return datetime.now(timezone.utc).date() > today_local()
