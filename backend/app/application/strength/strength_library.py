"""Biblioteca curada de exercícios de FORTALECIMENTO PARA QUEM CORRE.

Foco em corredor: cadeia posterior (glúteo/isquios), core/estabilidade de
quadril e panturrilha — os elos que previnem lesão e melhoram a economia de
corrida. Tudo peso do corpo ou faixa elástica (dá pra fazer em casa).

- DADOS (nomes/músculos/base do movimento): Free Exercise DB (domínio público,
  licença Unlicense) — reaproveitados livremente.
- DEMONSTRAÇÃO: 2 fotos (início/fim do movimento) do mesmo acervo (imagens
  Everkinetic, CC-BY-SA) servidas via CDN; o app alterna os 2 quadros = um
  "GIF" simples do movimento. Crédito exibido na tela. Vídeo próprio é fase 2.
- CUES/dicas: escritas por nós, no tom do coach, com o PORQUÊ pra corredor.

Ver [[project_ideias_produto]], [[feedback_free_tools_preference]],
[[project_analise_corpo_garmin]] (a força conta na carga via cross-training)."""

# base das imagens (2 quadros por exercício) — CDN estável do repositório aberto
_IMG = "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@main/exercises"


def _imgs(ex_id: str) -> list[str]:

    return [f"{_IMG}/{ex_id}/0.jpg", f"{_IMG}/{ex_id}/1.jpg"]


# categorias (ordem de exibição) — a espinha do fortalecimento do corredor
CATEGORIES = [
    "Glúteos e quadril",
    "Core e estabilidade",
    "Pernas",
    "Panturrilha",
]

# crédito obrigatório (CC-BY-SA das imagens)
CREDIT = "Demonstrações: Free Exercise DB (imagens CC-BY-SA)."


# Cada exercício: por que importa pro corredor + como fazer + erro comum.
EXERCISES = [
    {
        "id": "single_leg_glute_bridge",
        "name": "Ponte de glúteo unilateral",
        "category": "Glúteos e quadril",
        "target": "Glúteos, isquiotibiais",
        "equipment": "Peso do corpo",
        "why": "O glúteo é o motor da passada. Unilateral corrige o lado mais "
               "fraco — causa comum de dor no joelho e no quadril de quem corre.",
        "cues": [
            "Deitado de costas, um pé no chão e a outra perna estendida.",
            "Suba o quadril empurrando pelo calcanhar, apertando o glúteo no topo.",
            "Quadril nivelado (não deixe cair pro lado da perna solta).",
        ],
        "reps": "3 x 10 cada perna",
        "images": _imgs("Single_Leg_Glute_Bridge"),
    },
    {
        "id": "glute_bridge",
        "name": "Ponte de glúteo",
        "category": "Glúteos e quadril",
        "target": "Glúteos",
        "equipment": "Peso do corpo",
        "why": "Ativa o glúteo e ensina o quadril a estender — o que impulsiona "
               "você pra frente na corrida.",
        "cues": [
            "Costas no chão, joelhos dobrados, pés na largura do quadril.",
            "Suba o quadril até o corpo formar uma linha do joelho ao ombro.",
            "Aperte o glúteo em cima; não force a lombar.",
        ],
        "reps": "3 x 15",
        "images": _imgs("Butt_Lift_Bridge"),
    },
    {
        "id": "hip_abduction_band",
        "name": "Abdução de quadril com faixa",
        "category": "Glúteos e quadril",
        "target": "Glúteo médio (abdutores)",
        "equipment": "Faixa elástica",
        "why": "O glúteo médio estabiliza o quadril a cada passada. Fraco, o "
               "joelho colapsa pra dentro — raiz de dor patelar e canela.",
        "cues": [
            "Faixa acima dos joelhos, em pé ou deitado de lado.",
            "Abra a perna contra a faixa, controlado, sem girar o tronco.",
            "Volte devagar — o controle na volta é metade do exercício.",
        ],
        "reps": "3 x 12 cada lado",
        "images": _imgs("Hip_Lift_with_Band"),
    },
    {
        "id": "plank",
        "name": "Prancha",
        "category": "Core e estabilidade",
        "target": "Core (abdômen profundo)",
        "equipment": "Peso do corpo",
        "why": "Um core firme não deixa a energia 'vazar' a cada passo — você "
               "corre mais eficiente e a postura não desaba no fim da prova.",
        "cues": [
            "Antebraços no chão, cotovelos sob os ombros, corpo reto.",
            "Contraia abdômen e glúteo; quadril nem cai nem sobe.",
            "Respire normal. Qualidade > tempo: pare quando a forma quebrar.",
        ],
        "reps": "3 x 30–45 s",
        "images": _imgs("Plank"),
    },
    {
        "id": "side_plank",
        "name": "Prancha lateral",
        "category": "Core e estabilidade",
        "target": "Core lateral, quadril",
        "equipment": "Peso do corpo",
        "why": "Trabalha a estabilidade lateral do quadril — o que segura a "
               "pelve no lugar e protege o joelho na corrida.",
        "cues": [
            "Apoiado no antebraço, corpo em linha reta de lado.",
            "Suba o quadril e segure; não deixe afundar.",
            "Olhar pra frente, pescoço relaxado.",
        ],
        "reps": "3 x 25–35 s cada lado",
        "images": _imgs("Side_Bridge"),
    },
    {
        "id": "superman",
        "name": "Superman",
        "category": "Core e estabilidade",
        "target": "Lombar, cadeia posterior",
        "equipment": "Peso do corpo",
        "why": "Fortalece a lombar e a cadeia posterior — sustenta a postura e "
               "evita a dor nas costas nas corridas longas.",
        "cues": [
            "Deitado de bruços, braços à frente.",
            "Eleve braços e pernas juntos, devagar, apertando o glúteo.",
            "Sem 'chutar' — movimento controlado, pescoço neutro.",
        ],
        "reps": "3 x 12",
        "images": _imgs("Superman"),
    },
    {
        "id": "walking_lunge",
        "name": "Afundo caminhando",
        "category": "Pernas",
        "target": "Quadríceps, glúteos",
        "equipment": "Peso do corpo",
        "why": "Trabalha uma perna de cada vez, igual à corrida — força e "
               "equilíbrio que se transferem direto pra passada.",
        "cues": [
            "Passo à frente, desça até o joelho de trás quase tocar o chão.",
            "Joelho da frente alinhado com o pé (não passa muito da ponta).",
            "Tronco ereto; impulsione pelo calcanhar da frente.",
        ],
        "reps": "3 x 10 cada perna",
        "images": _imgs("Bodyweight_Walking_Lunge"),
    },
    {
        "id": "split_squat",
        "name": "Agachamento unilateral (split)",
        "category": "Pernas",
        "target": "Quadríceps, glúteos, isquios",
        "equipment": "Peso do corpo",
        "why": "Estabilidade e força numa perna só — corrige assimetrias que "
               "sobrecarregam um lado e viram lesão.",
        "cues": [
            "Um pé à frente, outro atrás (pode apoiar num banco).",
            "Desça reto, joelho da frente estável, sem cair pra dentro.",
            "Suba pela perna da frente, controlado.",
        ],
        "reps": "3 x 10 cada perna",
        "images": _imgs("Split_Squats"),
    },
    {
        "id": "step_up",
        "name": "Subida no step",
        "category": "Pernas",
        "target": "Glúteos, quadríceps",
        "equipment": "Degrau/banco",
        "why": "Imita a mecânica de subir na passada e reforça o glúteo no "
               "apoio — ótimo pra quem corre em subida ou trilha.",
        "cues": [
            "Suba num degrau firme empurrando pelo calcanhar.",
            "Suba o joelho da perna livre no topo; controle a descida.",
            "Sem impulso do pé de trás — quem faz força é a perna de cima.",
        ],
        "reps": "3 x 10 cada perna",
        "images": _imgs("Step-up_with_Knee_Raise"),
    },
    {
        "id": "calf_raise",
        "name": "Elevação de panturrilha",
        "category": "Panturrilha",
        "target": "Panturrilha, tendão de Aquiles",
        "equipment": "Peso do corpo / faixa",
        "why": "A panturrilha é a mola da corrida e o tendão de Aquiles adora "
               "adoecer. Fortalecer previne uma das lesões mais chatas do corredor.",
        "cues": [
            "Em pé, suba na ponta dos pés o máximo que der.",
            "Desça devagar (a fase lenta é a que fortalece o tendão).",
            "Progrida pra uma perna só quando ficar fácil.",
        ],
        "reps": "3 x 15",
        "images": _imgs("Calf_Raises_-_With_Bands"),
    },
]


# Enriquecimento dos 10 acima (erro comum / onde sentir / mais fácil-difícil /
# respiração + prescrição ESTRUTURADA). `execution` alimenta a execução guiada
# (contar série/rep/tempo, slice 3). Conteúdo curado no tom do coach.
_ENRICH = {
    "single_leg_glute_bridge": {
        "common_mistake": "Deixar o quadril despencar do lado sem apoio.",
        "feel_where": "Sinta o glúteo e a parte de trás da coxa empurrando o chão.",
        "regression": "Faça a ponte tradicional com os dois pés apoiados.",
        "progression": "Apoie o pé sobre um banco ou adicione peso no quadril.",
        "breathing": "Solte o ar ao subir e puxe ao descer.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    "glute_bridge": {
        "common_mistake": "Arquear a lombar no topo em vez de usar o glúteo.",
        "feel_where": "Sinta a contração forte no glúteo no topo do movimento.",
        "regression": "Reduza a amplitude mantendo as costas bem apoiadas.",
        "progression": "Faça a subida rápida e segure 3 segundos no topo.",
        "breathing": "Expire na subida e inspire no retorno.",
        "execution": {"sets": 3, "reps": 12, "hold_seconds": None, "per_side": False, "rest_seconds": 45},
    },
    "hip_abduction_band": {
        "common_mistake": "Girar o pé para fora em vez de manter a ponta pra frente.",
        "feel_where": "Sinta queimar a lateral do quadril (glúteo médio).",
        "regression": "Faça o movimento deitado sem o elástico.",
        "progression": "Aumente a resistência da faixa elástica.",
        "breathing": "Solte o ar ao afastar a perna e puxe ao voltar.",
        "execution": {"sets": 3, "reps": 12, "hold_seconds": None, "per_side": True, "rest_seconds": 30},
    },
    "plank": {
        "common_mistake": "Deixar o quadril ceder pro chão ou subir demais.",
        "feel_where": "Sinta o abdômen firme e todo o tronco trabalhado.",
        "regression": "Apoie os joelhos no chão.",
        "progression": "Tire um pé do chão alternando os lados.",
        "breathing": "Respire de forma curta e firme sem soltar o abdômen.",
        "execution": {"sets": 3, "reps": None, "hold_seconds": 45, "per_side": False, "rest_seconds": 45},
    },
    "side_plank": {
        "common_mistake": "Deixar o quadril cair em direção ao chão.",
        "feel_where": "Sinta a lateral do abdômen e o quadril segurando o corpo.",
        "regression": "Apoie os joelhos dobrados no chão.",
        "progression": "Eleve a perna de cima durante a sustentação.",
        "breathing": "Mantenha a respiração contínua e controlada.",
        "execution": {"sets": 3, "reps": None, "hold_seconds": 30, "per_side": True, "rest_seconds": 45},
    },
    "superman": {
        "common_mistake": "Hiperestender o pescoço olhando para a frente.",
        "feel_where": "Sinta a musculatura das costas e dos glúteos acionada.",
        "regression": "Eleve apenas os braços ou apenas as pernas de cada vez.",
        "progression": "Segure 3 segundos no topo a cada repetição.",
        "breathing": "Solte o ar ao subir e puxe ao descer.",
        "execution": {"sets": 3, "reps": 12, "hold_seconds": None, "per_side": False, "rest_seconds": 45},
    },
    "walking_lunge": {
        "common_mistake": "Deixar o joelho da frente passar muito da ponta do pé.",
        "feel_where": "Sinta a coxa da frente e o glúteo empurrarem você.",
        "regression": "Faça o afundo estático sem caminhar.",
        "progression": "Segure halteres ou kettlebells ao caminhar.",
        "breathing": "Inspire ao dar o passo e descer; expire ao subir.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 60},
    },
    "split_squat": {
        "common_mistake": "Projetar o tronco pra frente sem dobrar o joelho de trás.",
        "feel_where": "Sinta o trabalho forte na coxa e glúteo da perna da frente.",
        "regression": "Apoie a mão em uma parede para dar equilíbrio.",
        "progression": "Eleve o pé de trás em um banco (agachamento búlgaro).",
        "breathing": "Desça puxando o ar e suba soltando.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    "step_up": {
        "common_mistake": "Tomar impulso com a perna de baixo em vez de subir pela de cima.",
        "feel_where": "Sinta o glúteo da perna do degrau fazer todo o esforço.",
        "regression": "Use um degrau mais baixo.",
        "progression": "Suba com o joelho em elevação rápida e use uma caixa alta.",
        "breathing": "Expire forte ao subir no degrau e inspire ao descer.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    "calf_raise": {
        "common_mistake": "Fazer rápido sem esticar bem a panturrilha embaixo.",
        "feel_where": "Sinta queimar a batata da perna até o topo.",
        "regression": "Faça sentado com peso sobre as coxas.",
        "progression": "Faça em um degrau para aumentar a amplitude.",
        "breathing": "Solte o ar no topo e puxe na descida.",
        "execution": {"sets": 3, "reps": 15, "hold_seconds": None, "per_side": False, "rest_seconds": 30},
    },
}

for _e in EXERCISES:
    _e.update(_ENRICH.get(_e["id"], {}))


# Exercícios NOVOS (mesma curadoria). Bird-dog/clamshell/caminhada lateral e
# panturrilha unilateral não têm foto fiel no acervo aberto → placeholder (a
# tela trata bem); dead bug tem. O conteúdo textual (o forte) vem completo.
EXERCISES += [
    {
        "id": "single_leg_calf_raise",
        "name": "Elevação de panturrilha unilateral",
        "category": "Panturrilha",
        "target": "Sóleo e gastrocnêmio",
        "equipment": "Degrau/banco",
        "why": "Fortalece a panturrilha de forma isolada pra suportar o impacto "
               "a cada passada — a impulsão que uma corrida eficiente pede.",
        "cues": [
            "Apoie a metade do pé no degrau e deixe o calcanhar descer bem.",
            "Suba na ponta do pé até o máximo, com controle.",
            "Desça devagar sentindo o alongamento antes da próxima repetição.",
        ],
        "reps": "3 x 12 cada perna",
        "images": [],
        "common_mistake": "Usar impulso ou dobrar o joelho durante a subida.",
        "feel_where": "Sinta o foco total na panturrilha da perna ativa.",
        "regression": "Faça no chão plano, sem a amplitude negativa do degrau.",
        "progression": "Segure um peso na mão do mesmo lado do pé apoiado.",
        "breathing": "Expire ao subir na ponta do pé e inspire ao descer.",
        "execution": {"sets": 3, "reps": 12, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    {
        "id": "monster_walk",
        "name": "Caminhada lateral com faixa",
        "category": "Glúteos e quadril",
        "target": "Glúteo médio e estabilizadores do quadril",
        "equipment": "Faixa elástica",
        "why": "Impede o joelho de colapsar pra dentro na passada e mantém a "
               "bacia alinhada — freia desgastes que viram dor de joelho e canela.",
        "cues": [
            "Faixa nos tornozelos e joelhos levemente flexionados.",
            "Dê passos laterais mantendo a tensão do elástico o tempo todo.",
            "Pés apontados pra frente, sem os calcanhares se aproximarem.",
        ],
        "reps": "3 x 12 cada lado",
        "images": [],
        "common_mistake": "Arrastar o pé de trás ou perder a tensão da faixa.",
        "feel_where": "Sinta queimar as laterais dos quadris enquanto caminha.",
        "regression": "Posicione a faixa acima dos joelhos.",
        "progression": "Desça mais o quadril, em posição de meio agachamento.",
        "breathing": "Mantenha uma respiração ritmada conforme dá os passos.",
        "execution": {"sets": 3, "reps": 12, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    {
        "id": "clamshell",
        "name": "Concha (clamshell)",
        "category": "Glúteos e quadril",
        "target": "Rotadores externos do quadril e glúteo médio",
        "equipment": "Faixa elástica",
        "why": "Estabiliza a pelve pra sua energia ir pra frente, e não pros "
               "lados — sustenta a postura ereta na fase de apoio da passada.",
        "cues": [
            "Deitado de lado, joelhos dobrados e calcanhares na linha do quadril.",
            "Pés juntos, abra o joelho de cima o máximo que puder.",
            "Volte devagar, sem rodar o tronco pra trás.",
        ],
        "reps": "3 x 15 cada lado",
        "images": [],
        "common_mistake": "Rodar o tronco ou a bacia pra trás pra ajudar a abrir.",
        "feel_where": "Sinta o trabalho bem na lateral do glúteo.",
        "regression": "Faça sem a faixa elástica.",
        "progression": "Eleve os pés do chão mantendo a execução.",
        "breathing": "Solte o ar na abertura do joelho e puxe no retorno.",
        "execution": {"sets": 3, "reps": 15, "hold_seconds": None, "per_side": True, "rest_seconds": 30},
    },
    {
        "id": "dead_bug",
        "name": "Dead bug",
        "category": "Core e estabilidade",
        "target": "Transverso do abdômen e core profundo",
        "equipment": "Peso do corpo",
        "why": "Ensina o core a estabilizar a coluna enquanto braços e pernas se "
               "movem — o que segura o ritmo e economiza energia no trote.",
        "cues": [
            "De costas, aperte a lombar firme contra o chão.",
            "Estenda braço e perna opostos devagar até quase tocar o chão.",
            "Volte à posição inicial com o abdômen travado.",
        ],
        "reps": "3 x 10 cada lado",
        "images": _imgs("Dead_Bug"),
        "common_mistake": "Descolar a lombar do chão ao mover as pernas.",
        "feel_where": "Sinta a parede abdominal profunda contraída do início ao fim.",
        "regression": "Mova apenas os braços ou apenas as pernas.",
        "progression": "Segure um mini-band entre as mãos ou os pés.",
        "breathing": "Solte o ar ao estender braço e perna; puxe ao voltar.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
    {
        "id": "bird_dog",
        "name": "Bird-dog",
        "category": "Core e estabilidade",
        "target": "Eretores da espinha, glúteo e core",
        "equipment": "Peso do corpo",
        "why": "Treina o cruzamento de força entre ombro e quadril opostos — o "
               "padrão direto da mecânica de uma passada forte e estável.",
        "cues": [
            "Em quatro apoios, mãos sob os ombros e joelhos sob o quadril.",
            "Estenda o braço direito à frente e a perna esquerda pra trás.",
            "Tronco reto, sem balançar o quadril; depois troque o lado.",
        ],
        "reps": "3 x 10 cada lado",
        "images": [],
        "common_mistake": "Girar o quadril ou arquear as costas ao esticar a perna.",
        "feel_where": "Sinta a estabilidade no abdômen, na lombar e no glúteo.",
        "regression": "Mova só a perna por vez, mantendo os braços fixos.",
        "progression": "Traga joelho e cotovelo opostos até se tocarem antes de estender.",
        "breathing": "Inspire na posição inicial e expire ao estender os membros.",
        "execution": {"sets": 3, "reps": 10, "hold_seconds": None, "per_side": True, "rest_seconds": 45},
    },
]


def library() -> dict:
    """Biblioteca completa pro app: exercícios agrupados por categoria + crédito.
    Conteúdo estático curado (sem PII), igual pra todo atleta."""

    return {
        "categories": CATEGORIES,
        "exercises": EXERCISES,
        "credit": CREDIT,
    }
