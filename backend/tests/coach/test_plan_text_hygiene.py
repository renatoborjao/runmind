"""O TEXTO DO PLANO que o atleta lê passa pela mesma higiene da análise. A auditoria dos planos de
18/10 (os 6 atletas) achou os números CERTOS (volume = soma das sessões, passos fecham com os km,
faixas de pace na ordem) mas a linguagem com os mesmos vícios da análise: "crave a faixa",
"cravando um trecho", "segure a empolgação" (estado interno que o atleta nunca contou — e a voz do
coach proíbe), "ACWR 1.7" no plano da Fernanda e "não deixe o pace cair abaixo de 6:45/km"
(ambíguo: pace menor é mais rápido)."""

import json
from datetime import date

from app.application.coach.planning.coach_plan_engine import PROMPT_TEMPLATE, CoachPlanEngine
from app.application.coach.writer.analysis_hygiene import plan_lines, plan_text


def test_the_real_plan_sentences_lose_the_tics_and_the_invented_feelings():

    assert plan_text(
        "Não tente compensar tempos passados, crave a faixa e mantenha a consistência."
    ) == "Não tente compensar tempos passados, mantenha a faixa e mantenha a consistência."

    assert plan_text(
        "O objetivo hoje é recuperar do volume não planejado da semana passada. Segure a "
        "empolgação e mantenha a percepção de esforço baixa."
    ) == (
        "O objetivo hoje é recuperar do volume não planejado da semana passada. Mantenha a "
        "percepção de esforço baixa."
    )

    assert plan_text("O desafio de hoje não é a distância, mas sim cravar o ritmo alvo.") == (
        "O desafio de hoje não é a distância, mas sim manter o ritmo alvo."
    )

    assert "cravando" not in plan_text(
        "Realizar o simulado principal do bloco, cravando um trecho robusto no ritmo da prova."
    )


def test_the_load_jargon_leaves_the_plan_too():
    """O plano da Fernanda (18/10): "absorver a alta carga recente (ACWR 1.7)"."""

    text = plan_text(
        "Semana de descarga do bloco: reduzir o volume para absorver a alta carga recente "
        "(ACWR 1.7), recuperar o corpo e consolidar a ótima economia aeróbica."
    )

    assert "ACWR" not in text
    assert text.startswith("Semana de descarga do bloco: reduzir o volume")
    assert "consolidar a ótima economia aeróbica" in text


def test_a_list_of_numbers_is_never_corrupted_by_the_cleanup():
    """Achado pelo próprio teste: a lista "47, 32, 39 e 43 km" perdia o "32" — um pedaço de uma
    palavra entre vírgulas era tratado como fragmento. Número do atleta não some."""

    text = plan_text(
        "Você fez 47, 32, 39 e 43 km nas últimas semanas: a carga alta (ACWR 1.7) pede uma "
        "semana leve."
    )

    assert text == "Você fez 47, 32, 39 e 43 km nas últimas semanas."

    from app.application.coach.writer.analysis_hygiene import clean_text

    analysis = clean_text(
        "Você fez 5.4 km em 27:54, com parciais 6:37, 6:38, 6:07 e 5:47 e frequência cardíaca "
        "na Z2.",
        has_hr=False,
    )

    assert "6:37, 6:38, 6:07 e 5:47" in analysis
    assert "Z2" not in analysis and "frequência" not in analysis


def test_a_plan_field_is_never_lost():
    """Se a limpeza esvazia o texto, o campo volta com ele só sem as muletas."""

    assert plan_text("Foco absoluto: segurar a empolgação.") != ""
    assert plan_text("") == "" and plan_text(None) == ""


def test_the_steps_keep_one_per_line_and_the_labels_survive():

    structure = "\n".join(
        [
            "Aquecimento: 2 km leve (6:20-6:45/km)",
            "Série: 4x 1,5 km no pace de limiar (5:25-5:35/km)",
            "Dica: Crave a faixa e segure a empolgação.",
            "Foco: retomar o limiar após a gripe.",
        ]
    )

    assert plan_lines(structure).split("\n") == [
        "Aquecimento: 2 km leve (6:20-6:45/km)",
        "Série: 4x 1,5 km no pace de limiar (5:25-5:35/km)",
        "Dica: Mantenha a faixa.",
        "Foco: retomar o limiar após a gripe.",
    ]


def test_a_clean_plan_is_untouched():

    text = "Aquecimento: 2 km leve (6:20-6:45/km)\nSérie: 6x 400m no pace 5:20-5:35/km"

    assert plan_lines(text) == text
    assert plan_text("Retomar a consistência dos 3 dias com o leve de verdade.") == (
        "Retomar a consistência dos 3 dias com o leve de verdade."
    )


def _raw(**overrides) -> str:

    plan = {
        "phase": "BUILD",
        "weekly_objective": "Retomar a rotina, cravando a faixa leve e segurando a empolgação.",
        "is_deload": True,
        "deload_why": "Você fez 47, 32, 39 e 43 km: a carga alta (ACWR 1.7) pede uma semana leve.",
        "suggest_extra_day": None,
        "sessions": [
            {
                "day": "Monday", "kind": "run", "workout_type": "Rodagem Leve",
                "distance_km": 5, "pace_min": "6:45", "pace_max": "7:15",
                "purpose": "Segure a empolgação e recupere o volume da semana passada.",
                "structure": [
                    "Rodagem: 5 km em ritmo fácil (6:45-7:15/km)",
                    "Dica: o desafio é cravar o ritmo alvo.",
                ],
            }
        ],
    }

    plan.update(overrides)

    return json.dumps(plan, ensure_ascii=False)


def test_the_engine_cleans_every_text_the_athlete_reads():

    plan = CoachPlanEngine._to_plan(_raw(), "Hélio", "10 km", date(2026, 10, 26))

    session = plan.sessions[0]

    assert "cravando" not in plan.weekly_objective and "empolgação" not in plan.weekly_objective
    assert plan.weekly_objective.startswith("Retomar a rotina")
    assert "ACWR" not in plan.deload_why and "47, 32, 39 e 43 km" in plan.deload_why
    assert "empolgação" not in session.objective and "empolgação" not in session.purpose
    # os passos seguem um por linha, com a dica limpa
    assert session.structure.split("\n") == [
        "Rodagem: 5 km em ritmo fácil (6:45-7:15/km)",
        "Dica: o desafio é manter o ritmo alvo.",
    ]
    # e o resto do plano não muda
    assert plan.phase == "BUILD" and plan.is_deload is True
    assert session.workout_type == "Rodagem Leve" and session.planned_distance_km == 5.0


def test_the_prompt_teaches_the_plan_language_rules():

    assert "LINGUAGEM DO PLANO" in PROMPT_TEMPLATE
    assert "\"mais rápido que 6:45\" / \"mais lento que 7:15\"" in PROMPT_TEMPLATE
    assert "nunca \"o pace cair abaixo de X\"" in PROMPT_TEMPLATE
    assert "nunca de um estado interno que ele não contou" in PROMPT_TEMPLATE
    assert "Sem jargão de carga (ACWR, carga aguda)" in PROMPT_TEMPLATE
