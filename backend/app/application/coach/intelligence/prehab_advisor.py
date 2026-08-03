"""Força/mobilidade PREVENTIVA (prehab de corrida): quando o risco de lesão sobe
ou o atleta relata dor, o coach não fica só em "segure a carga" — dá 2-3
exercícios CONCRETOS pra a área, com o alerta de procurar um profissional se a
dor for aguda/persistente. Não é virar personal de academia: é o prehab que todo
bom treinador de corrida orienta. Base de conhecimento determinística (sem IA,
sem dependência externa — [[feedback_free_tools_preference]]).

Dispara no quadro do coach por (a) dor relatada numa área conhecida ou (b) risco
de lesão elevado (prehab geral). Ver [[injury_risk_analyzer]] e o check-in."""

import re
import unicodedata

# área -> (rótulo, palavras-chave no relato, 2-3 exercícios de prehab)
_AREAS: list[tuple[str, list[str], list[str]]] = [
    (
        "joelho",
        ["joelho", "patela", "rotula"],
        [
            "fortalecer glúteo médio: concha/clam (deitado de lado, 2x15 cada)",
            "agachamento isométrico na parede (3x30s)",
            "ponte de glúteo (2x15); segure descidas/ladeira forte por ora",
        ],
    ),
    (
        "panturrilha ou tendão de Aquiles",
        ["panturrilha", "aquiles", "batata da perna", "gemeo", "gastro"],
        [
            "elevação de panturrilha (calf raise) 3x15, desça devagar",
            "isométrico na ponta do pé (3x30s)",
            "alongamento suave da panturrilha após correr",
        ],
    ),
    (
        "canela (canelite/shin splints)",
        ["canela", "canelite", "tibia", "shin"],
        [
            "elevação da ponta do pé (tibial anterior) 3x15",
            "reduza impacto/volume nos próximos dias; pise mais leve",
            "cheque o desgaste do tênis (amortecimento gasto piora)",
        ],
    ),
    (
        "quadril / banda iliotibial",
        ["quadril", "iliotibial", "it band", "lateral da coxa", "bandinha"],
        [
            "glúteo médio: monster walk com miniband (2x10 passos)",
            "concha/clam (2x15 cada lado)",
            "mobilidade de quadril (90/90) antes de correr",
        ],
    ),
    (
        "posterior da coxa (isquiotibiais)",
        ["posterior", "isquio", "isquiotibial", "atras da coxa", "posterior de coxa"],
        [
            "ponte unipodal (2x10 cada perna)",
            "nordic curl leve/assistido (2x6), controlando a descida",
            "mobilidade de posterior sem forçar (nada de alongar dor aguda)",
        ],
    ),
    (
        "planta do pé (fascite plantar)",
        ["planta do pe", "fascite", "sola do pe", "calcanhar", "fascia"],
        [
            "rolar a sola num rolinho/bolinha (1-2 min por pé)",
            "fortalecer o arco: toalha com os dedos (2x15)",
            "elevação de panturrilha (o Aquiles puxa a fáscia) 3x15",
        ],
    ),
    (
        "lombar / core",
        ["lombar", "costas", "core", "abdomen", "abdominal"],
        [
            "prancha frontal + lateral (3x20-30s cada)",
            "ponte de glúteo (2x15)",
            "bird-dog (2x10 cada lado) pra estabilidade",
        ],
    ),
]

# prehab GERAL (risco elevado sem dor localizada): a base que protege o corredor
_GENERAL = [
    "glúteo médio: concha/clam (2x15 cada lado)",
    "ponte de glúteo (2x15) e prancha (3x30s) pra core",
    "elevação de panturrilha (3x15) e mobilidade de quadril antes de correr",
]

_SAFETY = (
    "sinalize que é prevenção, não tratamento: se a dor for AGUDA, com inchaço, "
    "ou que piora/persiste, o atleta deve PARAR e procurar um profissional "
    "(fisio/médico) — não insista por cima da dor"
)


def _normalize(text: str) -> str:

    lowered = (text or "").lower().strip()

    without = "".join(
        c
        for c in unicodedata.normalize("NFD", lowered)
        if unicodedata.category(c) != "Mn"
    )

    return re.sub(r"\s+", " ", without)


class PrehabAdvisor:

    @staticmethod
    def detect_area(text: str) -> tuple[str, list[str]] | None:
        """Área de dor reconhecida no relato -> (rótulo, exercícios). None se
        nenhuma área conhecida aparece (aí o coach fala geral ou pergunta onde)."""

        norm = _normalize(text)

        for label, cues, exercises in _AREAS:

            if any(cue in norm for cue in cues):

                return label, exercises

        return None

    @staticmethod
    def directive_for_pain(note: str) -> str:
        """Diretriz pro coach quando o atleta RELATA dor: exercícios da área (ou
        peça pra localizar) + o alerta de segurança. Vazio se não há relato."""

        if not note:

            return ""

        found = PrehabAdvisor.detect_area(note)

        if found is None:

            return (
                "O atleta relatou dor/incômodo mas não deu pra saber a região. "
                "Pergunte ONDE dói e, com a área, oriente 2-3 exercícios "
                f"preventivos específicos. {_SAFETY.capitalize()}."
            )

        label, exercises = found

        return (
            f"PREVENÇÃO — o atleta relatou dor em {label}. Oriente estes "
            "exercícios preventivos (prehab), de forma acolhedora: "
            + "; ".join(exercises)
            + f". {_SAFETY.capitalize()}."
        )

    @staticmethod
    def directive_general() -> str:
        """Prehab GERAL pro risco elevado sem dor localizada — prevenção."""

        return (
            "PREVENÇÃO (risco de lesão elevado) — além de segurar a carga, "
            "vale orientar prehab de corrida: "
            + "; ".join(_GENERAL)
            + ". Enquadre como prevenção pra seguir treinando com segurança."
        )
