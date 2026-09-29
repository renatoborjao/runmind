from datetime import date, datetime, time, timedelta

from app.application.planner.briefing_deadline import BriefingDeadline
from tests.coach.factories import make_activity

# terça-feira
DAY = date(2026, 9, 29)

FLOOR = time(4, 30)
CEILING = time(11, 0)
DEFAULT = time(7, 0)


def _deadline(activities, day=DAY):

    return BriefingDeadline.compute(
        activities, day, floor=FLOOR, ceiling=CEILING, default=DEFAULT
    )


def _run(days_ago, hh, mm, sport="Run", day=DAY, id=None):

    when = datetime.combine(day - timedelta(days=days_ago), time(hh, mm))

    return make_activity(
        id=id or int(when.timestamp()), sport=sport, start_date=when
    )


def test_sem_historico_cai_no_prazo_padrao():

    assert _deadline([]) == DEFAULT


def test_corredor_da_madrugada_recebe_20_min_antes_do_habito():
    """Caso real renato2: terças 05h17–05h29 → prazo 05h00, antes de sair."""

    runs = [_run(7, 5, 29), _run(14, 5, 17), _run(21, 5, 24), _run(28, 5, 20)]

    assert _deadline(runs) == time(5, 0)


def test_quem_treina_a_noite_espera_o_sono_ate_o_teto():

    runs = [_run(d, 19, 0) for d in (7, 14, 21, 1, 2, 3)]

    assert _deadline(runs) == CEILING


def test_habito_do_dia_da_semana_ganha_do_geral():
    """Terça cedo, resto da semana tarde: vale o hábito da TERÇA."""

    tuesdays = [_run(7, 6, 0), _run(14, 6, 10), _run(21, 6, 5)]
    others = [_run(d, 18, 30) for d in (1, 2, 3, 4, 5, 6)]

    assert _deadline(tuesdays + others) == time(5, 40)


def test_poucas_amostras_no_dia_usa_o_habito_geral():

    runs = [_run(7, 6, 30)] + [_run(d, 6, 30) for d in (1, 2, 3, 4)]

    assert _deadline(runs) == time(6, 10)


def test_caminhada_nao_conta_como_treino():

    walks = [_run(d, 5, 0, sport="Walk") for d in (7, 14, 21)]

    assert _deadline(walks) == DEFAULT


def test_mesma_corrida_em_duas_fontes_e_segunda_corrida_do_dia_nao_contam_2x():
    """1 amostra por dia = a 1ª corrida (Garmin + Strava da mesma corrida, ou
    um 2º treino à noite, não puxam o hábito)."""

    runs = []

    for d in (7, 14, 21):

        runs += [
            _run(d, 5, 30, id=d),
            _run(d, 5, 30, id=100 + d),
            _run(d, 19, 0, id=200 + d),
        ]

    assert _deadline(runs) == time(5, 10)


def test_prazo_nunca_antes_da_janela():

    runs = [_run(d, 4, 40) for d in (7, 14, 21)]

    assert _deadline(runs) == FLOOR


def test_historico_antigo_fora_da_janela_de_habito_nao_conta():

    runs = [_run(d, 5, 0) for d in (84, 91, 98)]

    assert _deadline(runs) == DEFAULT


def test_hoje_nao_entra_na_amostra():

    runs = [_run(0, 5, 0)] + [_run(d, 8, 0) for d in (7, 14, 21)]

    assert _deadline(runs) == time(7, 40)
