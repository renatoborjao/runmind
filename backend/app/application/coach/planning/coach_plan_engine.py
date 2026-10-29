import json
from datetime import date

from google.genai import types

from app.application.coach.planning.workout_menu import (
    STEPS_RULE,
    TIME_OR_DISTANCE_RULE,
    WORKOUT_MENU,
)
from app.application.coach.writer.analysis_hygiene import plan_lines, plan_text
from app.core.config import get_settings
from app.core.weekdays import WEEKDAYS
from app.domain.entities.planned_session import PlannedSession
from app.domain.entities.training_plan import TrainingPlan
from app.domain.entities.workout_step import parse_steps, total_distance_km
from app.infrastructure.integrations.gemini.client import (
    generate_json,
    repair_json,
)

# Pro pensa (thinking) e isso conta no orçamento de saída + é cobrado como
# output. Damos um teto de thinking EXPLÍCITO (não dinâmico, que gastaria ~8k)
# e um max_output com folga pra caber thinking + o JSON do plano — senão o
# thinking come o orçamento e volta vazio (bug conhecido).
THINKING_BUDGET = 1024

# Folga generosa: o JSON do plano (3-5 sessões com steps aninhados) + o
# thinking do Pro precisam caber sem CORTE — JSON cortado é a principal
# causa de quebra e do retry PAGO. Só paga o que gera, não o teto; então a
# folga é de graça e derruba os retries.
MAX_OUTPUT_TOKENS = 6000

VALID_DAYS = set(WEEKDAYS.values())

# só planejamos corrida/caminhada; musculação, descanso, bike etc. NÃO são
# nossos — o atleta cuida disso. Se a IA devolver, a gente descarta.
RUNNING_KINDS = {"run", "walk", "run_walk"}

PROMPT_TEMPLATE = """Você é um treinador de corrida experiente montando o plano \
da PRÓXIMA SEMANA para um atleta específico. O plano tem que ser REAL e VIVO:
segue a evolução, os limites e a rotina que já funcionam para ELE — nada de
fórmula genérica nem de inflar volume.

RETRATO REAL DO ATLETA (dados do histórico dele — use só isto, não invente):
{context}

REGRAS:
- O plano é SÓ de corrida/caminhada. NÃO prescreva musculação, descanso, bike
  ou qualquer outra atividade — isso não é seu (o atleta cuida por conta).
  Apenas as sessões de corrida/caminhada nos dias de corrida dele.
- Respeite os DIAS e a FREQUÊNCIA de corrida dele: agende as sessões NOS DIAS
  que o retrato lista e mantenha a MESMA quantidade (se ele treina N dias, o
  plano tem N sessões nesses mesmos dias). NÃO adicione dias pra "encher", não
  invente outros dias nem tire sessões. Só mude o DIA de uma sessão quando a
  memória/preferência dele pedir (ex.: longão no domingo) ou quando o padrão de
  furos mostrar que um dia fixo não acontece — nunca por conta própria. Isto
  vale INCLUSIVE em semana de descarga: alivia volume/intensidade, mantém os
  dias.
- TREINE RUMO À META — não faça manutenção. O plano deve EVOLUIR o atleta em
  direção ao objetivo, não sentar no volume/ritmo médio atual dele. Quando ele
  vem consistente, PUXE: suba o volume (passo-padrão ~+10%; até ~15% quando o
  corpo está verde e o dossiê mostra ESPAÇO PRA PUXAR), ancorado no que o
  atleta REALMENTE correu nas semanas fechadas (se correu acima do plano, o
  plano é que ficou baixo) E/OU aprofunde a
  qualidade em TODOS os tipos de treino, não só no longão — o forte chega mais
  perto do ritmo-alvo ou ganha série maior, o moderado alonga, o longão ganha
  km OU qualidade, e o leve segue leve DE VERDADE (a qualidade dele é a FC
  baixa, as acelerações, a cadência) — exemplos, não receita: a sabedoria é
  sua — sempre construindo o que a META do atleta exige. Conservador demais é desperdiçar a
  janela em que o atleta evolui: se o corpo aguenta, a semana pede MAIS que a
  anterior.
- ROTA ATÉ A META e PEDIDO DO ATLETA: se o dossiê trouxer "ROTA ATÉ A META", ela é
  a conta do que a prova exige × onde o plano atual o leva — feche a DIFERENÇA nas
  semanas que restam, com o primeiro degrau JÁ nesta semana, ou diga ao atleta que
  não cabe e proponha ajustar a meta; semana igual à anterior sem dizer por quê é
  erro. Se trouxer "ELE PEDE MAIS", o que ele diz de si é DADO: com os números
  confirmando (esforço baixo, corpo firme) a resposta é DOSE — longão com mais km,
  mais tempo em qualidade de verdade, não só um dia a mais — dita a ele no objetivo
  e no propósito da semana; sem confirmar, diga o porquê com o dado. O leve segue
  definido pela FC (teto aeróbico): se o dossiê mostrar o pace em que ele faz o
  leve de verdade, use ESSA faixa e não a do modelo.
- SEMANAS ANTERIORES e ROTA SEMANA A SEMANA: o dossiê traz o que você prescreveu × o
  que ELE fez em cada semana e a rota semana a semana (volume, longão, dose de
  qualidade, km no ritmo da prova, foco sugerido). A semana nasce do que ele FEZ,
  nunca do papel: sessão que ele não cumpriu não foi dose absorvida (refaça ou
  ajuste o degrau em vez de somar por cima como se tivesse feito), e o que ele fez
  além do papel é carga que o corpo já pagou. A rota SOBE enquanto ele cumpre: o
  volume desta semana fica dentro de ±20% do dela SEM precisar justificar; fora
  disso escreva o MOTIVO em "route_note" (1 frase, com os números dele: corpo,
  doença, viagem, prova, o que ele não cumpriu) — o mesmo vale pro LONGÃO: ficar
  abaixo do maior recente dele ou do da rota pede o motivo. Repetir o mesmo estímulo com a
  mesma dose semana após semana é ESTAGNAR: o foco sugerido gira de propósito
  (limiar → VO2 → subidas/força → ritmo de prova) e o longão muda de forma — troque
  com razão (lacuna, corpo, preferência dele), mas faça a dose, o ritmo e a distância
  EVOLUÍREM juntos. A decisão é sua; a rota é guia, não trilho.
- FORTE ENTREGUE: o dossiê traz "FORTES: PRESCRITO × ENTREGUE" — se ele vem
  FAZENDO os fortes mas NÃO bate o ritmo-alvo (blocos mais lentos, esforço
  percebido ≤3/10), mais um forte igual não evolui ninguém: trate a CAUSA (alvo
  acima do que ele sustenta → recalibre pelo que ele fez; ele não empurra → dê a
  régua que ele entende e diga o que você viu) e escreva no propósito o que muda
  pra ele entregar. Prescrever e contar como feito não é estímulo.
- ESCADA DO ESTÍMULO e FUNÇÃO DE CADA SESSÃO (conhecimento, não regra — a decisão é
  sua): o dossiê traz a "ÚLTIMA DOSE DE CADA ESTÍMULO". Treinador de verdade costuma
  fazer o MESMO estímulo subir em degrau mensurável (uma repetição a mais, bloco
  maior, pace mais perto do alvo, pausa menor) antes de trocá-lo: trocar de estímulo
  toda semana é variar sem evoluir. Mas você decide o que a evolução × a meta × o
  objetivo dele pedem nesta semana — avançar a dose, repetir (e dizer por quê),
  trocar (lacuna, fase, corpo, preferência dele) ou recuar. No propósito de cada
  sessão diga o que mudou em relação à última dose do mesmo tipo, ou por que não
  mudou. Toda sessão tem uma FUNÇÃO (recuperação, volume aeróbico, técnica/cadência/
  acelerações, estímulo forte, especificidade da prova): leve que só soma km, sem
  função, é desperdício — mas o leve que ele precisa pra absorver o forte tem valor,
  e vale dizer qual é a função dele. O longão evolui pela fase (base: km; específica:
  etapas e ritmo de prova; descarga: recua). Nada disso é cota nem fórmula.
- MAS COM CRITÉRIO: o teto é o SALTO, não o passo — nada de semana +25% sobre a
  anterior nem de longão muito acima do maior recente (é onde corredor amador
  se machuca, e o HRV não avisa). Respeite a capacidade real e a aderência — se
  ele vem cumprindo pouco, segure ou recue (ver PERIODIZAÇÃO abaixo). Nunca
  prescreva estímulo que o nível dele ainda não comporta.
- DOSE À ALTURA DA CAPACIDADE, não da cautela genérica: antes de aliviar por um
  sinal de recuperação, pese o QUADRO INTEIRO (STATUS DO CORPO + APRENDIZADOS).
  Um limitador CRÔNICO/baseline que os aprendizados mostram que ele SUSTENTA
  (ex.: "sono cronicamente curto mesmo com o corpo equilibrado") NÃO é motivo pra
  encolher a dose semana após semana — senão o atleta fica ETERNAMENTE
  subtreinado; trate-o como o normal dele. Se o status do corpo diz que a CARGA
  está tranquila, a leitura é "TEM ESPAÇO pra progredir", não "alivia". Só recue
  de verdade por sinal AGUDO: sobrecarga real (STRAINED), recuperação em queda
  clara AGORA, dor/lesão/doença, ou pedido do atleta.
- ORÇAMENTO DE TEMPO É ALVO, não teto a evitar: se o atleta tem um limite de
  duração por dia (ex.: "treinos de semana em até 50-55 min"), MIRE PERTO dele
  nos dias de QUALIDADE — encha o tempo disponível com trabalho produtivo (bloco
  principal do tamanho que a meta pede), NÃO entregue um treino 15-20 min ABAIXO
  do que ele tem de folga (ex.: 15 min de limiar num dia que comporta 50). O
  limite é teto de segurança, não a meta — respeite-o, mas USE o espaço.
- PERIODIZAÇÃO — a decisão é SUA, de treinador, ancorada na PROVA real (está no
  retrato como "Prova-âncora", com distância e semanas até ela). NÃO existe
  regra fixa de calendário; você raciocina:
    * COM prova: o polimento/afiação é PROPORCIONAL à DISTÂNCIA. Prova CURTA
      (5k/10k) pede afiação CURTA — tipicamente só a ÚLTIMA semana; então a ~2
      semanas de um 10k você AINDA constrói/mantém volume e qualidade, NÃO corta
      cedo. Meia/maratona pedem polimento mais LONGO (~2-3 semanas). Longe da
      prova, construa base/volume; só poupe de verdade na véspera.
    * ENSAIO DA PROVA (simulado/prova-teste) — NÃO ESQUEÇA: no bloco antes da
      prova (tipicamente ~10-14 dias antes num 5k/10k, ~2-3 semanas numa meia/
      maratona), encaixe UM simulado — bloco CONTÍNUO no RITMO-ALVO cobrindo um
      pedação grande da distância (ver o cardápio) — pra o atleta chegar sabendo
      se sustenta o pace, e não ir "no escuro". É distinto dos tiros no ritmo-
      alvo (que continuam valendo pra construir). Só quando a semana da vez cai
      nessa janela e o nível já comporta; NÃO repita toda semana, é um ensaio.
      Deixe dias leves em volta pra ele chegar recuperado no simulado e na prova.
    * SEM prova (objetivo de fundo sem data): progrida SEMANA A SEMANA rumo ao
      objetivo, sem reduzir volume à toa. Só recue por motivo REAL — lesão/dor,
      pedido do atleta, ou sobrecarga clara (recuperação pontual). Nada de
      "semana leve" sem razão.
- 1º plano (sem aderência registrada): comece perto do volume atual, MAS já com
  leve inclinação de evolução e a ESTRUTURA que a meta pede (ex.: se a meta é
  de tempo, inclua um treino no ritmo-alvo). O atleta veio pra MELHORAR, não
  pra manter.
- VÁRIOS OBJETIVOS: a meta do atleta pode reunir MAIS DE UM objetivo (ex.:
  saúde + emagrecer + uma marca de tempo). Leia a meta inteira e CONTEMPLE
  TODOS eles, equilibrando: se além da performance ele quer saúde/bem-estar/
  constância, não vire só máquina de prova — cuide da sustentabilidade e do
  prazer de correr. Se NÃO houver alvo de performance (só saúde/evolução
  geral), priorize regularidade e progressão gentil, sem puxar ritmo agressivo.
- {time_rule}
- Cada corrida com um PROPÓSITO distinto. Você é o treinador e decide tudo —
  com o critério de quem entende de fisiologia, não com regra fixa:
  * PACE: a META dá a DIREÇÃO; o degrau de hoje sai da CAPACIDADE ATUAL (os
    paces reais do retrato: fácil / limiar / VO2). Bloco longo bem acima do
    limiar de hoje, ou tiro médio acima do VO2 de hoje, costuma não sair — o
    atleta corta ou sobrevive sem o estímulo certo (confira nos PADRÕES se isso
    já aconteceu com ele). Se decidir puxar acima, que seja deliberado e dito
    no propósito. A faixa do leve e do aquecimento é a "fácil" das "Paces reais"
    DESTA semana — ela pode ter mudado (o leve dele é medido pela FC): não copie
    a faixa do plano anterior.
  * DISTRIBUIÇÃO DE INTENSIDADE: evolução sustentável vem de muito volume leve
    DE VERDADE (pela FC, abaixo do teto aeróbico dele — escreva hr_max nos
    passos dos leves quando souber o teto) e poucas sessões fortes bem feitas.
    Um longão com blocos/progressão também é sessão forte. Quantas fortes cabem
    na semana é decisão sua: pese frequência, corpo, fase, meta e o que ele vem
    absorvendo — semana com forte demais + leve saindo forte vira fadiga
    crônica, não evolução.
- EVOLUÇÃO É O CRITÉRIO DE ESCOLHA — escolha LIVRE, de treinador. Antes de
  montar, responda pra você: "o que ESTA semana acrescenta de novo à evolução
  dele rumo à meta, em relação às últimas?" Se a resposta for "nada", a semana
  está errada. Vale pra semana INTEIRA, não só pro dia forte: o leve pode ser
  rodagem com acelerações, steady, cadência, fartlek solto; o longão pode ser
  constante, por tempo, progressivo, com final rápido ou com blocos no
  ritmo-alvo; o forte pode ser qualquer um do repertório. Quando o corpo pede
  SEGURAR, a novidade vem da FORMA (outro estímulo na mesma dose), não da
  carga. Repertório (ponto de partida, não lista fechada):
{menu}
  Longe da prova / construindo base -> volume, longão, limiar; perto da prova
  -> afiar no ritmo-alvo e ensaiar (simulado). Diga no "weekly_objective" o
  que a semana acrescenta.
- PERIODIZAÇÃO EM BLOCOS — como treinador de verdade, você pensa em BLOCOS
  (3 a 6 semanas) com começo, meio e fim, não semana solta. O contexto diz se
  há BLOCO EM ANDAMENTO (e o papel desta semana nele) ou se esta semana ABRE
  um bloco. Ao ABRIR: defina "block" — o FOCO do bloco rumo à meta/prova e o
  PAPEL de cada semana (ex.: construir, construir, puxar mais, consolidar/
  testar — alívio só se o corpo pedir, nunca por calendário; a forma e a dose
  são suas). NUNCA escreva em "weeks_plan" uma semana de descarga, alívio,
  recuperação ou "semana leve" — nem a última do bloco: o bloco só diz
  construir, puxar, consolidar ou testar. O recuo de volume só existe em DOIS
  casos: o CORPO pede (sinal de descarga do dossiê) ou o atleta NÃO vem
  aderindo (aí o plano se ancora no que ele cumpre — veja SEMANAS ANTERIORES).
  Em andamento: monte a semana cumprindo o papel dela e devolva "block": null. Se
  o corpo/vida pedir desvio (doença, sobrecarga, prova nova), desvie e
  REDEFINA o bloco em "block" — o novo começa ESTA semana.
- SEMANA DE DESCARGA (mais leve de propósito): só quando o CORPO pede — o
  "sinal de descarga" do dossiê (recuperação caindo com a carga em alta, corpo
  sobrecarregado, forma recuando), ou a reta final da prova (aí é o polimento).
  Quando ele NÃO vem aderindo, o volume desce ao que ele cumpre — isso não é
  descarga, é ancorar no real. O TAMANHO da descarga é proporcional ao sinal e à
  ADAPTAÇÃO DELE (o dossiê mostra): sinal curto + atleta que cumpre e se recupera
  rápido = segurar a rampa ou recuo leve; recuo fundo seguido de volta ao volume
  cheio é dente de serra.
  Descarga NÃO é calendário: semanas seguidas subindo, bloco que carrega ou
  "já faz um tempo" não são motivo. Atleta que cumpre o plano e recupera bem
  segue EVOLUINDO — aliviar nele só destreina. O papel que o bloco deu a uma
  semana foi escrito semanas antes, sem saber como o atleta chegaria: se o
  papel desta semana é de descarga mas o dossiê não traz o sinal, NÃO descarregue
  (semana leve sobre semana já leve só destreina): siga a progressão (puxe, se
  há ESPAÇO PRA PUXAR) e REDEFINA "block". Ao descarregar, marque
  "is_deload": true e escreva
  "deload_why": 1-2 frases em português simples, COM OS NÚMEROS DELE (os km das
  últimas semanas, o que ele fez), dizendo por que ESTA semana é mais leve e o
  que ela prepara — sem jargão (nada de ACWR/carga aguda). O "weekly_objective"
  e o rótulo do bloco têm que dizer a MESMA coisa que a semana é (descarga não
  pode vir com objetivo de "construir"). Semana normal: "is_deload": false e
  "deload_why": null.
- LINGUAGEM DO PLANO: o atleta LÊ cada frase. (1) Pace em palavras claras: \
"mais rápido que 6:45" / "mais lento que 7:15" — nunca "o pace cair abaixo de \
X" ou "subir acima de X" (pace menor = mais rápido: a frase fica ambígua). \
(2) Fale do TREINO, nunca de um estado interno que ele não contou: em vez de \
"segure a empolgação/ansiedade", "segure o ritmo na faixa X". (3) Sem as \
muletas "crave/cravar a faixa" e "foco absoluto": diga o que fazer, com o \
número. (4) Sem jargão de carga (ACWR, carga aguda): km e semanas dele.
- MAIS UM DIA DE TREINO? A frequência é escolha DELE: NUNCA adicione dia ao
  plano. Mas, pensando na EVOLUÇÃO rumo à meta, se um dia a mais faria
  diferença real (a meta pede mais volume do que os dias dele comportam, ele
  vem cumprindo bem, o corpo está absorvendo) e ele não recusou isso há pouco
  (veja o que você já disse), PROPONHA em "suggest_extra_day": UMA frase — qual
  dia livre, que treino (curto/leve costuma bastar) e por quê. Senão, null.
  Com o corpo em alerta ou aderência baixa, não é hora: null.
- LONGÃO só quando faz sentido: um "longão" é o treino MAIS LONGO da semana E
  claramente ACIMA da rodagem típica dele. Se o atleta ainda corre pouco (ex.:
  rodagem típica/maior treino ~5 km), NÃO rotule nenhuma corrida de "Longão" —
  chame de rodagem/base. O longão só aparece quando o volume evolui e existe
  uma corrida realmente mais longa. NUNCA dê o nome "Longão" a uma distância
  igual (ou menor) à rodagem comum do atleta.
- NUTRIÇÃO NO TREINO LONGO (gel, carboidrato, isotônico): o sistema anexa SOZINHO
  a cada sessão longa o horário certo de repor (por duração). NÃO escreva
  horários, doses ou marcas de gel/carboidrato em dicas, estrutura ou propósito —
  senão o atleta lê duas orientações diferentes.
- NÃO recomende nem cite marcas/modelos de TÊNIS em lugar nenhum (structure,
  dica, purpose). O app tem um recomendador PRÓPRIO de calçado (sabe km de cada
  par, rodízio e desgaste) que anexa a sugestão de tênis em cada treino — se
  você sugerir um par, briga com ele, repete o mesmo modelo e confunde o atleta.
  Fale do TREINO (ritmo, blocos, foco), nunca do calçado.
- SEMPRE traga o RITMO em NÚMERO nos passos que têm alvo (ex.: "6x 800m a
  4:45-4:50/km", "rodagem 50 min a 6:20-6:45/km") — nada de "ritmo forte" solto
  sem o pace. O atleta precisa do número pra executar.
- "structure" é uma LISTA de passos CLAROS e COMPLETOS, em linguagem simples
  que qualquer corredor entende. Detalhe de verdade: aquecimento (distância +
  pace), a parte principal (séries/distâncias/repetições/pace/recuperação
  EXPLÍCITOS), o desaquecimento e uma dica prática. Um passo por item.
- {steps_rule}
  Monte o treino que fizer sentido pra evolução dele.
- Respeite lesões/limitações que aparecerem no retrato.
- AVERSÕES A TIPO DE TREINO: se o retrato disser que o atleta não gosta de um
  tipo de treino, NÃO ignore — mas também NÃO jogue fora o estímulo que ele
  precisa pra meta. Distinga o motivo:
    * Gosto/tédio (ex.: "acha tiro na pista chato") -> MANTENHA o estímulo
      fisiológico e troque só a FORMA (ex.: fartlek na rua no lugar de
      intervalado na pista; progressivo no lugar de tempo em ritmo fixo).
    * Restrição física/dor (ex.: "subida incomoda o joelho") -> ADAPTE ou
      REMOVA de verdade aquele estímulo e compense com outro seguro.
  Explique a troca no "purpose" da sessão, pra ele ver que você ouviu e por
  que o objetivo foi mantido.

Responda APENAS com JSON (o exemplo abaixo é só de FORMATO — NÃO é template pra
copiar o tipo "Velocidade" toda semana; escolha os tipos pela fase/meta/variedade):
{{"weekly_objective": "objetivo/foco curto da semana",
  "phase": "BUILD",
  "is_deload": false | true,
  "deload_why": null | "por que esta semana é mais leve, com os números dele",
  "route_note": null | "se saiu de ±20% da rota ou o longão ficou abaixo: o motivo, com números",
  "block": null | {{"weeks": 4, "focus": "foco do bloco rumo à meta",
            "weeks_plan": ["sem 1: ...", "sem 2: ...", "sem 3: ...", "sem 4: ..."]}},
  "suggest_extra_day": null | "proposta curta de UM dia a mais (qual, o quê, por quê)",
  "sessions": [
    {{"day": "Tuesday", "kind": "run", "workout_type": "Velocidade",
      "distance_km": 9.0, "pace_min": "4:45", "pace_max": "4:50",
      "structure": [
        "Aquecimento: 2 km bem leve (6:30-7:00/km) + 3 educativos curtos",
        "Série: 6x 800m no pace 4:45-4:50/km",
        "Recuperação: 400m de trote leve entre cada tiro",
        "Desaquecimento: 1,5 km leve soltando as pernas",
        "Dica: comece o 1º tiro mais controlado pra não estourar no fim"
      ],
      "steps": [
        {{"kind": "warmup", "distance_km": 2, "pace_min": "6:30", "pace_max": "7:00"}},
        {{"kind": "repeat", "reps": 6, "steps": [
          {{"kind": "interval", "distance_m": 800, "pace_min": "4:45", "pace_max": "4:50"}},
          {{"kind": "recovery", "distance_m": 400}}
        ]}},
        {{"kind": "cooldown", "distance_km": 1.5, "pace_min": "6:30", "pace_max": "7:00"}}
      ],
      "purpose": "aumentar o ritmo de prova"}}
  ]}}

"phase" é a SUA decisão de periodização desta semana (ver PERIODIZAÇÃO):
"BASE" (construir, longe da prova), "BUILD" (qualidade/progressão — padrão e o
caso SEM prova), "PEAK" (afiação perto da prova), "TAPER" (poupar na semana da
prova). Coerente com as sessões que você montou — não marque TAPER e mande um
volumão, nem BUILD e corte tudo.

Cada sessão é uma corrida/caminhada com distance_km, paces, structure (texto),
steps (estruturado) e purpose. kind: "run" (corrida) ou "walk"/"run_walk"
(caminhada/corrida-caminhada, iniciante). Dias em inglês (Monday..Sunday).
Sessão POR TEMPO: troque "distance_km": 8.0 por "duration_min": 50 (a sessão
fica sem km) e use "duration_min" nos steps.
"""


class CoachPlanEngine:
    """IA-treinadora: gera o plano da semana a partir do retrato real do
    atleta. Se falhar, o chamador cai no motor determinístico (fallback)."""

    @staticmethod
    async def generate(
        runner_name: str,
        objective: str,
        week_start: date,
        context: str,
        model: str | None = None,
        thinking_budget: int | None = None,
    ) -> TrainingPlan:

        settings = get_settings()

        prompt = PROMPT_TEMPLATE.format(
            context=context,
            menu=WORKOUT_MENU,
            time_rule=TIME_OR_DISTANCE_RULE,
            steps_rule=STEPS_RULE,
        )

        # modelo/thinking podem ser sobrepostos pelo chamador (ex.: modelo PRO
        # só no plano, atrás de flag) — default é o coach model (Flash) atual.
        model = model or settings.gemini_coach_model

        budget = THINKING_BUDGET if thinking_budget is None else thinking_budget

        # generate_json re-gera se o JSON do plano vier torto (blindagem) —
        # o plano é core; não pode cair no determinístico por escorregada do
        # modelo. Só cai no fallback (AIPlanService) se TODAS as tentativas
        # falharem, aí levanta pra ele.
        plan = await generate_json(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=MAX_OUTPUT_TOKENS,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=budget,
                ),
            ),
            parse=lambda raw: CoachPlanEngine._parse_plan(
                raw, runner_name, objective, week_start,
            ),
        )

        if plan is None:

            raise ValueError("plano da IA inválido após as tentativas")

        return plan

    @staticmethod
    def _parse_plan(
        raw: str,
        runner_name: str,
        objective: str,
        week_start: date,
    ) -> TrainingPlan | None:
        """Wrapper de _to_plan pra o generate_json: devolve None em qualquer
        problema (JSON torto, sem corridas) em vez de levantar, pra re-gerar."""

        try:

            return CoachPlanEngine._to_plan(
                raw, runner_name, objective, week_start,
            )

        except (ValueError, json.JSONDecodeError, TypeError):

            return None

    @staticmethod
    def _to_plan(
        raw: str,
        runner_name: str,
        objective: str,
        week_start: date,
    ) -> TrainingPlan:

        try:

            data = json.loads(repair_json(raw))

        except (json.JSONDecodeError, TypeError) as e:

            raise ValueError(f"JSON do plano inválido: {e}")

        if not isinstance(data, dict):

            raise ValueError("plano da IA não é um objeto")

        sessions = CoachPlanEngine._parse_sessions(
            data.get("sessions", []),
        )

        if not any(s.kind == "run" for s in sessions):

            raise ValueError("plano da IA sem corridas")

        running_days = [s.day for s in sessions if s.kind == "run"]

        # volume com o km EFETIVO (distância, ou estimativa de tempo quando o
        # AIPlanService a preenche depois) — conta todos os tipos.
        weekly_volume = round(
            sum(s.effective_distance_km or 0 for s in sessions),
            1,
        )

        # a periodização é decisão do COACH (não de um engine rígido): usamos a
        # fase que ELE marcou; "IA" (não marcou) sinaliza pro chamador cair no
        # PhaseEngine como fallback. Ver [[feedback_tudo_dinamico]].
        phase = str(data.get("phase", "")).strip().upper()

        if phase not in {"BASE", "BUILD", "PEAK", "TAPER"}:

            phase = "IA"

        return TrainingPlan(
            athlete_name=runner_name,
            objective=objective,
            phase=phase,
            weekly_volume=weekly_volume,
            running_days=running_days,
            week_start=week_start,
            sessions=sessions,
            # o texto que o atleta lê passa pela higiene (sem muletas, sem estado
            # interno inventado, sem jargão de carga) — a auditoria dos planos de
            # 18/10 achou "crave a faixa", "segure a empolgação", "ACWR 1.7" em 6/6
            weekly_objective=plan_text(str(data.get("weekly_objective", "")).strip()),
            is_deload=data.get("is_deload") is True,
            deload_why=CoachPlanEngine._deload_why(data),
            route_note=CoachPlanEngine._route_note(data),
            block=CoachPlanEngine._parse_block(data.get("block")),
            extra_day_note=(
                plan_text(str(data.get("suggest_extra_day")).strip())
                if data.get("suggest_extra_day") else None
            ),
        )

    @staticmethod
    def _deload_why(data: dict) -> str | None:
        """A razão da descarga — só existe se a IA marcou a semana como descarga
        (razão solta numa semana normal é ruído)."""

        if data.get("is_deload") is not True:

            return None

        why = str(data.get("deload_why") or "").strip()

        return plan_text(why) if why and why.lower() not in ("null", "none") else None

    @staticmethod
    def _route_note(data: dict) -> str | None:
        """O motivo de a semana fugir da rota (volume fora de ±20%), nas palavras do coach."""

        note = str(data.get("route_note") or "").strip()

        return plan_text(note) if note and note.lower() not in ("null", "none") else None

    @staticmethod
    def _parse_block(raw) -> dict | None:
        """O bloco que a IA abriu/redefiniu: foco + papel de cada semana (2 a 8
        semanas). None se não veio ou veio torto."""

        if not isinstance(raw, dict):

            return None

        weeks_plan = [
            str(w).strip() for w in (raw.get("weeks_plan") or []) if str(w).strip()
        ]

        focus = str(raw.get("focus") or "").strip()

        if not focus or not 2 <= len(weeks_plan) <= 8:

            return None

        return {"weeks": len(weeks_plan), "focus": focus, "weeks_plan": weeks_plan}

    @staticmethod
    def _parse_sessions(raw_sessions) -> list[PlannedSession]:

        if not isinstance(raw_sessions, list):

            return []

        sessions = []

        for item in raw_sessions:

            if not isinstance(item, dict):

                continue

            day = item.get("day")

            if day not in VALID_DAYS:

                continue

            kind = item.get("kind", "run")

            # descarta musculação/descanso/bike — não planejamos isso
            if kind not in RUNNING_KINDS:

                continue

            distance = item.get("distance_km")

            if not isinstance(distance, (int, float)) or distance <= 0:

                distance = None

            parsed_steps = parse_steps(item.get("steps"))

            # A distância REAL vem dos PASSOS (inclui aquecimento/recuperações/
            # desaquecimento) — o número solto da IA às vezes os esquece (dá 6.5
            # quando os passos somam 7.5). Com passos, eles mandam; sem eles,
            # cai no distance_km da IA.
            step_km = total_distance_km(parsed_steps)

            if step_km is not None:

                distance = step_km

            duration = item.get("duration_min")

            if not isinstance(duration, (int, float)) or duration <= 0:

                duration = None

            sessions.append(
                PlannedSession(
                    day=day,
                    workout_type=(
                        item.get("workout_type")
                        or CoachPlanEngine._default_type(kind)
                    ),
                    objective=plan_text(str(item.get("purpose", "")).strip()),
                    planned_distance_km=(
                        round(float(distance), 1)
                        if distance is not None
                        else None
                    ),
                    # sessão por TEMPO: o atleta prefere/pediu minutos, não km
                    planned_duration_minutes=(
                        int(round(float(duration)))
                        if duration is not None
                        else None
                    ),
                    target_pace_min=CoachPlanEngine._pace(item.get("pace_min")),
                    target_pace_max=CoachPlanEngine._pace(item.get("pace_max")),
                    kind=kind,
                    structure=CoachPlanEngine._structure(
                        item.get("structure"),
                    ),
                    purpose=plan_text(str(item.get("purpose", "")).strip()),
                    steps=parsed_steps,
                )
            )

        return sessions

    @staticmethod
    def _structure(value) -> str:
        """Estrutura vem como lista de passos (preferido) ou string; guarda
        um passo por linha pra o formatter renderizar cada um."""

        if isinstance(value, list):

            return plan_lines(
                "\n".join(str(step).strip() for step in value if str(step).strip())
            )

        return plan_lines(str(value or "").strip())

    @staticmethod
    def _default_type(kind: str) -> str:

        return {
            "walk": "Caminhada",
            "run_walk": "Corrida-caminhada",
        }.get(kind, "Corrida")

    @staticmethod
    def _pace(value) -> str | None:

        if not value:

            return None

        return str(value).strip()
