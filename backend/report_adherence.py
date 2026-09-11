"""Quem está SEGUINDO o plano do coach — ranking de aderência de todos os
atletas, para decidir quem vale manter e quem é peso morto.

Reaproveita o AdherenceAnalyzer (a mesma engine que o coach usa por dentro):
para cada atleta confronta o que foi PRESCRITO com o que foi TREINADO de
verdade, semana a semana, e resume em três coisas que decidem:
  - rate:  fração das sessões prescritas que tiveram treino casado (0-100%)
  - trend: aderência subindo, estável ou caindo nas últimas semanas
  - furo:  o que ele MAIS vive furando (um dia da semana ou um tipo de treino)

⚠ O QUE ESTE 'rate' MEDE (e o que NÃO mede): mede PRESENÇA no plano — a
sessão é dada como cumprida quando houve corrida no DIA planejado (ou, fora
do dia, com DISTÂNCIA dentro de 2 km/30%). NÃO confere se o TIPO/estímulo
bateu: quem correu 8 km de rodagem lenta no dia do intervalado conta como
'cumprido' aqui. 'Seguir o plano de verdade' (executar o estímulo certo)
exige os splits/voltas do treino, que o arquivo permanente não guarda —
é a evolução 'aderência de estímulo' (ver TODO no fim do arquivo).

Puro leitura de disco (arquivo permanente de treinos + histórico de planos),
sem tocar em Strava/rede. Roda igual local ou no servidor — mas o resultado só
é fiel onde os dados estão VIVOS (produção, na Oracle). Numa cópia local
defasada, os números refletem a data do último sync, não o hoje.

Uso:
  python report_adherence.py            # todos os atletas, ranking
  python report_adherence.py <profile>  # um atleta, detalhado semana a semana
"""

import asyncio
import sys
from datetime import date, timedelta

from app.application.history.adherence_analyzer import AdherenceAnalyzer
from app.application.history.stimulus_adherence import (
    INTERVAL_HIT,
    INTERVAL_MISS,
    INTERVAL_PARTIAL,
    ON_TARGET,
    STRUCTURED,
    TOO_FAST,
    TOO_SLOW,
    StimulusAdherence,
)
from app.infrastructure.persistence.stimulus_result_store import (
    StimulusResultStore,
)
from app.application.use_cases.load_runner_profile import LoadRunnerProfile
from app.core.clock import today_local, use_athlete_timezone
from app.domain.entities.adherence_report import (
    ADHERENCE_FALLING,
    ADHERENCE_RISING,
    ADHERENCE_STABLE,
)
from app.domain.entities.training_history import TrainingHistory
from app.infrastructure.persistence.activity_archive_repository import (
    ActivityArchiveRepository,
)
from app.infrastructure.persistence.runner_profile_repository import (
    RunnerProfileRepository,
)
from app.infrastructure.persistence.weekly_plan_repository import (
    WeeklyPlanRepository,
)

# janela de análise (mesmo lookback do coach)
WEEKS = 8

_TREND_LABEL = {
    ADHERENCE_RISING: "subindo ↑",
    ADHERENCE_STABLE: "estável →",
    ADHERENCE_FALLING: "caindo ↓",
}

# --- limiares do veredito (ação, não só nota) ---------------------------
# sem treinar por mais que isso = sumiu (abandonou, independe do plano)
_GONE_DAYS = 21
# ativo, mas cumprindo menos que isso e sem padrão = corre do jeito dele
_IGNORES_RATE = 0.55
# cumprindo a maior parte = está seguindo de fato
_FOLLOWS_RATE = 0.85
# "nunca engajou": aderência geral no chão desde o começo
_NEVER_RATE = 0.35

# veredito -> (rótulo curto, prioridade de "limar": menor = corta antes)
VERDICTS = {
    "GONE": ("SUMIU", 0),
    "NEVER": ("NUNCA ENGAJOU", 1),
    "IGNORES": ("IGNORA O PLANO", 2),
    "AVOIDS": ("FURA 1 ESTÍMULO", 3),
    "PARTIAL": ("PARCIAL", 4),
    "FOLLOWS": ("SEGUINDO ✅", 5),
    "NO_DATA": ("SEM SÉRIE", 6),
}


def _verdict(report, last_run: date | None, today: date) -> str:
    """Classifica o atleta na AÇÃO que ele pede — a pergunta do Renato não é
    'qual a nota' e sim 'mantenho ou limo'. Prioriza o sinal mais duro:
    sumiu > nunca engajou > ignora > fura só um estímulo > parcial > segue."""

    days_idle = (today - last_run).days if last_run else None

    # sumiu: não treina há semanas. Se, além de sumido, NUNCA cumpriu de
    # verdade, é 'nunca engajou' (nunca virou cliente ativo).
    if days_idle is None or days_idle > _GONE_DAYS:

        if report.rate is not None and report.rate < _NEVER_RATE:

            return "NEVER"

        return "GONE"

    # daqui pra baixo o atleta É ativo (treinou dentro da janela)
    if report.rate is None:

        return "NO_DATA"

    has_pattern = report.missed_day is not None or report.missed_type is not None

    if report.rate >= _FOLLOWS_RATE and not has_pattern:

        return "FOLLOWS"

    # fura um estímulo específico (dia/tipo) mas no geral aparece: ajustar,
    # não limar — o coach reposiciona o treino
    if has_pattern and report.rate >= _IGNORES_RATE:

        return "AVOIDS"

    # treina, mas cumpre pouco do que foi mandado e sem foco num tipo só:
    # corre do jeito dele, ignorando o plano
    if report.rate < _IGNORES_RATE:

        return "IGNORES"

    return "PARTIAL"


def _monday_of(day: date) -> date:

    return day - timedelta(days=day.weekday())


def _assess(profile: str) -> dict | None:
    """Roda a aderência de um atleta a partir do disco. None quando não há
    plano nenhum registrado (atleta que nunca recebeu plano)."""

    runner = LoadRunnerProfile.execute(profile)

    use_athlete_timezone(runner.timezone)

    today = today_local()

    plans = WeeklyPlanRepository().history(profile)

    history = TrainingHistory(
        activities=ActivityArchiveRepository().load_activities(profile),
    )

    if not plans:

        return None

    # última segunda ainda não à frente; o analyzer ignora semana em curso
    until_week = _monday_of(today)

    report = AdherenceAnalyzer.analyze(
        plans,
        history,
        until_week=until_week,
        weeks=WEEKS,
        reference_date=today,
    )

    stimulus = StimulusAdherence.analyze(
        plans,
        history,
        until_week=until_week,
        weeks=WEEKS,
        reference_date=today,
        interval_results=StimulusResultStore().all(profile),
    )

    last_plan = max(plan.week_start for plan in plans)

    last_run = (
        max(act.start_date.date() for act in history.activities)
        if history.activities
        else None
    )

    return {
        "profile": profile,
        "name": runner.name or profile,
        "report": report,
        "plans": len(plans),
        "runs": len(history.activities),
        "last_plan": last_plan,
        "last_run": last_run,
        "today": today,
        "verdict": _verdict(report, last_run, today),
        "stimulus": stimulus,
    }


def _fmt_pattern(pattern) -> str:

    if pattern is None:

        return "—"

    return f"{pattern.label} ({pattern.count}/{pattern.opportunities})"


def _rate_pct(report) -> str:

    if report.rate is None:

        return "  —"

    return f"{round(report.rate * 100):3d}%"


def _stimulus_pct(stimulus) -> str:

    if stimulus.rate is None:

        return "—"

    return f"{round(stimulus.rate * 100)}%"


def _stimulus_deviation(stimulus) -> str:
    """O desvio de ritmo DOMINANTE — pegar leve (foi no dia e trotou) ou
    forçar além (não respeita o fácil/descarga). '—' quando corre no alvo."""

    slow = len(stimulus.too_slow)

    fast = len(stimulus.too_fast)

    if slow == 0 and fast == 0:

        return "—"

    if slow >= fast:

        return f"pegou leve ({slow}x)"

    return f"forçou além ({fast}x)"


def ranking() -> None:

    rows = []

    for profile in sorted(RunnerProfileRepository().list_all()):

        assessed = _assess(profile)

        if assessed is not None:

            rows.append(assessed)

    if not rows:

        print("Nenhum atleta com plano registrado no storage local.")

        return

    # ordena por prioridade de corte: SUMIU/NUNCA no topo, SEGUINDO no fim;
    # dentro do mesmo veredito, menor aderência primeiro
    rows.sort(
        key=lambda r: (
            VERDICTS[r["verdict"]][1],
            r["report"].rate if r["report"].rate is not None else 1.0,
        )
    )

    print()
    print("ADERÊNCIA AO PLANO DO COACH  —  manter ou limar")
    print(f"(janela: últimas {WEEKS} semanas · gerado {rows[0]['today']})")
    print("* 'segue'  = PRESENÇA (treinou no dia/distância certa)")
    print("* 'ritmo'  = EXECUTOU o estímulo (pace na faixa que o coach mandou)")
    print()

    header = (
        f"{'atleta':<12} {'veredito':<16} {'segue':>5} {'ritmo':>6}  "
        f"{'desvio de ritmo':<20} {'último treino':<14}"
    )
    print(header)
    print("-" * len(header))

    for row in rows:

        report = row["report"]

        # desvio de ritmo dominante: pegar leve ou forçar além
        desvio = _stimulus_deviation(row["stimulus"])

        # aviso de dado velho: último treino há muito tempo = cópia defasada
        idle = (
            (row["today"] - row["last_run"]).days
            if row["last_run"]
            else None
        )

        if row["last_run"] is None:

            sync = "nenhum"

        elif idle is not None and idle > 10:

            sync = f"⚠ {row['last_run']} ({idle}d)"

        else:

            sync = str(row["last_run"])

        print(
            f"{row['name'][:11]:<12} "
            f"{VERDICTS[row['verdict']][0]:<16} "
            f"{_rate_pct(report)} "
            f"{_stimulus_pct(row['stimulus']):>6}  "
            f"{desvio:<20} "
            f"{sync:<14}"
        )

    print()
    print("Vereditos:")
    print("  SUMIU           não treina há +3 semanas — abandonou (candidato)")
    print("  NUNCA ENGAJOU   sumido E quase nada cumprido desde o início")
    print("  IGNORA O PLANO  treina, mas corre do jeito dele (aderência baixa)")
    print("  FURA 1 ESTÍMULO segue quase tudo, evita 1 dia/tipo — AJUSTAR, não limar")
    print("  SEGUINDO ✅      cumpre a maior parte e está ativo")
    print()
    print("  segue = % do prescrito com treino casado por DIA/DISTÂNCIA (presença)")
    print("  ritmo = % das sessões avaliáveis com pace na faixa prescrita")
    print("  desvio = tiros e sessões sem pace-alvo saem da conta do ritmo")
    print("  (detalhe sessão a sessão: report_adherence.py <atleta>)")
    print()

    # honestidade do dado: só alerta se ALGUÉM está com treino velho (a
    # cópia pode estar defasada). Sem isso, todo dado recente = sem ruído.
    stale = [
        row
        for row in rows
        if row["last_run"] and (row["today"] - row["last_run"]).days > 10
    ]

    if stale:

        print(
            "⚠ Atenção: "
            + ", ".join(r["name"] for r in stale)
            + " com último treino há +10 dias. Se você SABE que treinaram,"
        )
        print(
            "  este storage está defasado (rode no servidor); se não, é "
            "abandono real."
        )
        print()


def detail(profile: str) -> None:

    assessed = _assess(profile)

    if assessed is None:

        print(f"{profile}: sem plano registrado.")

        return

    report = assessed["report"]

    print()
    print(f"ADERÊNCIA — {assessed['name']} ({profile})")
    print(f"  planos registrados: {assessed['plans']}")
    print(f"  treinos arquivados: {assessed['runs']}")
    print(f"  último plano:  semana de {assessed['last_plan']}")
    print(f"  último treino: {assessed['last_run'] or '—'}")
    print(f"  hoje (fuso do atleta): {assessed['today']}")
    print()

    if report.rate is None:

        print("  Sem semana fechada com plano de corrida na janela.")

        return

    print(f"  VEREDITO: {VERDICTS[assessed['verdict']][0]}")
    print(f"  ADERÊNCIA GERAL: {round(report.rate * 100)}%")
    print(f"  TENDÊNCIA: {_TREND_LABEL.get(report.trend, 'poucos dados')}")
    print(f"  MAIS FURA (dia):  {_fmt_pattern(report.missed_day)}")
    print(f"  MAIS FURA (tipo): {_fmt_pattern(report.missed_type)}")
    print()
    print("  Semana a semana:")

    for week in report.weeks:

        missed = ", ".join(week.missed_days) if week.missed_days else "—"

        print(
            f"    {week.week_start}  "
            f"{week.done}/{week.planned}  "
            f"({round(week.rate * 100):3d}%)  furou: {missed}"
        )

    print()

    _print_stimulus(assessed["stimulus"])


_STIMULUS_MARK = {
    ON_TARGET: "✅ no ritmo",
    TOO_SLOW: "🐢 pegou leve",
    TOO_FAST: "🔥 forçou além",
    INTERVAL_HIT: "🎯 tiros no alvo",
    INTERVAL_PARTIAL: "🟡 tiros parciais",
    INTERVAL_MISS: "❌ furou os tiros",
    STRUCTURED: "· tiro (s/ splits)",
}


def _print_stimulus(stimulus) -> None:
    """Prescrito × executado, sessão a sessão — 'seguir o plano de verdade'."""

    print("  EXECUÇÃO DO ESTÍMULO (pace prescrito × executado):")

    if stimulus.rate is not None:

        print(
            f"    no ritmo: {round(stimulus.rate * 100)}% "
            f"({len(stimulus.on_target)}/{len(stimulus.evaluated)} avaliáveis) "
            f"· 🐢 leve: {len(stimulus.too_slow)} · "
            f"🔥 forte: {len(stimulus.too_fast)}"
        )

    else:

        print("    (nenhuma sessão contínua com pace-alvo pra avaliar)")

    print()

    # só as sessões que dizem algo (avaliadas + tiros); NO_TARGET é ruído aqui
    shown = [
        session
        for session in stimulus.sessions
        if session.verdict in _STIMULUS_MARK
    ]

    for session in shown:

        mark = _STIMULUS_MARK[session.verdict]

        pace = (
            f"alvo {session.target} · fez {session.executed}"
            if session.target and session.executed
            else (f"fez {session.executed}" if session.executed else "")
        )

        delta = (
            f"  ({session.delta_sec:+d}s/km)"
            if session.delta_sec
            else ""
        )

        # tiros medidos: mostra "4/5 no alvo" em vez de pace médio (irrelevante)
        info = session.detail if session.detail else f"{pace}{delta}"

        print(
            f"    {session.week_start} {session.day[:3]:<3} "
            f"{session.workout_type[:26]:<26} {mark:<18} {info}"
        )

    print()


def main() -> None:

    if len(sys.argv) > 1:

        detail(sys.argv[1])

    else:

        ranking()


if __name__ == "__main__":

    # LoadRunnerProfile é síncrono, mas mantém o mesmo shape do seed
    _ = asyncio
    main()


# ----------------------------------------------------------------------
# TODO — EVOLUÇÃO 'aderência de ESTÍMULO' (seguir o plano DE VERDADE)
#
# Hoje o 'segue %' é PRESENÇA: casou a corrida com a sessão por dia/distância
# (WeeklyPlanMatcher). Não distingue "fez o intervalado prescrito" de "foi no
# dia e trotou 8 km". Para medir execução do estímulo:
#   1. classificar a corrida executada (TrainingClassifier -> WorkoutType) e
#      comparar com o session.workout_type prescrito (bateu o TIPO?);
#   2. o classificador precisa de RunnerMetrics (RunnerMetricsBuilder) + do
#      pace/FC médios (o arquivo TEM) — isso já pega "mandei forte, fez fácil";
#   3. o caso do TIRO exige WorkoutStructure.is_interval, que vem dos
#      splits/voltas — o arquivo permanente NÃO guarda. Ou se persiste a
#      estrutura por atividade, ou se lê a evidência que o pipeline pós-treino
#      já produz (comparação bloco-a-bloco / PaceCalibrationStore).
# Desenhar + validar OFFLINE com treinos reais ANTES de expor no relatório
# (senão vira falso-negativo: acusa de furar quem fez o tiro certo).
# ----------------------------------------------------------------------
