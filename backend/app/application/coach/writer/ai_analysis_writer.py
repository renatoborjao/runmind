import json
import re
from dataclasses import dataclass

from google.genai import types

from app.application.coach.context.coach_context import CoachContext
from app.application.coach.intelligence.perception_recorder import (
    WATCH_FEEL_WORDS,
)
from app.application.coach.writer.coach_persona import COACH_VOICE, first_name
from app.application.coach.writer.labels import (
    intensity_label,
    plan_workout_label,
    workout_type_label,
)
from app.application.external_plan.treino_online_legend import (
    legend_for_prompt,
)
from app.application.history.hr_zone_history import HrZoneHistory
from app.application.planner.pace_formatter import PaceFormatter
from app.core.clock import today_local
from app.core.config import get_settings
from app.domain.entities.workout_structure import WorkoutStructure
from app.domain.value_objects.hr_zones import zone_share_label
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# Pro pensa (thinking) e isso conta no orçamento de saída + é cobrado como
# output. Teto de thinking EXPLÍCITO + max_output com folga pra caber
# thinking + a análise (senão o thinking come tudo e volta vazio).
THINKING_BUDGET = 512

MAX_OUTPUT_TOKENS = 2000

# Quantas bullets a IA pode devolver na seção de análise.
MAX_BULLETS = 4

# Saída ESTRUTURADA: o modelo é obrigado a emitir o objeto abaixo — elimina a
# quebra de JSON (e o retry PAGO). É de graça (config na mesma chamada). Só o
# corte por token ainda pode quebrar — daí o max_output com folga.
#   headline  — a abertura com o veredito VERDADEIRO (substitui o "Parabéns"
#               automático que abria até treino que não saiu)
#   analysis  — a leitura do treino
#   attention — o puxão de orelha, só quando o dado/padrão pede (senão null)
#   next_step — o que fazer no próximo treino, concreto (substitui as frases
#               prontas de recuperação/histórico)
ANALYSIS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "headline": types.Schema(type=types.Type.STRING),
        "analysis": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        ),
        "attention": types.Schema(type=types.Type.STRING, nullable=True),
        "next_step": types.Schema(type=types.Type.STRING),
    },
    required=["headline", "analysis", "next_step"],
)


@dataclass(slots=True)
class AIAnalysis:
    """A leitura do treino pela IA-treinadora (ver ANALYSIS_SCHEMA)."""

    headline: str | None
    analysis: list[str]
    attention: str | None
    next_step: str | None

# Fatos SEM veredito: "apagou/quebrou" é conclusão, não dado — quando o
# rótulo já vinha com julgamento, a IA amplificava (+4% virava "você
# quebrou"). O grau fica no fato; a leitura fica com a IA.
TREND_LABELS = {
    "negative": "acelerou no fim (negative split)",
    "even": "ritmo constante do início ao fim",
    "positive_mild": (
        "segunda metade um pouco mais lenta que a primeira "
        "(diferença pequena, faixa de variação normal)"
    ),
    "positive": "queda acentuada de ritmo na segunda metade",
    "unknown": "sem dado de progressão",
}

# abaixo disso a "volta" é fantasma (relógio reiniciando, lap acidental), não
# um bloco de treino de verdade
_MIN_LAP_M = 30

PROMPT_TEMPLATE = """{voice}
AGORA: o treino deste atleta ACABOU de sair. Escreva a sua leitura dele, por \
mensagem (WhatsApp) — honesta e ESPECÍFICA deste treino.

FATOS DO TREINO + DOSSIÊ DO ATLETA (use SÓ isto, não invente número nenhum):
{facts}

O QUE LER NOS FATOS:
- INTENÇÃO × EXECUÇÃO: compare o que o treino PEDIA (tipo, pace, blocos, \
intenção) com o que saiu. O critério de LEVE é o TETO AERÓBICO dele (nos \
fatos): leve/regenerativo/longão-base com FC acima do teto NÃO foi leve, mesmo \
com o pace no alvo — diga isso, não chame de "controle". Abaixo do teto FOI \
leve, qualquer que seja o número da zona do relógio (na régua pela FC máxima, \
a Z3 inteira pode ficar abaixo do teto — não cobre Z3 abaixo do teto). Passar \
do combinado num dia leve não é mérito. Cortar/não completar a sessão-chave \
pesa.
- FC × PACE: FC subindo com o pace parado (deriva, desacoplamento) = fadiga, \
calor ou base curta. Em tiros, FC de recuperação quase igual à de pico \
(diferença menor que ~10 bpm) = pausa curta/rápida demais ou corpo cansado.
- PERCEPÇÃO: RPE/sensação do atleta (deste treino e os relatos recentes do \
dossiê) batendo ou não com a FC/pace — divergência é informação, comente.
- PADRÕES RECENTES: se o de hoje REPETE um padrão ruim, é aí que se cobra; se \
hoje QUEBROU um padrão ruim, reconheça de verdade (é evolução).
- Comente o que ESTES dados mostram — estrutura/splits (tiros, se manteve o \
ritmo, se acelerou ou caiu no fim). Nada de frase genérica que serviria pra \
qualquer treino.
- NÃO contradiga os fatos. Se o treino foi um intervalado, trate como \
intervalado (não chame de leve).
- Se houver "Execução por bloco", COMPARE os blocos executados com a \
estrutura PRESCRITA (use a legenda pra decodificar as siglas). O atleta pode \
ter CUMPRIDO a estrutura (ex.: alternou 3' corrida / 2' caminhada) mesmo que \
os splits por km pareçam constantes — os blocos revelam isso; não afirme que \
ele "não fez" o treino sem olhar os blocos. Se cumpriu os blocos mas com \
pouco contraste (recuperação rápida demais), aponte ISSO, não a ausência. \
As voltas executadas podem estar em ordem diferente ou faltar um bloco \
prescrito (ex.: aquecimento que o relógio não registrou por ter reiniciado) — \
ALINHE por bom senso e NÃO acuse o atleta de ter pulado um bloco que só não \
foi gravado.
- Se a "Execução por bloco" vier marcada "(comparação EXATA, já calculada)", \
os vereditos "[pace dentro/fora do alvo]", "[FC ...]" e "Não completou" JÁ \
FORAM CALCULADOS por código — use-os como estão, NÃO recalcule nem questione a \
conta. Pace no alvo com "[FC ACIMA do teto aeróbico]" = o pace saiu certo mas \
NÃO foi leve (diga isso; não chame de "controle"). Bloco sem veredito (sem \
"[...]") não tinha alvo definido (ex.: aquecimento livre) — neutro.
- AMBIENTE: descubra onde o treino foi SÓ pela linha "Ambiente" dos fatos — \
NUNCA deduza da prescrição nem de preferências (a prescrição pode SUGERIR \
esteira como opção sem que o atleta a tenha usado). Se "Ambiente: ESTEIRA", a \
distância e o pace do RELÓGIO podem divergir do real (o relógio estima): NÃO \
cobre diferença de distância nem de pace, use a DISTÂNCIA PLANEJADA como \
referência e foque em execução, FC/esforço, consistência dos tiros e \
recuperação. Se "Ambiente: AR LIVRE", a distância e o pace são REAIS — JAMAIS \
chame de esteira nem justifique diferença de distância com "esteira".
- VOCABULÁRIO DE RITMO: só use palavras como "quebrou", "apagou" ou "não \
aguentou" se os fatos disserem "queda ACENTUADA de ritmo". Segunda metade \
"um pouco mais lenta" é variação normal de treino (subida, calor, semáforo) \
— trate como normal, sem tom de falha.
- POST-MORTEM (por que foi assim): se ele ficou ABAIXO do esperado (paces \
fora do alvo, FC alta pro ritmo, não completou), CONECTE à causa provável que \
está nos fatos (sono curto, corpo em alerta, carga, calor). Um dia ruim \
isolado não é forma perdida — mas se a MESMA causa se repete (PADRÕES \
RECENTES: sono curto há semanas, recuperação piorando), ela deixou de ser \
"condição do dia": é o problema a resolver, e você diz isso. Se ele foi bem \
apesar de um contexto ruim, reconheça o treino — sem transformar o sinal ruim \
do corpo em qualidade. NUNCA invente causa que não esteja nos fatos; se o \
desempenho foi normal/bom, não force desculpa.
- DORES/LESÕES: se o dossiê trouxer lesão/limitação declarada ou dor/doença nos \
relatos, leve SEMPRE em conta — NUNCA cobre \
desempenho, ritmo ou volume ignorando uma dor ou lesão declarada. Reconheça, \
priorize recuperação e, se for dor, oriente cautela (e procurar profissional se \
persistir). Jamais mande "forçar" ou "compensar" em cima de dor.
- DOSSIÊ (quem é o atleta, evolução, corpo, padrões, plano, o que você já \
disse): use pra PERSONALIZAR — conecte este treino à trajetória/evolução dele, respeite \
o que ele já te contou (memória) e o que você aprendeu que funciona ou não pra \
ele. Você não é um robô olhando só hoje: é o treinador que acompanha esse \
atleta há tempo. Nunca contrarie esses fatos nem invente além deles, e NÃO \
contradiga o que você mesmo já decidiu/disse (plano da semana, bom dia) — se o \
treino de hoje muda a leitura, diga o que mudou. Memória \
de "recuperação rápida"/"recupera acelerado" é sobre a DOSE do plano — não \
apaga sinal de FC/sono na execução e nunca vira elogio.
- Fale com "você", português do Brasil.

RESPONDA APENAS JSON com:
- "headline": UMA frase curta (até ~12 palavras) que ABRE a mensagem, com o \
primeiro nome dele e o veredito VERDADEIRO do treino. Treino bom de fato: pode \
celebrar. Abaixo do esperado: diga com respeito, sem drama. Nada de "Parabéns" \
automático. No máximo 1 emoji, no fim.
- "analysis": 2 a {max_bullets} frases curtas, cada uma um ponto específico \
destes dados. Sem emojis, sem títulos.
- "attention": null OU 1-2 frases — o PUXÃO DE ORELHA, só quando um padrão \
(PADRÕES RECENTES) ou uma escolha de hoje atrapalha o objetivo dele: nomeie o \
comportamento, cite o dado, diga o custo pro objetivo e o que fazer. Sem nada \
sério, null (não invente cobrança só pra ter).
- "next_step": 1 frase CONCRETA pro próximo treino/dias, ligada ao que \
aconteceu hoje — se houver "Próximo treino do plano" nos fatos, diga o que \
fazer DIFERENTE nele (teto de FC, ritmo, dose, sono). Nada genérico tipo \
"descanse bem" ou "se houver fadiga, pegue leve".
{{"headline": "...", "analysis": ["..."], "attention": null, "next_step": "..."}}
"""


class AIAnalysisWriter:
    """Escreve a seção de análise do feedback via IA, ancorada nos fatos
    determinísticos + na estrutura real do treino (splits/voltas). Se a IA
    falhar ou vier vazia, retorna None e o pipeline cai no texto
    determinístico — feedback nunca vira silêncio."""

    @staticmethod
    async def write(
        context: CoachContext,
    ) -> AIAnalysis | None:

        try:

            facts = AIAnalysisWriter._facts(context)

            settings = get_settings()

            # generate_json re-gera se o JSON vier torto (o modelo escorrega
            # às vezes) — a análise é o coração do produto, não pode cair no
            # genérico à toa. Só cai no fallback se TODAS as tentativas
            # falharem.
            return await generate_json(
                model=settings.gemini_coach_model,
                contents=PROMPT_TEMPLATE.format(
                    voice=COACH_VOICE,
                    facts=facts,
                    max_bullets=MAX_BULLETS,
                ),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ANALYSIS_SCHEMA,
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    thinking_config=types.ThinkingConfig(
                        thinking_budget=THINKING_BUDGET,
                    ),
                ),
                parse=AIAnalysisWriter._parse,
            )

        except Exception as e:

            # IA fora do ar / JSON inválido / vazio: cai no determinístico
            print(f"IA falhou na análise do treino, fallback: {e}")

            return None

    @staticmethod
    def _parse(
        raw: str,
    ) -> AIAnalysis | None:
        """Repara + valida a resposta. Devolve None em QUALQUER problema
        (JSON torto, estrutura errada, análise vazia) pra o generate_json
        re-gerar. Abertura/atenção/próximo passo são opcionais: faltando, a
        mensagem usa o neutro (nunca quebra por eles)."""

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError, ValueError):

            return None

        if not isinstance(data, dict):

            return None

        bullets = data.get("analysis")

        if not isinstance(bullets, list):

            return None

        lines = [
            str(item).strip()
            for item in bullets
            if str(item).strip()
        ]

        if not lines:

            return None

        return AIAnalysis(
            headline=AIAnalysisWriter._text(data.get("headline")),
            analysis=lines[:MAX_BULLETS],
            attention=AIAnalysisWriter._text(data.get("attention")),
            next_step=AIAnalysisWriter._text(data.get("next_step")),
        )

    @staticmethod
    def _text(value) -> str | None:
        """Campo de texto opcional: vazio/"null"/não-string vira None."""

        if not isinstance(value, str):

            return None

        text = value.strip()

        if not text or text.lower() in ("null", "none", "-"):

            return None

        return text

    @staticmethod
    def _planned_target(planned) -> str:
        """Alvo do treino planejado pra linha 'Planejado:': distância OU
        duração (treino POR TEMPO) + faixa de pace, o que existir. Espelha o
        que o plano da semana já mostra ao atleta — assim a IA compara o
        executado com a régua certa (inclusive longão por tempo)."""

        parts = []

        if planned.planned_distance_km:

            parts.append(f"{planned.planned_distance_km:.1f} km")

        elif planned.planned_duration_minutes:

            parts.append(f"{planned.planned_duration_minutes} min")

        pace = AIAnalysisWriter._pace_range(planned)

        if pace:

            parts.append(pace)

        return " · ".join(parts)

    @staticmethod
    def _pace_range(planned) -> str:
        """Faixa de pace alvo (M:SS/km). Range quando min≠max, valor único
        quando iguais, vazio quando não há."""

        pace_min = planned.target_pace_min

        pace_max = planned.target_pace_max

        if pace_min and pace_max:

            if pace_min == pace_max:

                return f"{pace_min}/km"

            return f"{pace_min}–{pace_max}/km"

        if pace_min:

            return f"{pace_min}/km"

        return ""

    @staticmethod
    def _facts(
        context: CoachContext,
    ) -> str:

        runner = context.runner

        executed = context.executed

        activity = executed.activity

        lines = [f"Atleta: {first_name(runner.name) or runner.name}"]

        if context.planned is not None:

            planned = context.planned

            planned_line = plan_workout_label(
                planned.workout_type,
                planned.planned_distance_km,
            )

            # alvo do treino: distância OU duração (treino POR TEMPO) + faixa
            # de pace, o que houver. Sem isto, um longão "1h45 entre 4:20 e
            # 4:40/km" chegaria à análise só como "Longão" — sem a régua certa
            # pra comparar o executado.
            target = AIAnalysisWriter._planned_target(planned)

            if target:

                planned_line += f" — {target}"

            lines.append(f"Planejado: {planned_line}")

            # prescrição (blocos/séries) pra IA comparar a execução com o que
            # foi pedido, não só distância crua. Treinador externo guarda a
            # prescrição em `notes` (com siglas do "Treino Online"), não em
            # `structure` — aí manda a LEGENDA junto pra IA decodificar
            # (CCR/CCL/FF/CAM...) e comparar com o executado.
            prescription = planned.structure or planned.notes

            if prescription:

                lines.append(
                    "Prescrição do treino: "
                    + prescription.strip().replace("\n", " | ")[:700]
                )

                if not planned.structure and planned.notes:

                    lines.append(
                        "Legenda das siglas do treinador:\n"
                        + legend_for_prompt()
                    )

            # execução POR BLOCO: quando o pareamento determinístico
            # (PlannedExecutionMatcher) conseguiu casar com confiança, o
            # veredito por bloco já vem CALCULADO — a IA narra, não faz
            # conta. Só cai no texto cru de voltas (pra IA alinhar "por bom
            # senso") quando o pareamento ficou ambíguo demais (ou não há
            # Garmin) — comportamento de hoje, intacto.
            if context.block_comparison is not None:

                lines.append(
                    AIAnalysisWriter._block_comparison_fact(
                        context.block_comparison,
                        AIAnalysisWriter.aerobic_block_ceiling(context),
                    )
                )

            else:

                laps_fact = AIAnalysisWriter._executed_laps_fact(
                    (activity.raw or {}).get("_garmin_laps") or []
                )

                if laps_fact:

                    lines.append(laps_fact)

        else:

            lines.append("Planejado: (treino extra, sem sessão no plano)")

        if executed.indoor:

            lines.append(
                "Ambiente: ESTEIRA — distância/pace do relógio podem "
                "divergir do real; a referência de distância é a do plano."
            )

        elif activity.start_latitude is not None:

            # tem GPS = correu na RUA/parque. Sinal POSITIVO explícito pra a IA
            # NÃO assumir esteira a partir da prescrição (que pode mencionar
            # esteira como opção) — bug real do Renato (correu no parque e a
            # análise disse "vi que você rodou na esteira").
            lines.append(
                "Ambiente: AR LIVRE (rua/parque, treino COM GPS) — a "
                "distância e o pace do relógio são REAIS; NÃO é esteira."
            )

        lines.append(
            f"Executado: {activity.distance / 1000:.1f} km, "
            f"pace médio {PaceFormatter.format(executed.pace_min_km)} min/km, "
            f"tipo identificado {workout_type_label(executed.training_type)}, "
            f"intensidade {intensity_label(executed.intensity)}"
            + (
                f", FC média na zona {executed.estimated_zone}"
                if executed.estimated_zone
                else ""
            )
        )

        zone_facts = AIAnalysisWriter._hr_zone_facts(executed, runner)

        if zone_facts:

            lines.append(zone_facts)

        intent = AIAnalysisWriter._intent_facts(context)

        if intent:

            lines.append(intent)

        if activity.average_heartrate:

            hr = f"FC média {int(activity.average_heartrate)}"

            if activity.max_heartrate:

                hr += f", máx {int(activity.max_heartrate)}"

            lines.append(hr + " bpm")

        lines.append(
            AIAnalysisWriter._structure_facts(executed.structure)
        )

        # tudo que o Garmin mediu no relógio — deixa a leitura DE ACORDO com
        # o executado (efeito de treino, percepção do atleta, dinâmica de
        # corrida, potência, carga). Só aparece pra quem treina com Garmin.
        garmin = AIAnalysisWriter._garmin_facts(
            (activity.raw or {}).get("_garmin_metrics")
        )

        if garmin:

            lines.append(garmin)

        # CONTEXTO DO DIA (post-mortem): a condição do atleta quando fez o treino
        # — sono da noite anterior, prontidão, corpo/carga. Deixa a IA explicar
        # um treino abaixo do esperado pela CAUSA, não só constatar o resultado.
        from app.application.coach.context.day_context_reader import (
            DayContextReader,
        )

        day_context = DayContextReader.facts(
            runner.id, activity.start_date.date()
        )

        if day_context:

            lines.append(day_context)

        # o DOSSIÊ do atleta — meta/prova, capacidade, evolução, corpo,
        # PERCEPÇÃO, padrões, plano da semana, memória, o que já cobrou e o que
        # o coach já disse (bom dia, plano): a MESMA base do plano e do chat.
        # Sem isto a análise olhava o treino + um recorte e "esquecia" quem o
        # atleta é — ou contradizia o que o plano/bom dia decidiu. LEI:
        # [[feedback_base_historico_sempre]]. Best-effort (vazio se falhar).
        from app.application.coach.context.athlete_dossier import AthleteDossier

        dossier = AthleteDossier.render(runner.id, runner=runner)

        if dossier:

            lines.append(dossier)

        # o próximo treino do plano — pra o "próximo passo" dizer o que fazer
        # DIFERENTE nele, não uma frase genérica de recuperação
        next_line = AIAnalysisWriter._next_session_fact(context)

        if next_line:

            lines.append(next_line)

        return "\n".join(lines)

    @staticmethod
    def _intent_facts(context: CoachContext) -> str | None:
        """O que o treino PEDIA em termos de esforço + o teto aeróbico dele,
        pra a IA julgar se o leve foi leve (pela FC, não só pelo pace)."""

        from app.application.history.stimulus_ledger import (
            EASY,
            LONG,
            StimulusLedger,
        )
        from app.application.history.training_patterns import TrainingPatterns

        planned = context.planned

        if planned is None:

            return None

        family = StimulusLedger.classify(planned.workout_type)

        zones = getattr(context.executed, "hr_zones", None)

        ceiling = TrainingPatterns.ceiling_of(
            zones, getattr(context.runner, "id", None),
        )

        norm = StimulusLedger._normalize(planned.workout_type)

        long_quality = family == LONG and any(
            c in norm for c in ("progress", "misto", "bloco", "final", "ritmo")
        )

        if family == EASY:

            intent = "LEVE/aeróbico — a FC deveria ficar abaixo do teto aeróbico"

        elif family == LONG and not long_quality:

            intent = (
                "LONGÃO-BASE — a maior parte deveria ficar abaixo do teto "
                "aeróbico (um pouco de deriva no fim é normal)"
            )

        elif family == LONG:

            intent = (
                "LONGÃO COM QUALIDADE — a parte leve abaixo do teto aeróbico, "
                "a parte forte no alvo prescrito"
            )

        else:

            intent = f"QUALIDADE ({family}) — os blocos fortes no alvo prescrito"

        text = f"Intenção do treino: {intent}"

        if ceiling:

            text += f" (teto aeróbico dele ~{ceiling} bpm, 70% da reserva de FC)"

        # desacoplamento só vale em esforço CONSTANTE (leve/longão-base): num
        # progressivo o pace sobe de propósito e o número vira ruído — foi o
        # que fez a IA chamar de "redonda" uma parte leve com FC em 149-165
        decoupling = AIAnalysisWriter._decoupling(context.executed.structure)

        if decoupling is not None and (
            family == EASY or (family == LONG and not long_quality)
        ):

            text += (
                f". Desacoplamento FC×pace (1ª × 2ª metade): {decoupling:+.1f}% "
                "(até ~5% é normal; acima disso = deriva de fadiga/calor)"
            )

        return text + "."

    @staticmethod
    def _decoupling(structure: WorkoutStructure | None) -> float | None:
        """Pa:FC (Friel): quanto a eficiência (velocidade/FC) caiu da 1ª pra 2ª
        metade, em %. Só com 4+ km de splits com FC."""

        if structure is None or not structure.km_splits or not structure.km_hr:

            return None

        pairs = [
            (pace, hr)
            for pace, hr in zip(structure.km_splits, structure.km_hr)
            if pace and hr
        ]

        if len(pairs) < 4:

            return None

        half = len(pairs) // 2

        def efficiency(items):

            return sum(1 / (pace * hr) for pace, hr in items) / len(items)

        first, second = efficiency(pairs[:half]), efficiency(pairs[half:])

        return (first - second) / first * 100 if first else None

    @staticmethod
    def _next_session_fact(context: CoachContext) -> str | None:

        nxt = getattr(context, "next_planned", None)

        if nxt is None:

            return None

        when = getattr(context, "next_planned_date", None)

        day = f" ({when:%d/%m})" if when else ""

        size = (
            f" {nxt.planned_distance_km:.1f} km" if nxt.planned_distance_km
            else (
                f" {nxt.planned_duration_minutes} min"
                if nxt.planned_duration_minutes else ""
            )
        )

        from app.core.weekdays import weekday_label

        return (
            f"Próximo treino do plano: {weekday_label(nxt.day)}{day} — "
            f"{nxt.workout_type}{size}"
        )

    @staticmethod
    def _hr_zone_facts(executed, runner=None) -> str | None:
        """Régua de zonas do atleta + tempo em cada zona — a IA só fala de
        zona com ISTO (a mesma leitura do gráfico do app e do relógio). Se a
        régua mudou há pouco (FC de repouso/máx do atleta mudou), avisa — a
        IA pode citar como sinal de evolução (ou de alerta), com cuidado."""

        zones = getattr(executed, "hr_zones", None)

        shares = zone_share_label(
            getattr(executed.activity, "hr_zone_minutes", None)
        )

        if zones is None and not shares:

            return None

        parts = []

        if zones is not None:

            source = (
                "do relógio Garmin do atleta"
                if zones.method.startswith("garmin")
                else "calculadas pela FC máx/repouso do atleta"
            )

            parts.append(f"Zonas de FC ({source}): {zones.describe()} bpm")

        if shares:

            parts.append(f"tempo em cada zona neste treino: {shares}")

        text = (
            "; ".join(parts)
            + ". Ao citar zona de FC, use SÓ estes números (são os que o "
            "atleta vê no app e no relógio)."
        )

        change = HrZoneHistory.recent_change(
            getattr(runner, "hr_zones_history", None), today_local()
        )

        if change is not None:

            text += (
                " As zonas do atleta MUDARAM recentemente "
                f"({HrZoneHistory.describe_change(*change)}). FC de repouso "
                "caindo costuma indicar evolução aeróbica; subindo pode ser "
                "fadiga/estresse. Cite só se ajudar a entender este treino, "
                "sem alarde."
            )

        return text

    # sensação do atleta (directWorkoutFeel do Garmin, 0-100 em passos de 25) —
    # a mesma tabela que grava a percepção do relógio (PerceptionRecorder)
    _FEEL_WORDS = WATCH_FEEL_WORDS

    @staticmethod
    def aerobic_block_ceiling(context: CoachContext) -> int | None:
        """Teto aeróbico pra julgar os blocos CONTÍNUOS pela FC — só quando a
        sessão é leve ou longão (num treino de ritmo o bloco contínuo é forte
        de propósito). None = não julga FC de bloco."""

        from app.application.history.stimulus_ledger import (
            EASY,
            LONG,
            StimulusLedger,
        )
        from app.application.history.training_patterns import TrainingPatterns

        planned = context.planned

        zones = getattr(context.executed, "hr_zones", None)

        if planned is None or zones is None:

            return None

        if StimulusLedger.classify(planned.workout_type) not in (EASY, LONG):

            return None

        return TrainingPatterns.ceiling_of(
            zones, getattr(context.runner, "id", None),
        )

    @staticmethod
    def block_hr_verdict(block, aerobic_ceiling: int | None) -> str | None:
        """Veredito de FC do bloco contínuo (calculado por código): o ✅ de
        pace não diz se foi LEVE — 6:21 no alvo com FC 156 (teto 151) não foi.
        None quando não se aplica."""

        hr = getattr(block, "executed_hr", None)

        if not aerobic_ceiling or not hr or block.kind != "run":

            return None

        if hr > aerobic_ceiling + 2:

            return "above"

        return "ok" if hr <= aerobic_ceiling else None

    @staticmethod
    def _block_comparison_fact(comparison, aerobic_ceiling: int | None = None) -> str:
        """Comparação EXATA bloco-a-bloco (PlannedExecutionMatcher) — cada
        bloco já traz o veredito calculado por código; a IA só narra. Nos
        blocos contínuos de leve/longão vem TAMBÉM o veredito de FC."""

        parts = []

        for block in comparison.blocks:

            seg = f"{block.label}: "

            if block.executed_distance_m:

                seg += f"{block.executed_distance_m:.0f}m "

            minutes, seconds = divmod(int(block.executed_duration_sec), 60)

            seg += f"em {minutes}'{seconds:02d}"

            if block.executed_pace:

                seg += f" ({PaceFormatter.format(block.executed_pace)}/km)"

            # FC do BLOCO: sem isto a "parte leve" do longão era julgada só
            # pelo pace ("cravou 6:21") com a FC em 149-165 (Renato, 26/09)
            if getattr(block, "executed_hr", None):

                seg += f" FC {block.executed_hr}"

            if block.pace_min and block.pace_max:

                seg += f" — alvo {block.pace_min}-{block.pace_max}/km"

            elif block.planned_distance_m:

                seg += f" — alvo {block.planned_distance_m:.0f}m"

            elif block.planned_duration_sec:

                p_min, p_sec = divmod(int(block.planned_duration_sec), 60)

                seg += f" — alvo {p_min}'{p_sec:02d}"

            if block.within_target is True:

                seg += " [pace dentro do alvo]"

            elif block.within_target is False:

                seg += " [pace fora do alvo]"

            hr_verdict = AIAnalysisWriter.block_hr_verdict(block, aerobic_ceiling)

            if hr_verdict == "above":

                seg += (
                    f" [FC ACIMA do teto aeróbico ({block.executed_hr} > "
                    f"{aerobic_ceiling}) — NÃO foi leve pela FC]"
                )

            elif hr_verdict == "ok":

                seg += " [FC no aeróbico — leve de verdade]"

            parts.append(seg)

        text = (
            "Execução por bloco (comparação EXATA, já calculada): "
            + "; ".join(parts)
        )

        if comparison.missing:

            text += f". Não completou: {', '.join(comparison.missing)}"

        return text

    @staticmethod
    def _executed_laps_fact(laps: list[dict]) -> str:
        """Formata as voltas EXECUTADAS (duração + distância + pace + FC) pra
        IA alinhar com a prescrição. A prescrição vem em tempo (3'/2'), então
        a duração de cada volta é a chave do casamento."""

        parts = []

        for lap in laps:

            dur = lap.get("duration_s") or 0

            dist = lap.get("distance_m") or 0

            # descarta volta-fantasma (relógio reiniciando / lap acidental):
            # um bloco real de corrida tem pelo menos ~30 m (caso do Renato:
            # laps de 5 m e 13 m quando o relógio quebrou e reiniciou)
            if not dur or dist < _MIN_LAP_M:

                continue

            minutes, seconds = divmod(int(dur), 60)

            seg = f"{minutes}'{seconds:02d} {dist}m"

            if lap.get("pace"):

                seg += f" {PaceFormatter.format(lap['pace'])}/km"

            if lap.get("avg_hr"):

                seg += f" FC{lap['avg_hr']}"

            parts.append(seg)

        if not parts:

            return ""

        return (
            "Execução por bloco (voltas do relógio, compare com a prescrição "
            "acima): " + "; ".join(parts)
        )

    @staticmethod
    def _clean_msg(msg) -> str | None:
        """Enum do Garmin ('OVERREACHING_14') -> texto legível
        ('overreaching') — tira o código no fim e troca '_' por espaço."""

        if not msg:

            return None

        text = re.sub(r"_\d+$", "", str(msg)).replace("_", " ").lower().strip()

        return text or None

    @staticmethod
    def _garmin_facts(metrics: dict | None) -> str | None:
        """Formata TODO o bundle rico do Garmin que faz sentido pra análise —
        só os campos presentes (cada treino/relógio traz um subconjunto)."""

        if not metrics:

            return None

        parts = []

        # --- efeito de treino (o estímulo que o treino gerou) ---
        te = metrics.get("training_effect")

        if te is not None:

            detail = " / ".join(
                x for x in (
                    metrics.get("training_effect_label"),
                    AIAnalysisWriter._clean_msg(metrics.get("aerobic_effect_msg")),
                ) if x
            )

            parts.append(
                f"efeito aeróbico {te}/5" + (f" ({detail})" if detail else "")
            )

        ana = metrics.get("anaerobic_effect")

        if ana is not None:

            msg = AIAnalysisWriter._clean_msg(metrics.get("anaerobic_effect_msg"))

            parts.append(
                f"efeito anaeróbico {ana}/5" + (f" ({msg})" if msg else "")
            )

        # --- percepção do atleta ---
        if metrics.get("workout_rpe"):

            parts.append(
                f"esforço percebido (RPE) {round(metrics['workout_rpe'] / 10)}/10"
            )

        feel = metrics.get("workout_feel")

        if feel is not None:

            word = AIAnalysisWriter._FEEL_WORDS.get(round(feel / 25) * 25)

            parts.append(f"sensação do atleta: {word or feel}")

        # --- pace ajustado ao relevo (esforço real em subida/descida) ---
        gap = metrics.get("grade_adjusted_speed")

        if gap:

            parts.append(
                f"pace ajustado ao relevo "
                f"{PaceFormatter.format((1000 / gap) / 60)} min/km"
            )

        # --- dinâmica de corrida (forma) ---
        dynamics = []

        if metrics.get("ground_contact_ms"):

            dynamics.append(
                f"contato com o solo {round(metrics['ground_contact_ms'])} ms"
            )

        if metrics.get("stride_length_cm"):

            dynamics.append(f"passada {round(metrics['stride_length_cm'])} cm")

        if metrics.get("vertical_oscillation_cm"):

            dynamics.append(
                f"oscilação vertical {metrics['vertical_oscillation_cm']:.1f} cm"
            )

        if metrics.get("vertical_ratio"):

            dynamics.append(f"razão vertical {metrics['vertical_ratio']:.1f}%")

        if dynamics:

            parts.append("dinâmica de corrida: " + ", ".join(dynamics))

        # --- potência ---
        if metrics.get("avg_power"):

            extras = []

            if metrics.get("normalized_power"):

                extras.append(f"normalizada {round(metrics['normalized_power'])} W")

            if metrics.get("max_power"):

                extras.append(f"máx {round(metrics['max_power'])} W")

            parts.append(
                f"potência média {round(metrics['avg_power'])} W"
                + (f" ({', '.join(extras)})" if extras else "")
            )

        # --- carga / gasto ---
        if metrics.get("body_battery_delta") is not None:

            parts.append(f"body battery {metrics['body_battery_delta']:+d}")

        intensity = []

        if metrics.get("vigorous_minutes"):

            intensity.append(f"{metrics['vigorous_minutes']} vigorosos")

        if metrics.get("moderate_minutes"):

            intensity.append(f"{metrics['moderate_minutes']} moderados")

        if intensity:

            parts.append("minutos de intensidade: " + " + ".join(intensity))

        if metrics.get("calories"):

            parts.append(f"{round(metrics['calories'])} kcal")

        # --- ambiente ---
        temp = metrics.get("avg_temperature")

        if temp is not None:

            line = f"temperatura ~{round(temp)}°C"

            if metrics.get("max_temperature"):

                line += f" (máx {round(metrics['max_temperature'])}°C)"

            parts.append(line)

        if not parts:

            return None

        return (
            "Dados do Garmin (medidos no relógio, de acordo com o "
            "executado): " + "; ".join(parts)
        )

    @staticmethod
    def _structure_facts(
        structure: WorkoutStructure | None,
    ) -> str:

        if structure is None or (
            not structure.has_detail and structure.interval is None
        ):

            return "Estrutura: sem splits (esteira ou atividade resumida)"

        # intervalado detectado no stream: descreve os tiros e a FC (é o
        # que revela se o atleta respeitou o treino de tiro)
        if structure.interval is not None:

            interval = structure.interval

            reps = "; ".join(
                f"tiro {i + 1}: {rep['distance_m']}m a "
                f"{PaceFormatter.format(rep['pace'])}"
                + (f" (pico {rep['peak_hr']}bpm)" if rep.get("peak_hr") else "")
                for i, rep in enumerate(interval.reps)
            )

            hr = ""

            if interval.avg_peak_hr:

                hr = (
                    f"; FC pico média {interval.avg_peak_hr}bpm"
                    + (
                        f", recuperação {interval.avg_recovery_hr}bpm"
                        if interval.avg_recovery_hr
                        else ""
                    )
                )

            cadence = (
                f"; cadência {structure.cadence_spm} ppm"
                if structure.cadence_spm
                else ""
            )

            return (
                f"Estrutura: INTERVALADO com {interval.rep_count} tiros "
                f"(pace médio {PaceFormatter.format(interval.avg_rep_pace)}"
                f"/km){hr}{cadence}. Reps — {reps}"
            )

        parts = []

        if structure.km_splits:

            # pace + FC por km: sem a FC a IA já "viu" fadiga em treino
            # onde a FC CAIU na segunda metade (pace estável + FC caindo
            # = eficiência, não cansaço)
            hr_by_km = structure.km_hr or []

            splits = ", ".join(
                f"km{i + 1} {PaceFormatter.format(pace)}"
                + (
                    f" ({hr_by_km[i]}bpm)"
                    if i < len(hr_by_km) and hr_by_km[i]
                    else ""
                )
                for i, pace in enumerate(structure.km_splits)
            )

            parts.append(f"splits: {splits}")

        parts.append(
            "intervalado (tiros alternados)"
            if structure.is_interval
            else "ritmo sem tiros"
        )

        parts.append(
            f"progressão: {TREND_LABELS.get(structure.split_trend)}"
        )

        if structure.cadence_spm:

            parts.append(f"cadência {structure.cadence_spm} ppm")

        return "Estrutura: " + "; ".join(parts)
