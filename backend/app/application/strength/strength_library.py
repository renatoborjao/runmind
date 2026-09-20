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


def library() -> dict:
    """Biblioteca completa pro app: exercícios agrupados por categoria + crédito.
    Conteúdo estático curado (sem PII), igual pra todo atleta."""

    return {
        "categories": CATEGORIES,
        "exercises": EXERCISES,
        "credit": CREDIT,
    }
