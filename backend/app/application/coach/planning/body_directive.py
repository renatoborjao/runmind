"""Traduz a leitura do corpo numa DIRETRIZ pro coach (a IA-treinadora) pesar ao
montar/ajustar o plano. Quem decide a dose é o coach, não o atleta: a diretriz
diz o que o corpo está pedindo e devolve a decisão pra IA (aliviar, remanejar ou
segurar a subida, conforme meta/momento) — nunca manda perguntar ao atleta.

Puro/determinístico: recebe o veredito já pronto (BodyReading + trajetória) e
devolve texto; string vazia quando o corpo não pede nada. Ver
[[project_analise_corpo_garmin]]."""

from app.domain.entities.body_reading import (
    BODY_RECOVERY_FLAG,
    BODY_STRAINED,
    BodyReading,
)
from app.domain.entities.body_reading_snapshot import (
    TRAJ_PERSISTING,
    BodyTrajectory,
)

_LIMITER = {
    "sono": "o sono (noites curtas)",
    "fc_repouso": "a FC de repouso, que vem subindo",
    "stress": "o stress alto",
}


def body_plan_directive(
    reading: BodyReading,
    trajectory: BodyTrajectory | None = None,
    drift=None,
    aerobic_ceiling: int | None = None,
) -> str:
    """Diretriz pro prompt do plano. Só fala quando o corpo pede atenção
    (STRAINED = sobrecarga real; RECOVERY_FLAG = recuperação caindo); senão
    vazio (o plano fica idêntico ao de hoje)."""

    state = reading.body_state

    if state not in (BODY_STRAINED, BODY_RECOVERY_FLAG):

        return ""

    limiter = _LIMITER.get(reading.limiter or "")

    lim = f" (limitador: {limiter})" if limiter else ""

    persisting = (
        trajectory is not None
        and trajectory.movement == TRAJ_PERSISTING
        and trajectory.alert_streak >= 2
    )

    if state == BODY_STRAINED:

        persist = (
            f" E não é de hoje: {trajectory.alert_streak} leituras seguidas em "
            "alerta — o corpo não está assimilando, dá mais peso a isto."
            if persisting
            else ""
        )

        return (
            "STATUS DO CORPO (você é o COACH — pese isto na dose desta semana; "
            "NÃO pergunte ao atleta, a decisão é sua): o corpo dele está "
            f"pedindo RECUPERAÇÃO — a carga subiu e a recuperação caiu{lim}."
            f"{persist} Priorize assimilar em vez de empilhar carga: alivie o "
            "volume/intensidade desta semana, ou remaneje o treino mais forte, "
            "conforme a meta e o momento dele. Recuperar bem AGORA é o que "
            "sustenta a evolução — não mantenha a carga cega."
        )

    # RECOVERY_FLAG com PIORA OBJETIVA (FC de repouso subindo / HRV caindo vs a
    # BASE do próprio atleta, em alerta há 3+ leituras): não é o normal dele —
    # SEGURA. Antes o critério era "confirme nos aprendizados se é baseline"
    # (vago) e o plano empurrou longão progressivo "pra avançar o teto" com a
    # FC de repouso do Renato em 59→70 — enquanto o retrato prometia "o plano
    # segura a intensidade". Segurar ≠ descarregar: mantém o volume, não sobe.
    if drift is not None and getattr(drift, "worsening", False):

        return _hold_directive(reading, drift, aerobic_ceiling, lim)

    # RECOVERY_FLAG: a recuperação deu um sinal, mas a CARGA está tranquila.
    # NÃO é freio automático — o coach pesa contra a CAPACIDADE do atleta. Um
    # limitador CRÔNICO que ele sustenta (ex.: sono curto com corpo equilibrado)
    # não pode encolher a dose toda semana, senão ele fica subtreinado pra sempre.
    recur = (
        f" Esse sinal se repete ({trajectory.alert_streak} leituras) — confirme "
        "nos APRENDIZADOS se é o BASELINE dele (que ele sustenta) ou se está "
        "piorando de verdade."
        if persisting
        else ""
    )

    return (
        "STATUS DO CORPO (você é o COACH — decide a dose pesando o QUADRO "
        f"INTEIRO): a carga está tranquila, mas a recuperação deu um sinal{lim}."
        f"{recur} PESE contra a capacidade dele: se esse limitador é o "
        "normal/baseline dele (os aprendizados mostram que ele SUSTENTA assim) e "
        "a carga está tranquila, NÃO trave a progressão por isto — é o normal "
        "dele, não um alerta. Só segure a subida se a recuperação estiver caindo "
        "DE VERDADE agora (agudo). Nunca corte volume à toa."
    )


def _hold_directive(reading: BodyReading, drift, aerobic_ceiling, lim: str) -> str:
    """Recuperação PIORANDO de verdade: segura a progressão com instruções
    concretas (sem subir, qualidade controlada, leve pela FC)."""

    evidence = []

    if drift.rhr_base and drift.rhr_now:

        evidence.append(
            f"FC de repouso {drift.rhr_base:.0f} → {drift.rhr_now:.0f} bpm"
        )

    if drift.hrv_base and drift.hrv_now:

        evidence.append(f"HRV {drift.hrv_base:.0f} → {drift.hrv_now:.0f}")

    if drift.sleep_avg:

        evidence.append(f"sono médio {drift.sleep_avg:.1f}h")

    cap = (
        f" com TETO de FC ~{aerobic_ceiling} bpm (escreva hr_max nos passos "
        "dos leves e do longão — o relógio avisa)"
        if aerobic_ceiling
        else " pela FC (conversável, sem apertar)"
    )

    return (
        "STATUS DO CORPO — PIORA REAL DA RECUPERAÇÃO (não é o normal dele; "
        f"você é o COACH, a decisão é sua){lim}: em alerta há "
        f"{drift.alert_streak} leituras seguidas, {', '.join(evidence)} — contra "
        "a própria base de semanas atrás. O que um bom treinador costuma fazer "
        "nesse quadro: SEGURAR a progressão (sem subir volume nem intensidade "
        "sobre a semana passada), qualidade enxuta e controlada (limite de baixo "
        "da faixa, menos repetições), longão sem progressão/blocos fortes, leves "
        f"e longão{cap}. Não é descarga (o volume se mantém): é segurar até o "
        "sinal virar. Pese isso com o resto do quadro e decida; o que escolher, "
        "diga no purpose/mensagem com franqueza — e que o sono é a alavanca dele."
    )
