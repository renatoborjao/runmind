"""Radar de sobrecarga (camada 2): calcula a CARGA de treino aguda (7d) vs
crônica (28d) e o ACWR a partir do histórico de atividades — pra QUALQUER
atleta, sem depender do 'training load' que só os relógios Garmin top dão.

Carga = minutos de treino (duração). Puro/testável, sem IO. Não decide nada
sozinho nem fala com o atleta — entrega o retrato pra a camada 3 (síntese)
consumir. Ver [[project_analise_corpo_garmin]]."""

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from app.application.history.hr_zone_calculator import HrZoneCalculator
from app.core.clock import today_local
from app.domain.entities.training_history import TrainingHistory
from app.domain.value_objects.hr_zones import HrZones
from app.domain.entities.training_load import (
    ACWR_CAUTION_MAX,
    ACWR_DETRAINING,
    ACWR_OPTIMAL_MAX,
    LOAD_CAUTION,
    LOAD_DETRAINING,
    LOAD_HIGH,
    LOAD_INSUFFICIENT,
    LOAD_LIGHT,
    LOAD_OPTIMAL,
    TrainingLoad,
)

# a crônica precisa de ~3 semanas pra ser um baseline honesto; com menos, o
# ACWR fica instável (divisor pequeno infla a razão), então não arriscamos um
# veredito — devolve INSUFFICIENT_DATA.
_MIN_HISTORY_DAYS = 21

_ACUTE_DAYS = 7
_CHRONIC_DAYS = 28

# BASE BAIXA: quem treina menos de ~1h30 por semana "sobe 40%" com UMA corrida um
# pouco mais forte (João 27/09: 30 min na semana, base de ~40 — "sobrecarregado").
# Nessa base, a razão só é pico com aumento REAL de tempo. Base normal segue a
# razão pura (pico de INTENSIDADE com o mesmo tempo é pico de verdade), e o
# iniciante que salta de 60 pra 150 min continua sinalizado.
_LOW_BASE_MINUTES = 90
_MIN_SPIKE_MINUTES = 30

# uma semana abaixo desta fração do PICO da janela é "taper" (afiação pré-prova),
# não a carga normal do atleta — ao calcular a crônica pós-prova, essas semanas
# ficam de fora (senão deflacionam a base e o ACWR vira um pico falso). Espelha o
# _DIP_RATIO do DeloadAnalyzer. Ver [[race_detector]].
_TAPER_DIP_RATIO = 0.7

# a crônica PADRÃO é 28d (padrão do ACWR — de propósito, pra o radar de risco não
# ficar lento). Mas quando há PROVA na janela, o taper corrompe esses 28d; aí a
# BASE ignora as semanas de carga baixa (a afiação) e usa as últimas 4 com carga
# REAL — a carga que o atleta de fato sustenta. Não hardcodamos "quantas semanas
# de taper" (varia com a distância: 10k~1, meia~2, maratona~3): detectamos o
# taper pela carga baixa e pulamos. Ver a conversa com o Renato (09/2026).
_BASELINE_WEEKS = 4                # semanas de carga REAL que formam a base
_BASELINE_LOOKBACK_WEEKS = 10      # até onde vasculhar pra achar essas 4

# REBOTE DE PARADA: o último mês tem semanas zeradas ou fracas (pausa médica, gripe, chuva e
# frio) e a semana de agora, que VOLTA ao que ele já sustentava, parece pico contra essa base
# rasa. Renato 01/11: ACWR 1,46 com 25 km na semana, quando sustentava 28-31 km — o coach leu
# "risco alto" e cortou o plano 30%. Se a aguda não passa do que ele SUSTENTOU (média das
# melhores semanas nas ~9 anteriores), o mês tem uma interrupção e a aguda não é um salto sobre a
# melhor semana do mês (≤ 30% acima), a razão é retorno ao normal dele. (Fernanda 1,43 e
# Leonardo 1,62 foram a mesma classe.)
_SUSTAINED_LOOKBACK_WEEKS = 9      # semanas ANTERIORES à aguda onde procurar o que ele sustentava
_GAP_SHARE = 0.5                   # semana abaixo desta fração do sustentado = interrupção
_MAX_STEP = 1.3                    # a aguda não passa disto vezes a MELHOR semana do último mês

# Voltar ao PLATÔ dele não é pico, mesmo que a semana passe um pouco do sustentado: o sustentado é
# uma MÉDIA das melhores semanas, então a melhor semana dele fica acima dela (Renato 08/11: 195 min
# contra um sustentado de 183, e a melhor semana dele era 193). Tolerância de 10% sobre a média.
_RETURN_TOLERANCE = 1.10

# base rasa por parada: além de "alguma semana abaixo de metade do sustentado", vale a média das
# semanas da janela crônica abaixo desta fração do sustentado (Renato: 128, 112 e 91 min contra
# 183 — a média é 60%; uma única semana de 91 min contra o corte de 91,7 era a diferença entre
# reconhecer a parada ou não)
_SHALLOW_SHARE = 0.75

# SALTO DE SESSÃO seguro: até esta fração acima da maior corrida dos 30 dias anteriores. Acima
# disso o risco de lesão por corrida única sobe (Frandsen et al., BJSM 2025: 5.205 corredores;
# 10–30% acima já foi 64% mais risco). Abaixo, a semana pode ter voltado a 3 corridas sem que
# NENHUMA delas tenha sido um salto — e aí a razão semanal alta é frequência, não impacto.
_SAFE_LONG_SPIKE = 0.10
_LONG_SPIKE_WINDOW_DAYS = 30


def sustained_average(week_load_back) -> float | None:
    """O que ele SUSTENTAVA: a média das `_BASELINE_WEEKS` melhores semanas das
    `_SUSTAINED_LOOKBACK_WEEKS` anteriores. `week_load_back(w)` devolve a carga (minutos, km…) da
    semana que fechou `w` semanas antes da referência. None sem 4 semanas com treino. É a definição
    ÚNICA de "sustentado": o retorno de parada da carga e a auditoria do plano a usam, pra não
    chamarem de salto o que o coach lê como volta ao normal."""

    loads = [week_load_back(w) for w in range(1, _SUSTAINED_LOOKBACK_WEEKS + 1)]

    best = sorted((load for load in loads if load > 0), reverse=True)[:_BASELINE_WEEKS]

    if len(best) < _BASELINE_WEEKS:

        return None

    return sum(best) / len(best)


# fator de intensidade da sessão SEM FC (raro): usa a mediana do próprio
# atleta; sem nenhuma sessão com FC, cai neste moderado
_DEFAULT_INTENSITY = 0.65

# TRIMP de Banister: fator = %FCR × k × e^(c·%FCR) — a exponencial dá muito
# mais peso ao esforço forte que o linear. Coeficientes por sexo (Banister).
_BANISTER = {
    "M": (0.64, 1.92),
    "F": (0.86, 1.67),
}


class TrainingLoadAnalyzer:

    @staticmethod
    def analyze(
        history: TrainingHistory,
        reference_date: date | None = None,
        resting_hr: int | None = None,
        max_hr: int | None = None,
        sex: str | None = None,
        recent_race_date: date | None = None,
        zones: HrZones | None = None,
    ) -> TrainingLoad:
        """Carga aguda vs crônica + ACWR. Com `resting_hr` E `max_hr`, cada
        sessão é ponderada por INTENSIDADE (TRIMP de Banister quando o `sex` é
        conhecido — exponencial por sexo; senão %FCR linear). Sem FC repouso/
        máx, cai na duração pura. O ACWR é razão, então a unidade não muda o
        veredito — o que muda é o peso relativo de treino forte vs leve.

        `recent_race_date`: houve uma PROVA na janela crônica → o taper que a
        antecedeu deflaciona a base (e infla o ACWR num pico falso). Nesse caso a
        crônica é calculada IGNORANDO as semanas de taper/prova — a base passa a
        ser a carga real do atleta, não a afiação temporária."""

        # a janela termina no último dia COMPLETO — ver _last_complete_day
        ref = TrainingLoadAnalyzer._last_complete_day(
            history, reference_date or today_local()
        )

        # carga por dia — Edwards (histograma relido com UMA régua) quando toda
        # a janela tem histograma, senão intensidade por FC média, senão duração
        per_day = TrainingLoadAnalyzer._load_per_day(
            history, resting_hr, max_hr, sex, ref, zones
        )

        acute = TrainingLoadAnalyzer._window_sum(per_day, ref, _ACUTE_DAYS)

        chronic_total = TrainingLoadAnalyzer._window_sum(
            per_day, ref, _CHRONIC_DAYS
        )

        # crônica = média SEMANAL nos 28 dias (pra o ACWR comparar maçã com
        # maçã: aguda de 7 dias contra a média de 7 dias do último mês)
        chronic = round(chronic_total / (_CHRONIC_DAYS / 7), 1)

        # PÓS-PROVA: recalcula a base ignorando o taper (senão o retorno ao
        # normal vira "pico"). Só reduz o ACWR (base mais honesta), nunca cria
        # sobrecarga falsa.
        race_aware = TrainingLoadAnalyzer._race_aware_chronic(
            per_day, ref, recent_race_date
        )

        if race_aware is not None:

            chronic = race_aware

        weekly = TrainingLoadAnalyzer._weekly_loads(per_day, ref)

        # SEMANA PARADA (férias, doença, viagem) não é a base dele: com 2+
        # semanas ativas no mês, a base é a média das ATIVAS — senão a volta ao
        # normal parece pico (Leonardo 27/09: uma semana zerada derrubou a base
        # e o ACWR foi a 1,62 com o mesmo tempo de treino). Voltando de parada
        # LONGA (menos de 2 semanas ativas) segue a média cheia: aí é pico mesmo.
        if race_aware is None:

            active = [w for w in weekly if w > 0]

            if 2 <= len(active) < len(weekly):

                chronic = round(sum(active) / len(active), 1)

        minutes = TrainingLoadAnalyzer._weekly_minutes(history, ref)

        active_minutes = [m for m in minutes if m > 0]

        base_minutes = (
            sum(active_minutes) / len(active_minutes)
            if 2 <= len(active_minutes) < len(minutes)
            else sum(minutes) / len(minutes)
        )

        acute = round(acute, 1)

        days_of_history = TrainingLoadAnalyzer._history_span(per_day, ref)

        acwr = (
            round(acute / chronic, 2)
            if chronic > 0
            else None
        )

        # com prova na janela, semana leve é o taper/recuperação — não destreino
        light_confirmed = race_aware is None and TrainingLoadAnalyzer._two_light_weeks(
            per_day, ref
        )

        status = TrainingLoadAnalyzer._status(
            acwr, days_of_history, light_confirmed
        )

        low_base = None

        if (
            status in (LOAD_CAUTION, LOAD_HIGH)
            and base_minutes < _LOW_BASE_MINUTES
            and minutes[-1] - base_minutes < _MIN_SPIKE_MINUTES
        ):

            status = LOAD_OPTIMAL

            low_base = (round(base_minutes), round(minutes[-1] - base_minutes))

        long_run_km = TrainingLoadAnalyzer._long_run_km(history, ref)

        long_spike = (
            round(long_run_km[0] / long_run_km[1] - 1, 3) if long_run_km is not None else None
        )

        rebound = None

        if status in (LOAD_CAUTION, LOAD_HIGH) and race_aware is None:

            sustained = TrainingLoadAnalyzer._rebound_base(
                history, ref, minutes, long_spike=long_spike
            )

            if sustained is not None:

                rebound = (round(sustained), minutes[-1])

                # a razão passa a ser sobre o que ele SUSTENTAVA, em tempo de treino (existe pro
                # histórico inteiro, a carga por FC só pros últimos 28 dias — e a duração não
                # sofre com a FC deslocada por substância/cigarro/calor)
                acwr = round(minutes[-1] / sustained, 2)

                chronic = round(acute / acwr, 1) if acwr > 0 else chronic

                status = TrainingLoadAnalyzer._status(
                    acwr, days_of_history, light_confirmed
                )

        return TrainingLoad(
            acute_load=acute,
            chronic_load=chronic,
            acwr=acwr,
            status=status,
            days_of_history=days_of_history,
            weekly_loads=weekly,
            weekly_minutes=minutes,
            low_base=low_base,
            rebound=rebound,
            long_spike=long_spike,
            long_run_km=long_run_km,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _intensity_factor(hrr: float, sex: str | None) -> float:
        """Peso de intensidade da sessão a partir do %FCR. Com sexo conhecido,
        TRIMP de Banister (exponencial); senão, %FCR linear."""

        coeffs = _BANISTER.get((sex or "").upper()[:1])

        if coeffs is None:

            return hrr

        k, c = coeffs

        return hrr * k * math.exp(c * hrr)

    @staticmethod
    def _load_per_day(
        history: TrainingHistory,
        resting_hr: int | None,
        max_hr: int | None,
        sex: str | None,
        ref: date,
        zones: HrZones | None = None,
    ) -> dict[date, float]:
        """Carga somada por dia, em 3 tiers (do mais pro menos preciso):
        (1) EDWARDS pelo histograma de FC relido com UMA régua (a atual) — só
        quando TODA a janela de 28d tem histograma; (2) intensidade por FC
        média (Banister/%FCR) com FC repouso+máx; (3) duração pura.

        NUNCA os minutos-por-zona gravados: cada um ficou preso à régua do dia
        da ingestão (fórmula de idade, reserva, relógio) e a mesma corrida
        pesava até 35% menos depois de uma troca de régua — ACWR falso de
        "destreino", e viés pra baixo justo quando a FC de repouso sobe (a
        régua sobe junto). Ver [[project_carga_regua_mista]]."""

        # tier 1: Edwards pelo histograma, liga sozinho quando os ~28 dias já
        # acumularam histograma (ingestão nova do Garmin/Strava com stream)
        ruler = zones or TrainingLoadAnalyzer._ruler(resting_hr, max_hr)

        edwards = TrainingLoadAnalyzer._edwards_per_day(history, ref, ruler)

        if edwards is not None:

            return edwards

        intensity_mode = (
            resting_hr is not None
            and max_hr is not None
            and max_hr > resting_hr
        )

        # (dia, minutos, fator) — fator None quando a sessão não tem FC
        sessions: list[tuple[date, float, float | None]] = []

        for activity in history.activities:

            minutes = (activity.moving_time or 0) / 60

            if minutes <= 0:

                continue

            factor = None

            if intensity_mode and activity.average_heartrate:

                hrr = (activity.average_heartrate - resting_hr) / (
                    max_hr - resting_hr
                )

                hrr = min(1.0, max(0.0, hrr))

                factor = TrainingLoadAnalyzer._intensity_factor(hrr, sex)

            sessions.append((activity.start_date.date(), minutes, factor))

        per_day: dict[date, float] = defaultdict(float)

        if not intensity_mode:

            for day, minutes, _ in sessions:

                per_day[day] += minutes

            return per_day

        # sessão sem FC (rara) herda a mediana de intensidade do próprio atleta
        known = [f for _, _, f in sessions if f is not None]

        fallback = statistics.median(known) if known else _DEFAULT_INTENSITY

        for day, minutes, factor in sessions:

            per_day[day] += minutes * (factor if factor is not None else fallback)

        return per_day

    @staticmethod
    def _ruler(resting_hr: int | None, max_hr: int | None) -> HrZones | None:
        """Régua única pra reler os histogramas quando o chamador não passou a
        do atleta: reserva de FC com o repouso/máx ATUAIS; só a máx → %FCmáx."""

        if max_hr and resting_hr and max_hr > resting_hr:

            return HrZones.from_hrr(int(max_hr), int(resting_hr))

        if max_hr:

            return HrZones.from_max(int(max_hr))

        return None

    @staticmethod
    def _edwards_per_day(
        history: TrainingHistory,
        ref: date,
        ruler: HrZones | None,
    ) -> dict[date, float] | None:
        """Carga de Edwards por dia — SÓ quando toda atividade dos últimos 28d
        tem HISTOGRAMA de FC, relido com a MESMA régua (a atual): mesma corrida,
        mesma carga, não importa quando entrou. None senão (cai nos outros
        tiers, também de régua única)."""

        if ruler is None:

            return None

        counting = [
            a for a in history.activities if (a.moving_time or 0) > 0
        ]

        window = [
            a for a in counting
            if ref - timedelta(days=_CHRONIC_DAYS - 1) <= a.start_date.date() <= ref
        ]

        # sem janela, ou alguma atividade da janela sem histograma: ainda não dá
        if not window or any(
            not getattr(a, "hr_histogram", None) for a in window
        ):

            return None

        per_day: dict[date, float] = defaultdict(float)

        for activity in counting:

            load = HrZoneCalculator.edwards_load(
                ruler.minutes_from_histogram(
                    getattr(activity, "hr_histogram", None)
                )
            )

            if load is not None:

                per_day[activity.start_date.date()] += load

        return per_day

    @staticmethod
    def _window_sum(
        per_day: dict[date, float],
        ref: date,
        days: int,
    ) -> float:
        """Soma a carga na janela [ref-(days-1) .. ref] inclusive."""

        start = ref - timedelta(days=days - 1)

        return sum(
            load
            for day, load in per_day.items()
            if start <= day <= ref
        )

    @staticmethod
    def _history_span(per_day: dict[date, float], ref: date) -> int:
        """Dias entre o treino mais antigo (até 28d atrás) e a referência —
        pra saber se há baseline suficiente pro veredito."""

        days_with_load = [
            day
            for day in per_day
            if ref - timedelta(days=_CHRONIC_DAYS - 1) <= day <= ref
        ]

        if not days_with_load:

            return 0

        return (ref - min(days_with_load)).days + 1

    @staticmethod
    def _race_aware_chronic(
        per_day: dict[date, float],
        ref: date,
        race_date: date | None,
    ) -> float | None:
        """Base crônica quando há PROVA na janela: as `_BASELINE_WEEKS` semanas
        de carga REAL IMEDIATAMENTE ANTES do taper — o bloco que o atleta
        construiu rumo à prova, a carga que ele de fato sustentava.

        Anda pra trás A PARTIR da semana da prova: pula o taper (semanas baixas
        coladas na prova) e junta as semanas de volume que vêm logo antes. NÃO
        entra a reconstrução pós-prova (senão um retorno agressivo mascararia o
        próprio ACWR) nem semanas soltas lá de trás (a base tem que ser o bloco
        recente que levou à prova, não volume antigo qualquer).

        None quando não há prova na janela ou não há bloco pré-taper no alcance —
        aí vale a crônica padrão de 28d. Só pode ELEVAR a base, nunca inventa
        sobrecarga."""

        if race_date is None:

            return None

        window_start = ref - timedelta(days=_CHRONIC_DAYS - 1)

        # só entra no modo pós-prova se a prova está na janela do ACWR (28d)
        if not (window_start <= race_date <= ref):

            return None

        # semanas (início, fim, carga) até o lookback, antigo→novo
        weeks: list[tuple[date, date, float]] = []

        for w in range(_BASELINE_LOOKBACK_WEEKS - 1, -1, -1):

            end = ref - timedelta(days=7 * w)

            start = end - timedelta(days=6)

            load = sum(
                v for day, v in per_day.items() if start <= day <= end
            )

            weeks.append((start, end, round(load, 1)))

        peak = max((load for _, _, load in weeks), default=0.0)

        if peak <= 0:

            return None

        race_idx = next(
            (
                i
                for i, (start, end, _) in enumerate(weeks)
                if start <= race_date <= end
            ),
            None,
        )

        if race_idx is None:

            return None

        # Passo 1 — o TRECHO contíguo de treino antes da prova: anda pra trás
        # desde a prova e para no 1º GAP (semana bem abaixo do que já se viu no
        # trecho). Assim volume ALTO e ANTIGO, separado por um buraco, NÃO entra
        # (ponto do Renato) — a referência é local ao trecho, não um pico global.
        stretch: list[float] = []  # do mais novo pro mais antigo

        run_peak = 0.0

        for i in range(race_idx - 1, -1, -1):

            load = weeks[i][2]

            if stretch and load < _TAPER_DIP_RATIO * run_peak:

                break  # gap: fim do trecho que levou à prova

            stretch.append(load)

            run_peak = max(run_peak, load)

        if not stretch:

            return None

        # Passo 2 — dentro do trecho, tira o TAPER (semanas abaixo do pico do
        # trecho) e fica com as últimas `_BASELINE_WEEKS` de carga REAL antes da
        # afiação: a carga que o atleta de fato sustentava.
        peak = max(stretch)

        block = [load for load in stretch if load >= _TAPER_DIP_RATIO * peak]

        base = block[:_BASELINE_WEEKS]

        if not base:

            return None

        return round(sum(base) / len(base), 1)

    @staticmethod
    def _rebound_base(
        history: TrainingHistory,
        ref: date,
        minutes: list[float],
        long_spike: float | None = None,
    ) -> float | None:
        """Os minutos semanais que ele SUSTENTAVA, quando a razão alta é só o retorno a eles —
        None quando é salto de verdade (ou não dá pra afirmar o contrário).

        Sustentado = média das `_BASELINE_WEEKS` melhores semanas das `_SUSTAINED_LOOKBACK_WEEKS`
        ANTERIORES à aguda (precisa de 4 semanas com treino, senão não há o que sustentar).
        Rebote só quando (1) a aguda não passa do sustentado, (2) as semanas anteriores da janela
        crônica têm interrupção (abaixo de metade do sustentado — a base rasa vem de parada, não de
        mês fraco inteiro) e (3) a aguda não é um salto sobre a MELHOR semana do último mês (até
        30% acima): quem volta de meses fracos direto pra perto do pico antigo continua sendo
        salto, e quem sobe de 128 pra 156 min na volta de uma parada não é.

        Duas correções (Renato 08/11: 91 → 195 min, ACWR 1,42, "sobrecarregado", plano cortado,
        mesmo tendo o MAIOR TREINO só 3% acima do maior dos 30 dias): (a) a aguda pode passar até
        10% do sustentado (a média das melhores semanas fica abaixo da melhor semana dele); (b) o
        passo de volume grande NÃO desqualifica o retorno quando NENHUMA corrida foi um salto de
        sessão (`long_spike` dentro de 10%) — a semana dobrou porque ele voltou a 3 corridas, não
        porque alguma ficou longa demais. A razão semanal prevê lesão pior que o salto de sessão
        (Impellizzeri 2020; Frandsen 2025), então o salto de sessão é quem libera o passo grande."""

        acute = minutes[-1]

        if acute <= 0:

            return None

        def minutes_back(w: int) -> float:

            end = ref - timedelta(days=7 * w)

            start = end - timedelta(days=6)

            return sum(
                (a.moving_time or 0) / 60
                for a in history.activities
                if start <= a.start_date.date() <= end
            )

        sustained = sustained_average(minutes_back)

        if sustained is None:

            return None

        if acute > _RETURN_TOLERANCE * sustained:

            return None

        before = minutes[:-1]

        has_gap = any(load < _GAP_SHARE * sustained for load in before) or (
            bool(before) and sum(before) / len(before) < _SHALLOW_SHARE * sustained
        )

        small_step = acute <= _MAX_STEP * max(before)

        safe_session = long_spike is not None and long_spike <= _SAFE_LONG_SPIKE

        return sustained if has_gap and (small_step or safe_session) else None

    @staticmethod
    def _long_run_km(history: TrainingHistory, ref: date) -> tuple[float, float] | None:
        """(maior corrida dos últimos 7 dias, maior dos 30 dias ANTERIORES a eles), em km. None
        sem corrida na semana ou sem corrida nos 30 dias anteriores — sem base de comparação não há
        "salto" a afirmar (a primeira corrida longa de quem volta de uma parada longa não é um)."""

        acute_start = ref - timedelta(days=_ACUTE_DAYS - 1)

        prev_start = acute_start - timedelta(days=_LONG_SPIKE_WINDOW_DAYS)

        acute_long = 0.0

        prev_long = 0.0

        for a in history.activities:

            day = a.start_date.date()

            km = (getattr(a, "distance", None) or 0) / 1000

            if acute_start <= day <= ref:

                acute_long = max(acute_long, km)

            elif prev_start <= day < acute_start:

                prev_long = max(prev_long, km)

        if acute_long <= 0 or prev_long <= 0:

            return None

        return round(acute_long, 1), round(prev_long, 1)

    @staticmethod
    def _weekly_loads(per_day: dict[date, float], ref: date) -> list[float]:
        """Carga de cada uma das últimas 4 semanas (antigo→novo), pra a
        camada 3 narrar a tendência (rampa/estável/queda)."""

        weeks: list[float] = []

        for w in range(3, -1, -1):

            end = ref - timedelta(days=7 * w)

            start = end - timedelta(days=6)

            weeks.append(
                round(
                    sum(
                        load
                        for day, load in per_day.items()
                        if start <= day <= end
                    ),
                    1,
                )
            )

        return weeks

    @staticmethod
    def _weekly_minutes(history: TrainingHistory, ref: date) -> list[float]:
        """Minutos de treino de cada uma das últimas 4 semanas (antigo→novo),
        nas MESMAS janelas da carga."""

        weeks: list[float] = []

        for w in range(3, -1, -1):

            end = ref - timedelta(days=7 * w)

            start = end - timedelta(days=6)

            weeks.append(
                round(
                    sum(
                        (a.moving_time or 0) / 60
                        for a in history.activities
                        if start <= a.start_date.date() <= end
                    )
                )
            )

        return weeks

    @staticmethod
    def _last_complete_day(history: TrainingHistory, ref: date) -> date:
        """Último dia COMPLETO da janela. Hoje só entra quando já tem treino:
        numa manhã de treino a corrida do dia ainda não aconteceu, e a janela de
        7 dias já soltou a do mesmo dia da semana passada — a aguda perde 1
        sessão de 3 e o ACWR cai por horário, não por carga (Renato 29/09: 0,73
        às 7h da terça com o volume de sempre; 1,00 na véspera). Sem treino hoje,
        a janela termina ontem; qualquer outra data de referência já é um dia
        fechado e passa direto."""

        if ref != today_local():

            return ref

        if any(
            (a.moving_time or 0) > 0 and a.start_date.date() == ref
            for a in history.activities
        ):

            return ref

        return ref - timedelta(days=1)

    @staticmethod
    def _two_light_weeks(per_day: dict[date, float], ref: date) -> bool:
        """Destreino é queda que SE SUSTENTA, não uma semana leve: as duas
        últimas semanas de calendário (seg–dom) COMPLETAS abaixo de 80% da média
        das 4 semanas ativas antes delas. Semana parcial nunca entra. Sem base
        pra comparar (menos de 2 semanas ativas antes) não confirma — não chuta."""

        # domingo que fechou a última semana completa (ref já é dia fechado)
        last_sunday = ref - timedelta(days=(ref.weekday() + 1) % 7)

        def week_load(end: date) -> float:

            start = end - timedelta(days=6)

            return sum(v for d, v in per_day.items() if start <= d <= end)

        base = [
            load
            for load in (
                week_load(last_sunday - timedelta(days=7 * k)) for k in range(2, 6)
            )
            if load > 0
        ]

        if len(base) < 2:

            return False

        limit = ACWR_DETRAINING * (sum(base) / len(base))

        return (
            week_load(last_sunday) < limit
            and week_load(last_sunday - timedelta(days=7)) < limit
        )

    @staticmethod
    def _status(
        acwr: float | None, days_of_history: int, light_confirmed: bool
    ) -> str:

        if acwr is None or days_of_history < _MIN_HISTORY_DAYS:

            return LOAD_INSUFFICIENT

        if acwr < ACWR_DETRAINING:

            # uma semana leve é só uma semana leve (viagem, pausa médica, treino
            # que mudou de dia): só vira destreino se as duas últimas semanas
            # completas confirmarem. Antes disso é LIGHT — nem "equilibrada"
            # (aguda bem abaixo da base) nem "queda de forma".
            return LOAD_DETRAINING if light_confirmed else LOAD_LIGHT

        if acwr <= ACWR_OPTIMAL_MAX:

            return LOAD_OPTIMAL

        if acwr <= ACWR_CAUTION_MAX:

            return LOAD_CAUTION

        return LOAD_HIGH
