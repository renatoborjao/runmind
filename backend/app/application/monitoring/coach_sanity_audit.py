"""AUDITORIA DE SANIDADE DO COACH — roda todo dia, SEM IA, e avisa o dono no Telegram SÓ quando há
achado novo. Procura o que o coach VÊ nos dados mas o atleta só denuncia reclamando.

A auditoria semanal (`ops/coach_audit.py`) caça SINTOMAS em mensagens: promessa sem entrega,
reclamação, erro engolido. Não olha o ESTADO do coach contra os DADOS nem a falta de evolução — e
foi por aí que o Leonardo ficou semanas com treino fraco sem ninguém saber (21/10): o treino do
próprio coach "Ritmo de Prova" lido como prova (modo pós-prova trava o "puxar"), esforço percebido
≤3/10 em 6 de 7 corridas, 0% do tempo em zona forte e um pedido de "mais" que não mudou a dose.

Cada achado vem em português simples, com os números. O alerta não muda NADA sozinho (só avisa) e
cada achado só volta a ser avisado depois de `COOLDOWN_DAYS` — sem ruído diário. Os checks são
puros (recebem números) e testados offline; `audit` só os liga aos dados reais.

    python -m app.application.monitoring.coach_sanity_audit          # mostra tudo (dry-run)
    python -m app.application.monitoring.coach_sanity_audit --send     # avisa o dono (cron)

Ver [[project_atleta_leonardo]] e [[project_rota_ate_a_meta]]."""

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from app.application.history import effort_scale
from app.application.history.effort_scale import EffortScale

# --- limiares (todos em um lugar; o alerta é pra OLHAR, não pra decidir) -------------------------

# cada achado só volta a ser avisado depois disto
COOLDOWN_DAYS = 7

# esforço baixo o tempo todo: relatos de esforço nos últimos 28 dias e mínimo de relatos; "baixo" é
# ABAIXO DO HABITUAL DELE (`effort_scale`), nunca um limite absoluto que acusa quem responde baixo
# por hábito
RPE_WINDOW_DAYS = 28
RPE_MIN_REPORTS = 5

# com prova datada e meta de tempo entre estas semanas de distância, esforço baixo pesa
EFFORT_WEEKS = (3, 12)

# pedido de mais carga sem resposta: dias desde o pedido e quanto a dose precisa ter subido
ASK_MIN_DAYS = 10
ASK_WEEK_GAIN = 1.15
ASK_LONG_GAIN = 1.10

# rota até a meta: a prova está perto E ainda falta tanto
PATH_WEEKS_LEFT = 8
PATH_LONG_GAP_KM = 1.5
PATH_WEEK_GAP_KM = 6.0

# forma estável há pelo menos estas semanas, com a prova a até tantas semanas
STAGNANT_WEEKS = 6
STAGNANT_RACE_WEEKS = 12

# --- checks que valem pra TODOS (não dependem de prova com data) ---------------------------------

# rodagem leve/regenerativa é metade ou mais das sessões prescritas, com meta de tempo
EASY_SHARE_MAX = 0.5
EASY_WINDOW_WEEKS = 6
EASY_MIN_SESSIONS = 8

# nenhum estímulo forte FEITO há tantos dias, correndo normalmente, com meta de tempo
NO_QUALITY_DAYS = 21
NO_QUALITY_MIN_RUNS = 6

# volume e maior treino sem mudar por estas semanas fechadas, com o plano em dia
STALL_WEEKS = 4
STALL_KM_SPREAD = 0.12
STALL_LONG_SPREAD_KM = 1.0
STALL_MIN_ADHERENCE = 0.85

# cumpriu menos que isto do plano nas últimas semanas (mínimo de sessões planejadas)
ADHERENCE_LOW = 0.6
ADHERENCE_MIN_PLANNED = 6
ADHERENCE_WEEKS = 3

# sem correr há tantos dias e sem doença registrada
STOPPED_DAYS = 14

# o "pós-prova" do coach vale por este número de semanas (deload_analyzer._POST_RACE_GRACE_WEEKS)
POST_RACE_WEEKS = 3

# --- forte PRESCRITO × ENTREGUE (nº 81) -----------------------------------------------------------

# fortes FEITOS na janela (6 semanas) pra opinar, e quantos "sem intensidade" entre eles
DELIVERY_MIN_DONE = 3
DELIVERY_MIN_SOFT = 2

# nenhum forte entregue há tantas semanas = o forte existe só no papel
DELIVERY_STALE_WEEKS = 3

# --- o plano nasce do que o atleta FEZ (a rota semana a semana, nº 80) ---------------------------

# volume prescrito que oscila: variação semana a semana acima disto, tantas vezes, sem motivo
SAWTOOTH_SWING = 0.35
SAWTOOTH_MIN_SWINGS = 2

# o papel passou disto sobre o que ele FEZ (o maior entre a semana anterior e o que ele sustenta);
# com o motivo escrito só alerta num salto bem maior (um motivo não justifica qualquer salto)
JUMP_OVER_DONE = 1.40
JUMP_EXPLAINED_MAX = 1.60

# volume prescrito fora desta faixa da rota, sem o motivo escrito pelo coach
ROUTE_OFF = 0.20

# ele fez menos que esta fração da rota por tantas semanas seguidas
ROUTE_LATE_SHARE = 0.8
ROUTE_LATE_WEEKS = 3

HIGH = "alto"
WATCH = "atenção"


@dataclass(slots=True)
class Finding:

    profile: str
    code: str
    level: str
    text: str


# O aviso é lido pelo dono, não por engenheiro: cada achado vira um título curto, a frase com os
# números (`Finding.text`) e UMA linha dizendo o que fazer. Tudo em português de corredor — sem
# "dose", "estímulo", "prescrito", "ruído" (Renato, 29/10: "recebi a auditoria e não entendi nada").
TITLES = {
    "prova_sem_lastro": "Prova que talvez não seja prova",
    "esforco_baixo": "Treinos talvez leves demais",
    "pediu_mais_sem_resposta": "Pediu mais treino e não foi atendido",
    "rota_abaixo_da_faixa": "Preparo abaixo do que a prova pede",
    "forma_estagnada": "Condicionamento parado",
    "rodagem_demais": "Muita corrida leve no plano",
    "sem_estimulo_forte": "Sem treino forte há tempo",
    "plano_parado": "Plano parou de evoluir",
    "aderencia_baixa": "Cumprindo pouco do plano",
    "dente_de_serra": "Km por semana subindo e descendo sem explicação",
    "salto_sobre_o_feito": "Semana muito acima do que ele fez",
    "desvio_sem_motivo": "Plano fora da rota sem explicação",
    "rota_atrasada": "Abaixo da rota há semanas",
    "descarga_por_calendario": "Semana leve marcada por calendário",
    "forte_sem_intensidade": "Treino forte feito em ritmo de leve",
    "parou_de_correr": "Parou de correr",
}

ACTIONS = {
    "prova_sem_lastro": (
        "Confira se foi prova de verdade ou só um treino com \"prova\" no nome. Se foi treino, "
        "o coach está freando sem motivo."
    ),
    "esforco_baixo": (
        "Pode ser que o treino esteja leve demais pra meta, ou base de propósito. Olhe o plano da "
        "semana dele."
    ),
    "pediu_mais_sem_resposta": "O coach precisa subir a carga ou explicar a ele por que não.",
    "rota_abaixo_da_faixa": (
        "As próximas semanas precisam subir o volume, com cuidado, pra ele chegar pronto."
    ),
    "forma_estagnada": "Falta variar ou apertar o treino forte pra ele evoluir antes da prova.",
    "rodagem_demais": "Veja se o plano tem treino forte e longão suficientes pra ele evoluir.",
    "sem_estimulo_forte": "O próximo plano precisa ter um treino forte.",
    "plano_parado": "Se não é manutenção de propósito, o plano precisa subir aos poucos.",
    "aderencia_baixa": (
        "Vale o coach conversar com ele sobre a rotina e ajustar o plano pro que ele consegue "
        "fazer."
    ),
    "dente_de_serra": (
        "Plano bom sobe aos poucos e só alivia quando o corpo pede: cada semana deve partir do "
        "que ele fez."
    ),
    "salto_sobre_o_feito": (
        "Pular muito acima do que ele fez aumenta o risco de lesão e de ele não cumprir. Sem bom "
        "motivo, o coach deve reduzir."
    ),
    "desvio_sem_motivo": "O coach tem que seguir a rota ou escrever por que saiu dela.",
    "rota_atrasada": (
        "A rota está acima do que ele cumpre: a rotina mudou, ou o plano precisa partir do que "
        "ele consegue."
    ),
    "descarga_por_calendario": (
        "Semana leve não é calendário: só vale se o corpo pedir ou se ele não cumprir o plano. O "
        "coach precisa refazer isso quando a semana chegar."
    ),
    "forte_sem_intensidade": (
        "Repetir o mesmo treino forte não resolve: o coach precisa ajustar o ritmo-alvo ou "
        "conversar com ele sobre esforço."
    ),
    "parou_de_correr": "Confira se há uma pausa combinada ou se ele se afastou.",
}


@dataclass(slots=True)
class Snapshot:
    """Os números de um atleta no painel de segunda."""

    profile: str
    km_week: float | None
    long_km: float | None
    adherence: float | None
    next_race: str | None
    route: str | None = None


# --- os checks (puros) ---------------------------------------------------------------------------


def _fmt_date(day: date) -> str:

    return f"{day:%d/%m}"


def unbacked_race(
    profile: str, event, result_dates: list[date], list_dates: list[date],
) -> Finding | None:
    """O coach acha que houve uma PROVA recente (modo pós-prova: sem sinal de "puxar" nem
    descarga) sem nenhuma prova na lista do app nem resultado registrado naquela data."""

    if event is None or event.weeks_ago > POST_RACE_WEEKS:

        return None

    near = [d for d in (*result_dates, *list_dates) if abs((d - event.date).days) <= 1]

    if near:

        return None

    return Finding(
        profile, "prova_sem_lastro", HIGH,
        f"O coach entendeu que \"{event.name}\" ({_fmt_date(event.date)}) foi uma prova e entrou "
        "em modo pós-prova (não aumenta a carga e não alivia). Só que não há prova nessa data na "
        "lista do app nem resultado registrado.",
    )


def low_effort(
    profile: str, rpes: list[int], hard_pct: int | None, weeks_left: int | None,
    target_time: str | None, race_label: str, scale: EffortScale = effort_scale.UNKNOWN,
) -> Finding | None:
    """Esforço percebido ABAIXO DO HABITUAL DELE E 0% do tempo em zona forte, com prova datada e
    meta de tempo a poucas semanas: o treino pode estar leve demais pro que a meta pede (ou é base
    deliberada — por isso é pra OLHAR). Só vale quando o número dele acompanha o treino: quem
    responde 3 em tudo (ou 2-3 por hábito) não tem "esforço baixo" a acusar."""

    if weeks_left is None or not target_time:

        return None

    if not (EFFORT_WEEKS[0] <= weeks_left <= EFFORT_WEEKS[1]) or hard_pct != 0:

        return None

    if len(rpes) < RPE_MIN_REPORTS:

        return None

    if not scale.below_habit(rpes):

        return None

    return Finding(
        profile, "esforco_baixo", WATCH,
        f"O esforço que ele relata está abaixo do normal dele (mediana {median(rpes):g} nas "
        f"últimas {len(rpes)} corridas, contra {scale.median:g} de sempre) e ele não correu nada "
        f"em zona forte (0% do tempo), com {race_label} em {weeks_left} semanas "
        f"(meta {target_time}).",
    )


def asked_more_unanswered(
    profile: str, asks: list, since: dict | None, today: date, body_tired: bool,
) -> Finding | None:
    """Ele pediu mais carga e, depois de `ASK_MIN_DAYS`, a dose (km/semana e maior treino) não
    subiu — sem o corpo dele justificar. É o erro de ignorar em silêncio."""

    if not asks or since is None or body_tired:

        return None

    first = asks[0]

    days = (today - first.day).days

    if days < ASK_MIN_DAYS:

        return None

    week_up = since["after_week"] >= since["before_week"] * ASK_WEEK_GAIN

    long_up = since["after_long"] > since["before_long"] * ASK_LONG_GAIN

    if week_up or long_up:

        return None

    return Finding(
        profile, "pediu_mais_sem_resposta", HIGH,
        f"Em {_fmt_date(first.day)} ele disse \"{first.quote}\" e, há {days} dias, o treino dele "
        f"não aumentou: antes ~{since['before_week']:.0f} km por semana e maior treino "
        f"{since['before_long']:.1f} km; depois ~{since['after_week']:.0f} km por semana e maior "
        f"treino {since['after_long']:.1f} km. O corpo dele não justifica segurar.",
    )


def path_gap(profile: str, path) -> Finding | None:
    """Pro passo atual, a prova chega perto e o preparo fica abaixo da faixa de referência."""

    if path is None or path.weeks_left > PATH_WEEKS_LEFT:

        return None

    gaps = []

    if path.long_gap >= PATH_LONG_GAP_KM:

        gaps.append(f"~{round(path.long_gap)} km no longão")

    if path.week_gap >= PATH_WEEK_GAP_KM:

        gaps.append(f"~{round(path.week_gap)} km por semana")

    if not gaps:

        return None

    return Finding(
        profile, "rota_abaixo_da_faixa", WATCH,
        f"Faltam {path.weeks_left} semanas pra prova. No passo das últimas semanas, ele chega "
        f"com longão de ~{path.projected_long:.0f} km e ~{path.projected_week:.0f} km por semana. "
        f"Pra essa prova o ideal é {path.long_ref[0]}-{path.long_ref[1]} km no longão e "
        f"{path.week_ref[0]}-{path.week_ref[1]} km por semana: faltam {' e '.join(gaps)}.",
    )


def stagnant_form(
    profile: str, direction: str | None, weeks: int, weeks_left: int | None,
) -> Finding | None:
    """Forma estável há semanas com a prova perto: o plano não está rendendo evolução."""

    if direction != "STABLE" or weeks < STAGNANT_WEEKS:

        return None

    if weeks_left is None or weeks_left > STAGNANT_RACE_WEEKS:

        return None

    return Finding(
        profile, "forma_estagnada", WATCH,
        f"O condicionamento dele não melhora há ~{weeks} semanas (o corpo não fica mais "
        f"eficiente no mesmo esforço) e a prova é em {weeks_left} semanas.",
    )


def easy_heavy(
    profile: str, easy: int, total: int, target_time: str | None,
) -> Finding | None:
    """Metade ou mais das sessões prescritas é rodagem leve/regenerativa e ele tem META DE TEMPO:
    o plano pode estar com treino demais sem estímulo e sem função pra evoluir."""

    if not target_time or total < EASY_MIN_SESSIONS or easy / total < EASY_SHARE_MAX:

        return None

    return Finding(
        profile, "rodagem_demais", WATCH,
        f"{easy} de {total} treinos planejados nas últimas {EASY_WINDOW_WEEKS} semanas "
        f"({easy / total:.0%}) são corridas leves ou de recuperação, e ele tem meta de tempo "
        f"({target_time}).",
    )


def no_quality(
    profile: str, days_since: int | None, runs: int, target_time: str | None,
) -> Finding | None:
    """Correndo normalmente, com meta de tempo, mas sem NENHUM estímulo forte feito (limiar, VO2,
    ritmo de prova, fartlek, progressivo) há semanas. `days_since` None = nenhum nas últimas 8."""

    if not target_time or runs < NO_QUALITY_MIN_RUNS:

        return None

    if days_since is not None and days_since < NO_QUALITY_DAYS:

        return None

    since = f"há {days_since} dias" if days_since is not None else "nas últimas 8 semanas"

    return Finding(
        profile, "sem_estimulo_forte", WATCH,
        f"Nenhum treino forte (limiar, VO2, ritmo de prova, fartlek ou progressivo) feito "
        f"{since}, com {runs} corridas nos últimos {NO_QUALITY_DAYS} dias e meta de "
        f"{target_time}.",
    )


def stalled_plan(
    profile: str, weekly_km: list[float], longest_km: list[float], adherence: float | None,
) -> Finding | None:
    """Volume e maior treino praticamente iguais por `STALL_WEEKS` semanas fechadas com o plano em
    dia: o plano parou de progredir (é pra olhar: pode ser manutenção de propósito)."""

    weeks = weekly_km[-STALL_WEEKS:]

    longs = longest_km[-STALL_WEEKS:]

    if len(weeks) < STALL_WEEKS or min(weeks) <= 0:

        return None

    if adherence is not None and adherence < STALL_MIN_ADHERENCE:

        return None

    mean = sum(weeks) / len(weeks)

    if (max(weeks) - min(weeks)) / mean > STALL_KM_SPREAD:

        return None

    if max(longs) - min(longs) > STALL_LONG_SPREAD_KM:

        return None

    return Finding(
        profile, "plano_parado", WATCH,
        f"O volume (~{mean:.0f} km por semana, variando só {(max(weeks) - min(weeks)) / mean:.0%}) "
        f"e o maior treino (~{max(longs):.0f} km) estão iguais há {STALL_WEEKS} semanas, e ele "
        "está cumprindo o plano.",
    )


def low_adherence(profile: str, done: int, planned: int, weeks: int) -> Finding | None:
    """Cumpriu pouco do plano nas últimas semanas: o plano pode estar desalinhado da rotina dele
    (dias, volume ou tipo) — prescrever o que ele não faz não evolui ninguém."""

    if planned < ADHERENCE_MIN_PLANNED or weeks < ADHERENCE_WEEKS:

        return None

    if done / planned >= ADHERENCE_LOW:

        return None

    return Finding(
        profile, "aderencia_baixa", WATCH,
        f"Cumpriu {done} de {planned} treinos nas últimas {weeks} semanas ({done / planned:.0%}). "
        "O plano pode não combinar com a rotina dele (dias, volume ou tipo de treino).",
    )


def sawtooth(profile: str, weeks: list[tuple[date, float, bool]]) -> Finding | None:
    """O volume PRESCRITO sobe e desce em dente de serra: `weeks` = (semana, km prescritos, tem
    motivo escrito — descarga ou nota da rota), da mais antiga pra mais recente. Variação acima de
    `SAWTOOTH_SWING` sem motivo, ao menos `SAWTOOTH_MIN_SWINGS` vezes: o plano de cada semana está
    nascendo do ruído da anterior, não de um desenho.

    Só vale pra semanas VIZINHAS — um "salto" entre duas semanas com buracos no meio não é salto
    (Renato, 29/10: 29 km em 21/09 e 18 km em 12/10, sem plano guardado nas semanas entre elas) — e
    só enquanto AINDA acontece: a mudança mais recente precisa ser um salto sem motivo. O que já se
    acalmou é história que ninguém consegue consertar."""

    tail = [weeks[-1]] if weeks else []

    for item in reversed(weeks[:-1]):

        if (tail[0][0] - item[0]).days != 7:

            break

        tail.insert(0, item)

    swings = []

    for (_, before, _), (week, after, explained) in zip(tail, tail[1:]):

        if before <= 0 or after <= 0 or explained:

            continue

        change = after / before - 1

        if abs(change) > SAWTOOTH_SWING:

            swings.append((week, before, after))

    if len(swings) < SAWTOOTH_MIN_SWINGS or swings[-1][0] != tail[-1][0]:

        return None

    km = " → ".join(f"{v:.0f}" for _, v, _ in tail[-6:])

    return Finding(
        profile, "dente_de_serra", WATCH,
        f"Os km planejados por semana sobem e descem bruscamente ({km} km): {len(swings)} "
        f"mudanças de mais de {SAWTOOTH_SWING:.0%} de uma semana pra outra, e o coach não "
        "explicou o motivo.",
    )


def jump_over_done(
    profile: str, week: date, planned: float, prev_done: float, sustained: float | None,
    explained: bool, note: str | None = None,
) -> Finding | None:
    """O papel desta semana passou muito do que ele FEZ (o maior entre a semana anterior e o que
    ele sustenta). Prescrever por cima do papel e não do feito é descartar o que ele cumpriu. Sem
    motivo escrito alerta a partir de `JUMP_OVER_DONE`; COM motivo só num salto de
    `JUMP_EXPLAINED_MAX` ou mais — um motivo não justifica qualquer salto."""

    base = max(prev_done, sustained or 0.0)

    if planned <= 0 or base <= 0 or planned < base * JUMP_OVER_DONE:

        return None

    head = (
        f"O plano de {_fmt_date(week)} pede ~{planned:.0f} km: {planned / base - 1:+.0%} "
        f"sobre o que ele fez (semana anterior {prev_done:.0f} km; ele costuma sustentar "
        f"~{(sustained or 0):.0f} km)"
    )

    if not explained:

        return Finding(
            profile, "salto_sobre_o_feito", HIGH, f"{head}, e o coach não explicou o motivo.",
        )

    if planned < base * JUMP_EXPLAINED_MAX:

        return None

    return Finding(
        profile, "salto_sobre_o_feito", WATCH,
        f"{head}. O coach explicou ({note or 'motivo escrito'}), mas o salto é grande.",
    )


def off_route(
    profile: str, week: date, planned: float, route_km: float | None, explained: bool,
) -> Finding | None:
    """O volume prescrito fugiu da rota (mais que `ROUTE_OFF`) sem o motivo escrito."""

    if explained or not route_km or planned <= 0:

        return None

    change = planned / route_km - 1

    if abs(change) <= ROUTE_OFF:

        return None

    return Finding(
        profile, "desvio_sem_motivo", WATCH,
        f"O plano de {_fmt_date(week)} pede ~{planned:.0f} km, contra ~{route_km:.0f} km da rota "
        f"(a escada de km por semana até a prova): {change:+.0%}, e o coach não explicou o "
        "desvio.",
    )


def route_late(profile: str, pairs: list[tuple[float, float]]) -> Finding | None:
    """Ele fez menos que `ROUTE_LATE_SHARE` da rota por `ROUTE_LATE_WEEKS` semanas fechadas
    seguidas: `pairs` = (km feitos, km da rota), da mais antiga pra mais recente."""

    recent = pairs[-ROUTE_LATE_WEEKS:]

    if len(recent) < ROUTE_LATE_WEEKS or any(r <= 0 for _, r in recent):

        return None

    if not all(done < ROUTE_LATE_SHARE * route for done, route in recent):

        return None

    done_km = ", ".join(f"{d:.0f}" for d, _ in recent)

    route_km = ", ".join(f"{r:.0f}" for _, r in recent)

    return Finding(
        profile, "rota_atrasada", WATCH,
        f"Ele está abaixo da rota (a escada de km por semana até a prova) há {ROUTE_LATE_WEEKS} "
        f"semanas: fez {done_km} km; a rota pedia {route_km} km.",
    )


def calendar_deload(
    profile: str, weeks_plan: list[str] | None, start: date | None, from_week: int,
) -> Finding | None:
    """O bloco aberto pelo coach reserva uma semana de descarga/alívio POR CALENDÁRIO. Descarga só
    existe quando o corpo pede ou o atleta não adere; o papel escrito semanas antes é hipótese que
    o coach precisa redefinir quando a semana chegar. `from_week`: a primeira semana (1-based)
    que ainda importa."""

    from app.application.history.deload_analyzer import is_deload_role

    if not weeks_plan or start is None:

        return None

    hits = [
        (k + 1, role) for k, role in enumerate(weeks_plan)
        if k + 1 >= from_week and is_deload_role(role)
    ]

    if not hits:

        return None

    number, role = hits[0]

    day = start + timedelta(weeks=number - 1)

    return Finding(
        profile, "descarga_por_calendario", WATCH,
        f"O bloco de treino aberto em {_fmt_date(start)} reservou a semana {number} "
        f"({_fmt_date(day)}) como semana leve (\"{role[:90]}\").",
    )


def _strong_counts(summary) -> str:
    """Os números do treino forte em português de corredor (o `headline` do dossiê fala em
    "prescritos / entregues / sem intensidade", que só o coach entende)."""

    text = f"Dos {summary.prescribed} treinos fortes planejados, ele fez {summary.done}"

    if summary.soft:

        text += f"; {summary.soft} saíram em ritmo de leve"

    if summary.unknown:

        text += f"; {summary.unknown} sem como medir"

    return text


def strong_not_delivered(profile: str, summary, today: date) -> Finding | None:
    """Os fortes são prescritos e FEITOS, mas não ENTREGUES: ele corre em ritmo/esforço de leve
    (Leonardo, 29/10: 6 fortes prescritos em 6 semanas, 0 no alvo, esforço 3/10 — o aviso antigo
    dizia só "0% em zona forte", sem semanas nem causa). `summary` = `stimulus_delivery.assess`."""

    from app.application.history import stimulus_delivery as delivery

    if summary is None or summary.done < DELIVERY_MIN_DONE or summary.soft < DELIVERY_MIN_SOFT:

        return None

    weeks = delivery.weeks_since(summary, today)

    if summary.delivered and weeks < DELIVERY_STALE_WEEKS:

        return None

    if summary.last_delivered is None:

        since = f"Nas últimas {delivery.WINDOW_WEEKS} semanas nenhum treino forte bateu o alvo"

    else:

        since = (
            f"Há {weeks} semanas sem um treino forte que bata o alvo "
            f"(o último foi em {_fmt_date(summary.last_delivered)})"
        )

    tail = delivery._tail(summary)

    extra = f" {tail[0].upper()}{tail[1:]}." if tail else ""

    return Finding(
        profile, "forte_sem_intensidade", HIGH,
        f"{since}. {_strong_counts(summary)}.{extra}"
        " Ele faz o treino forte em ritmo de leve: o coach manda, mas o esforço não chega.",
    )


def route_status(done: float | None, route: float | None) -> str | None:
    """Pro painel: o que ele fez na última semana fechada contra a rota."""

    if done is None or not route:

        return None

    ratio = done / route

    if ratio < ROUTE_LATE_SHARE:

        return f"atrás da rota ({done:.0f} de {route:.0f} km)"

    if ratio > 1 + ROUTE_OFF:

        return f"adiante da rota ({done:.0f} de {route:.0f} km)"

    return f"na rota ({done:.0f} de {route:.0f} km)"


def stopped_running(profile: str, days_since: int | None, ill: bool) -> Finding | None:
    """Sem correr há semanas e sem doença registrada: pausa combinada ou afastamento?"""

    if ill or days_since is None or days_since < STOPPED_DAYS:

        return None

    return Finding(
        profile, "parou_de_correr", HIGH,
        f"A última corrida foi há {days_since} dias e não há doença registrada.",
    )


# --- ligação com os dados reais -------------------------------------------------------------------


class CoachSanityAudit:

    @staticmethod
    def athletes() -> list[str]:

        from app.infrastructure.persistence.runner_profile_repository import (
            RunnerProfileRepository,
        )

        return RunnerProfileRepository().list_active()

    @staticmethod
    def audit(profile: str, today: date | None = None) -> list[Finding]:
        """Todos os checks de UM atleta. Cada check é independente e best-effort: um dado
        faltando nunca derruba os outros."""

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.core.clock import today_local

        today = today or today_local()

        data = AthleteDossier._inputs(profile, None, None, None, today)

        findings: list[Finding] = []

        def run(check):

            try:

                found = check(data)

                if found is not None:

                    findings.append(found)

            except Exception as e:  # noqa: BLE001 — um check torto não derruba a auditoria

                print(f"Sanidade: check falhou p/ '{profile}': {e}")

        run(lambda d: CoachSanityAudit._check_race(d))
        run(lambda d: CoachSanityAudit._check_effort(d))
        run(lambda d: CoachSanityAudit._check_asked_more(d))
        run(lambda d: CoachSanityAudit._check_path(d))
        run(lambda d: CoachSanityAudit._check_form(d))
        run(lambda d: CoachSanityAudit._check_easy_heavy(d))
        run(lambda d: CoachSanityAudit._check_no_quality(d))
        run(lambda d: CoachSanityAudit._check_stalled(d))
        run(lambda d: CoachSanityAudit._check_adherence(d))
        run(lambda d: CoachSanityAudit._check_stopped(d))

        for check in CoachSanityAudit._route_checks(data):

            run(check)

        run(lambda d: CoachSanityAudit._check_delivery(d))

        # o achado novo explica os dois mais vagos (esforço baixo / sem estímulo forte): um aviso só
        if any(f.code == "forte_sem_intensidade" for f in findings):

            findings[:] = [
                f for f in findings if f.code not in ("esforco_baixo", "sem_estimulo_forte")
            ]

        return findings

    @staticmethod
    def _check_delivery(data) -> Finding | None:

        from app.application.history import stimulus_delivery

        return strong_not_delivered(
            data.profile, stimulus_delivery.for_profile(data.profile, data.today), data.today,
        )

    @staticmethod
    def _ledger(data):
        """O livro-razão das semanas até a semana SEGUINTE à de hoje (a corrente entra em
        andamento): prescrito × feito, com a rota e o motivo que cada plano guardou."""

        from app.application.coach.context.athlete_dossier import AthleteDossier

        ref = data.today - timedelta(days=data.today.weekday()) + timedelta(weeks=1)

        saved, data.target_week = data.target_week, ref

        try:

            return AthleteDossier._ledger(data)

        finally:

            data.target_week = saved

    @staticmethod
    def _route_checks(data) -> list:

        def sawtooth_check(d):

            weeks = [
                (w.week_start, w.planned_km, bool(w.deload or w.route_note))
                for w in CoachSanityAudit._ledger(d)
            ]

            return sawtooth(d.profile, weeks)

        def jump_check(d):

            from app.application.history import week_ledger

            ledger = CoachSanityAudit._ledger(d)

            if not ledger:

                return None

            last = ledger[-1]

            usual = week_ledger.typical(ledger[:-1])

            return jump_over_done(
                d.profile, last.week_start, last.planned_km, last.prev_done_km,
                usual[0] if usual else None, bool(last.deload or last.route_note),
                last.route_note,
            )

        def off_check(d):

            ledger = CoachSanityAudit._ledger(d)

            last = ledger[-1] if ledger else None

            if last is None or not last.route_km:

                return None

            mid = (last.route_km[0] + last.route_km[1]) / 2

            return off_route(
                d.profile, last.week_start, last.planned_km, mid,
                bool(last.deload or last.route_note),
            )

        def late_check(d):

            pairs = [
                (w.done_km, (w.route_km[0] + w.route_km[1]) / 2)
                for w in CoachSanityAudit._ledger(d)
                if not w.in_progress and w.route_km
            ]

            return route_late(d.profile, pairs)

        def deload_check(d):

            from app.application.coach.planning.ai_plan_service import AIPlanService
            from app.infrastructure.persistence.weekly_plan_repository import (
                WeeklyPlanRepository,
            )

            upcoming = d.today - timedelta(days=d.today.weekday()) + timedelta(weeks=1)

            found = AIPlanService._find_block(WeeklyPlanRepository(), d.profile, upcoming)

            if found is None:

                return None

            block, index = found

            return calendar_deload(
                d.profile, block.get("weeks_plan"), date.fromisoformat(block["start"]), index,
            )

        return [sawtooth_check, jump_check, off_check, late_check, deload_check]

    @staticmethod
    def _check_race(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.history.race_detector import RaceDetector
        from app.infrastructure.persistence.race_result_repository import (
            RaceResultRepository,
        )

        results = RaceResultRepository().load(data.profile)

        event = RaceDetector.most_recent(data.activities, data.today, past_results=results)

        result_dates = [
            RaceDetector._parse_date(r.get("date")) for r in results if r.get("date")
        ]

        list_dates = [
            RaceDetector._parse_date(r.get("date"))
            for r in AthleteDossier._races(data)
            if r.get("date")
        ]

        return unbacked_race(
            data.profile,
            event,
            [d for d in result_dates if d],
            [d for d in list_dates if d],
        )

    @staticmethod
    def _rpes(data) -> list[int]:

        from app.infrastructure.persistence.session_rpe_repository import (
            SessionRpeRepository,
        )

        cutoff = data.today - timedelta(days=RPE_WINDOW_DAYS)

        return [
            s.rpe
            for s in SessionRpeRepository().load_sessions(data.profile)
            if s.rpe is not None and date.fromisoformat(s.day) >= cutoff
        ]

    @staticmethod
    def _races_ahead(data) -> list[dict]:
        """TODAS as provas à frente (A, B e C), da mais próxima pra mais distante, cada uma com o
        seu alvo — não só a principal: o 15 km preparatório a 8 semanas pesa mesmo com a meia (A)
        a 23. Sem lista, a prova do perfil."""

        from app.application.coach.context.athlete_dossier import AthleteDossier

        ahead = []

        for race in AthleteDossier._races(data):

            if not race.get("date"):

                continue

            when = date.fromisoformat(race["date"])

            if when > data.today:

                ahead.append({
                    "date": when,
                    "km": race.get("distance_km"),
                    "target": race.get("target_time"),
                    "role": race.get("priority") or race.get("priority_effective"),
                })

        goal = data.goal

        if not ahead and getattr(goal, "race_date", None) and goal.race_date > data.today:

            ahead.append({
                "date": goal.race_date, "km": goal.distance_km,
                "target": goal.target_time, "role": None,
            })

        return sorted(ahead, key=lambda r: r["date"])

    @staticmethod
    def _race_label(race: dict) -> str:

        km = f"{race['km']:g} km" if race.get("km") else "prova"

        role = {"A": "principal", "B": "preparatória", "C": "de treino"}.get(race.get("role") or "")

        return f"a prova de {km} em {race['date']:%d/%m}" + (f" ({role})" if role else "")

    @staticmethod
    def _check_effort(data) -> Finding | None:
        """O esforço baixo pesa contra a prova MAIS PRÓXIMA dentro da janela — qualquer papel."""

        from app.application.coach.context.athlete_dossier import AthleteDossier

        for race in CoachSanityAudit._races_ahead(data):

            weeks_left = (race["date"] - data.today).days // 7

            if EFFORT_WEEKS[0] <= weeks_left <= EFFORT_WEEKS[1] and race.get("target"):

                return low_effort(
                    data.profile,
                    CoachSanityAudit._rpes(data),
                    AthleteDossier._hard_pct(data),
                    weeks_left,
                    race["target"],
                    CoachSanityAudit._race_label(race),
                    effort_scale.for_data(data.profile, data.activities),
                )

        return None

    @staticmethod
    def _check_asked_more(data) -> Finding | None:

        from app.application.history import athlete_asks_more as asks_more
        from app.domain.entities.body_reading import BODY_RECOVERY_FLAG, BODY_STRAINED
        from app.infrastructure.persistence.checkin_repository import CheckinRepository
        from app.infrastructure.persistence.conversation_repository import (
            ConversationRepository,
        )

        asks = asks_more.find(
            ConversationRepository().load(data.profile),
            CheckinRepository().load(data.profile),
            data.today,
        )

        if not asks:

            return None

        since = asks_more.dose_since(data.activities, asks[0].day, data.today)

        body = getattr(data.reading, "body_state", None)

        return asked_more_unanswered(
            data.profile, asks, since, data.today,
            body_tired=body in (BODY_STRAINED, BODY_RECOVERY_FLAG),
        )

    @staticmethod
    def _check_path(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        return path_gap(data.profile, AthleteDossier.route_path(data))

    @staticmethod
    def _check_form(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        evolution = AthleteDossier._form_of(data)

        if evolution is None or evolution.stale or not evolution.has_data:

            return None

        races = CoachSanityAudit._races_ahead(data)

        weeks_left = (races[0]["date"] - data.today).days // 7 if races else None

        weeks = evolution.ef.weeks_covered if evolution.ef is not None else 0

        return stagnant_form(data.profile, evolution.direction, weeks, weeks_left)

    # --- os checks que não dependem de prova -------------------------------------------------

    @staticmethod
    def _plans(data) -> list:

        from app.infrastructure.persistence.weekly_plan_repository import (
            WeeklyPlanRepository,
        )

        repository = WeeklyPlanRepository()

        plans = list(repository.history(data.profile))

        current = repository.load(data.profile)

        if current is not None:

            plans.append(current)

        return plans

    @staticmethod
    def _check_easy_heavy(data) -> Finding | None:

        from app.application.history.stimulus_ledger import EASY, StimulusLedger

        start = data.today - timedelta(weeks=EASY_WINDOW_WEEKS)

        easy = total = 0

        for plan in {p.week_start: p for p in CoachSanityAudit._plans(data)}.values():

            for session in plan.sessions:

                if getattr(session, "kind", "run") not in ("run", "walk", "run_walk"):

                    continue

                if not start <= plan.session_date(session) <= data.today:

                    continue

                total += 1

                easy += StimulusLedger.classify(session.workout_type) == EASY

        return easy_heavy(data.profile, easy, total, getattr(data.goal, "target_time", None))

    @staticmethod
    def _check_no_quality(data) -> Finding | None:

        from app.application.history import stimulus_ledger as ledger
        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_run_sport

        quality = {
            ledger.RACE_PACE, ledger.HILLS, ledger.FARTLEK, ledger.THRESHOLD, ledger.VO2,
            ledger.PROGRESSION,
        }

        stats = ledger.StimulusLedger.families(
            CoachSanityAudit._plans(data), data.activities, data.today,
        )

        last = [s.last_done for f, s in stats.items() if f in quality and s.last_done]

        days_since = (data.today - max(last)).days if last else None

        since = data.today - timedelta(days=NO_QUALITY_DAYS)

        runs = sum(
            1 for a in data.activities if is_run_sport(a.sport) and activity_date(a) >= since
        )

        return no_quality(
            data.profile, days_since, runs, getattr(data.goal, "target_time", None),
        )

    @staticmethod
    def _adherence(data):

        from app.application.history.adherence_analyzer import AdherenceAnalyzer

        last_closed = data.today - timedelta(days=data.today.weekday() + 7)

        return AdherenceAnalyzer.analyze(
            CoachSanityAudit._plans(data), data.history, until_week=last_closed,
        )

    @staticmethod
    def _check_stalled(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier

        weekly, longest = AthleteDossier.closed_weeks(data)

        report = CoachSanityAudit._adherence(data)

        return stalled_plan(data.profile, weekly, longest, report.rate)

    @staticmethod
    def _check_adherence(data) -> Finding | None:

        report = CoachSanityAudit._adherence(data)

        weeks = report.weeks[-ADHERENCE_WEEKS:]

        return low_adherence(
            data.profile,
            sum(w.done for w in weeks),
            sum(w.planned for w in weeks),
            len(weeks),
        )

    @staticmethod
    def _check_stopped(data) -> Finding | None:

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.application.history.weekly_buckets import activity_date
        from app.domain.value_objects.sports import is_run_sport

        runs = [activity_date(a) for a in data.activities if is_run_sport(a.sport)]

        days = (data.today - max(runs)).days if runs else None

        return stopped_running(
            data.profile, days, AthleteDossier._open_illness(data) is not None,
        )

    @staticmethod
    def snapshot(profile: str, today: date | None = None) -> Snapshot:
        """Os números de UM atleta pro painel: volume e maior treino das últimas 4 semanas
        fechadas, aderência e a próxima prova. Best-effort: o que faltar fica None."""

        from app.application.coach.context.athlete_dossier import AthleteDossier
        from app.core.clock import today_local

        today = today or today_local()

        data = AthleteDossier._inputs(profile, None, None, None, today)

        km_week = long_km = adherence = next_race = route = None

        try:

            weekly, longest = AthleteDossier.closed_weeks(data)

            ran = [v for v in weekly[-4:] if v > 0]

            km_week = sum(ran) / len(ran) if ran else None

            long_km = max(longest[-4:] or [0.0]) or None

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (volume) falhou p/ '{profile}': {e}")

        try:

            adherence = CoachSanityAudit._adherence(data).rate

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (aderência) falhou p/ '{profile}': {e}")

        try:

            races = CoachSanityAudit._races_ahead(data)

            if races:

                weeks = (races[0]["date"] - today).days // 7

                next_race = f"{CoachSanityAudit._race_label(races[0])}, em {weeks} sem"

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (prova) falhou p/ '{profile}': {e}")

        try:

            closed = [
                w for w in CoachSanityAudit._ledger(data) if not w.in_progress and w.route_km
            ]

            if closed:

                last = closed[-1]

                route = route_status(last.done_km, (last.route_km[0] + last.route_km[1]) / 2)

        except Exception as e:  # noqa: BLE001

            print(f"Sanidade: painel (rota) falhou p/ '{profile}': {e}")

        return Snapshot(profile, km_week, long_km, adherence, next_race, route)

    @staticmethod
    def audit_all(today: date | None = None) -> list[Finding]:

        out: list[Finding] = []

        for profile in CoachSanityAudit.athletes():

            try:

                out.extend(CoachSanityAudit.audit(profile, today))

            except Exception as e:  # noqa: BLE001

                print(f"Sanidade: atleta '{profile}' falhou: {e}")

        return out


# --- aviso (cooldown + mensagem + envio) ---------------------------------------------------------


class SanityState:
    """Quando cada achado foi avisado pela última vez — storage/sanity_audit/state.json."""

    def __init__(self, path: Path | None = None):

        self.path = path or (
            Path(__file__).resolve().parents[3] / "storage" / "sanity_audit" / "state.json"
        )

    def load(self) -> dict:

        if not self.path.exists():

            return {}

        try:

            return json.loads(self.path.read_text(encoding="utf-8"))

        except (OSError, ValueError):

            return {}

    def save(self, state: dict) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8",
        )


def _key(finding: Finding) -> str:

    return f"{finding.profile}:{finding.code}"


def fresh(findings: list[Finding], state: dict, today: date) -> list[Finding]:
    """Só os achados que ainda não foram avisados nos últimos `COOLDOWN_DAYS`."""

    out = []

    for finding in findings:

        last = state.get(_key(finding))

        if last and (today - date.fromisoformat(last)).days < COOLDOWN_DAYS:

            continue

        out.append(finding)

    return out


def _name(profile: str) -> str:

    try:

        from app.application.coach.writer.coach_persona import first_name
        from app.application.use_cases.load_runner_profile import LoadRunnerProfile

        return first_name(LoadRunnerProfile.execute(profile).name) or profile

    except Exception:  # noqa: BLE001

        return profile


def _count(n: int, one: str, many: str) -> str:

    return f"{n} {one if n == 1 else many}"


def format_message(
    findings: list[Finding],
    names: dict[str, str] | None = None,
    audited: list[str] | None = None,
    open_findings: list[Finding] | None = None,
) -> str:
    """O aviso pro dono: um bloco por atleta (🔴 alto antes de 🟡 atenção), cada achado com título,
    a frase com os números e o que fazer. Com `audited`, diz QUEM foi olhado: quem está em dia de
    verdade e quem tem aviso antigo ainda aberto (`open_findings` = todos os achados de hoje, novos
    ou em cooldown) — um ✅ só aparece pra quem não tem pendência nenhuma."""

    names = names or {}

    by_profile: dict[str, list[Finding]] = {}

    for finding in sorted(findings, key=lambda f: (f.level != HIGH, f.profile)):

        by_profile.setdefault(finding.profile, []).append(finding)

    serious = sum(1 for f in findings if f.level == HIGH)

    lines = [
        f"🔎 Revisão diária do coach — {_count(len(findings), 'aviso novo', 'avisos novos')}",
        "",
    ]

    if serious:

        lines.append(
            f"{_count(serious, 'ponto sério', 'pontos sérios')} (🔴) e "
            f"{_count(len(findings) - serious, 'pra acompanhar', 'pra acompanhar')} (🟡)."
        )

    else:

        lines.append(
            f"Nada urgente: {_count(len(findings), 'ponto', 'pontos')} pra acompanhar (🟡)."
        )

    lines.append("")

    for profile, items in by_profile.items():

        lines.append(f"{names.get(profile, profile)}")

        for item in items:

            icon = "🔴" if item.level == HIGH else "🟡"

            title = TITLES.get(item.code)

            lines.append(f"{icon} {title}" if title else f"{icon} {item.text}")

            if title:

                lines.append(item.text)

            action = ACTIONS.get(item.code)

            if action:

                lines.append(f"👉 {action}")

            lines.append("")

    if audited:

        still_open = {f.profile for f in open_findings or findings}

        clean = [names.get(p, p) for p in audited if p not in still_open]

        pending = [names.get(p, p) for p in audited if p in still_open and p not in by_profile]

        lines.append(f"Olhei os {len(audited)} atletas hoje.")

        if clean:

            lines.append(f"✅ Em dia, sem nenhuma pendência: {', '.join(clean)}.")

        if pending:

            lines.append(f"🕐 Avisados antes e ainda em aberto: {', '.join(pending)}.")

        lines.append("")

    lines.append(
        f"É só um aviso: nada foi alterado. Cada ponto aberto volta a ser avisado só depois de "
        f"{COOLDOWN_DAYS} dias."
    )

    return "\n".join(lines)


def format_panel(
    snapshots: list[Snapshot],
    findings: list[Finding],
    names: dict[str, str] | None = None,
) -> str:
    """O painel de TODOS os atletas (segunda): um por linha, com o semáforo do que a auditoria viu
    e os números que o coach tem à mão. É a prova de que cada atleta foi olhado."""

    names = names or {}

    by_profile: dict[str, list[Finding]] = {}

    for finding in findings:

        by_profile.setdefault(finding.profile, []).append(finding)

    lines = [f"📋 Painel dos atletas — {len(snapshots)} auditados", ""]

    for snap in snapshots:

        items = by_profile.get(snap.profile, [])

        icon = "🔴" if any(f.level == HIGH for f in items) else ("🟡" if items else "🟢")

        bits = []

        if snap.km_week is not None:

            bits.append(f"~{snap.km_week:.0f} km/sem")

        if snap.long_km:

            bits.append(f"maior treino {snap.long_km:.0f} km")

        if snap.adherence is not None:

            bits.append(f"aderência {snap.adherence:.0%}")

        if snap.next_race:

            bits.append(snap.next_race)

        if snap.route:

            bits.append(snap.route)

        alerts = f" — {len(items)} alerta(s)" if items else ""

        lines.append(f"{icon} {names.get(snap.profile, snap.profile)}{alerts}: " + " · ".join(bits))

    return "\n".join(lines)


async def _send(message: str) -> bool:

    from app.application.notifications.notification_service import (
        TELEGRAM,
        NotificationService,
    )
    from app.core.config import get_settings

    admin_id = get_settings().admin_telegram_id

    if not admin_id:

        print("Sem ADMIN_TELEGRAM_ID: nada enviado.")

        return False

    await NotificationService.send_to(channel=TELEGRAM, address=admin_id, message=message)

    return True


def run(
    send: bool,
    today: date | None = None,
    state: SanityState | None = None,
    force_panel: bool = False,
) -> str:
    """Audita TODOS os atletas ativos. Sem `send`: só mostra (dry-run, ignora o cooldown, mostra o
    painel). Com `send`: avisa o dono dos achados NOVOS (com a cobertura dos auditados) e, na
    segunda-feira (ou com `force_panel`), manda o painel de todos; grava quando avisou. Devolve o
    que foi enviado."""

    from app.core.clock import today_local

    today = today or today_local()

    state = state or SanityState()

    audited = CoachSanityAudit.athletes()

    findings = CoachSanityAudit.audit_all(today)

    stored = state.load()

    pending = fresh(findings, stored, today)

    names = {p: _name(p) for p in audited}

    def panel() -> str:

        snaps = [CoachSanityAudit.snapshot(p, today) for p in audited]

        return format_panel(snaps, findings, names)

    if not send:

        alert = format_message(findings, names, audited, findings) if findings else "Sem achados."

        shown = f"{alert}\n\n{panel()}"

        print(shown)

        print(f"\n({len(pending)} de {len(findings)} seriam enviados agora — fora do cooldown)")

        return shown

    parts = []

    if pending:

        parts.append(format_message(pending, names, audited, findings))

    with_panel = today.weekday() == 0 or force_panel

    if with_panel:

        parts.append(panel())

    if not parts:

        print(f"{today} sanidade: sem achados novos ({len(findings)} em cooldown)")

        return ""

    message = "\n\n".join(parts)

    if asyncio.run(_send(message)):

        for finding in pending:

            stored[_key(finding)] = today.isoformat()

        state.save(stored)

        print(f"{today} sanidade: {len(pending)} achado(s) novo(s), painel={with_panel}")

    return message


def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument("--send", action="store_true")

    # manda o painel de todos os atletas hoje (por padrão só na segunda-feira)
    parser.add_argument("--painel", action="store_true")

    args = parser.parse_args()

    run(send=args.send, force_panel=args.painel)


if __name__ == "__main__":

    main()
