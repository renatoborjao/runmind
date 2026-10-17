"""CALENDÁRIO de provas: o coach enxerga TODAS as provas à frente do atleta (com
distância, papel e intervalo entre elas), não só a mais próxima.

Até aqui o plano ancorava na prova futura mais próxima e as demais viravam só
texto na memória. Com várias provas isso erra os dois lados: trata a
preparatória como o fim do ciclo (polimento completo) ou ignora a principal que
vem depois. O papel de cada prova (A principal · B preparatória · C de treino)
diz o quanto o ciclo se organiza em torno dela — vem da lista do app
(`RaceService.list`: o que o atleta escolheu, senão a sugestão).

MAIS UM insumo, não decreto: dado + conhecimento de periodização + "decida"
([[feedback_ia_decide_sem_regras]]). Puro/determinístico. Substitui a hierarquia
por TEXTO (`race_hierarchy_directive`) quando há calendário de verdade; com uma
prova só (sem papel B/C escolhido) nada muda. Ver [[project_n_provas_design]]."""

from datetime import date

_HEAD = (
    "CALENDÁRIO DE PROVAS (mais um insumo pra você, o COACH — não decreto): "
)

_ROLE_NAME = {
    "A": "PRINCIPAL (A)",
    "B": "PREPARATÓRIA (B)",
    "C": "DE TREINO (C)",
}

_HOW_TO_READ = (
    "PAPÉIS: A principal — o ciclo vai rumo a ela: pico de especificidade, "
    "polimento completo (10 km ~7–10 dias, meia ~10–14, maratona ~2–3 semanas) e "
    "recuperação depois. B preparatória — marco no caminho: mira a meta dela e "
    "testa forma/ritmo, só com MINI-polimento (~4–6 dias de volume menor, com um "
    "toque de intensidade), sem reorganizar o ciclo; recupere e retome rumo à "
    "principal. C de treino — vira treino (longão ritmado/qualidade), sem "
    "polimento. Menos de ~3 semanas entre provas: a de menor papel vira treino. "
    "Os sinais automáticos (fase, 'prova em N sem', descarga) seguem a PRÓXIMA "
    "prova: se ela é B/C, leia-os pelo papel dela."
)

_SUGGESTED_NOTE = (
    "'sugerido' = o atleta ainda não confirmou: hipótese razoável (confirme com "
    "ele se vier ao caso)."
)


def future_races(races: list[dict], today: date) -> list[dict]:
    """Provas ainda por vir (hoje conta), da mais próxima pra mais distante."""

    iso = today.isoformat()

    return sorted(
        (r for r in races if r.get("date") and r["date"] >= iso),
        key=lambda r: r["date"],
    )


def has_calendar(races: list[dict], today: date) -> bool:
    """Há calendário de verdade? Duas ou mais provas à frente, ou UMA com papel
    B/C que o próprio atleta escolheu (aí o papel muda como o plano a trata)."""

    ahead = future_races(races, today)

    if len(ahead) >= 2:

        return True

    return len(ahead) == 1 and ahead[0].get("priority") in ("B", "C")


def race_calendar_directive(races: list[dict], today: date) -> str:
    """Diretriz com o calendário. Vazia quando não há calendário (ver
    `has_calendar`) — o chamador segue com a âncora e a hierarquia por texto."""

    if not has_calendar(races, today):

        return ""

    ahead = future_races(races, today)

    lines = [f"{_HEAD}o atleta tem {len(ahead)} prova(s) à frente:"]

    previous: date | None = None

    for race in ahead:

        when = date.fromisoformat(race["date"])

        lines.append(f"• {_describe(race, when, today, previous)}")

        previous = when

    lines.append(_HOW_TO_READ)

    if any(
        not r.get("priority") and r.get("priority_effective") for r in ahead
    ):

        lines.append(_SUGGESTED_NOTE)

    return "\n".join(lines)


def _describe(
    race: dict, when: date, today: date, previous: date | None
) -> str:

    parts = [f"{when.strftime('%d/%m/%Y')} — {race.get('name') or 'prova'}"]

    km = race.get("distance_km")

    if km:

        parts.append(f"{km:.1f} km".replace(".0 km", " km"))

    if race.get("target_time"):

        parts.append(f"alvo {race['target_time']}")

    weeks = (when - today).days // 7

    parts.append(f"em {weeks} semana(s)" if weeks else "esta semana")

    if previous is not None:

        gap = (when - previous).days // 7

        parts.append(f"{gap} sem. depois da anterior")

    parts.append(_role_text(race))

    return " · ".join(parts)


def _role_text(race: dict) -> str:

    chosen = race.get("priority")

    effective = race.get("priority_effective")

    if chosen in _ROLE_NAME:

        return f"papel: {_ROLE_NAME[chosen]}"

    if effective in _ROLE_NAME:

        return f"papel: {_ROLE_NAME[effective]}, sugerido"

    return "papel: não definido (decida pelo contexto)"
