import asyncio
from unittest.mock import AsyncMock, patch

from app.application.coach.writer.ai_analysis_writer import (
    AIAnalysisWriter,
)
from app.domain.entities.workout_structure import WorkoutStructure
from tests.coach.factories import (
    make_activity,
    make_context,
    make_enriched_activity,
    make_planned_session,
)

MODULE = "app.application.coach.writer.ai_analysis_writer"
GEN_TEXT = "app.infrastructure.integrations.gemini.client.generate_text"


def _structure(**overrides) -> WorkoutStructure:

    defaults = dict(
        km_splits=[4.0, 6.5, 4.0, 6.5],
        km_hr=[172, 150, 174, 151],
        lap_count=0,
        lap_paces=[],
        fastest_km_pace=4.0,
        slowest_km_pace=6.5,
        pace_spread=0.625,
        split_trend="even",
        is_interval=True,
        cadence_spm=178,
        hr_avg=160,
        hr_max=182,
        has_detail=True,
    )

    defaults.update(overrides)

    return WorkoutStructure(**defaults)


def _write(context=None, **patch_kwargs):

    with patch(GEN_TEXT, new=AsyncMock(**patch_kwargs)):

        return asyncio.run(
            AIAnalysisWriter.write(context or make_context())
        )


def test_returns_bullets_from_ai():

    lines = _write(
        return_value='{"analysis": ["Belo intervalado.", "Segurou os tiros."]}',
    )

    assert lines == ["Belo intervalado.", "Segurou os tiros."]


def test_returns_none_when_ai_fails():

    lines = _write(side_effect=RuntimeError("Gemini fora do ar"))

    assert lines is None


def test_returns_none_on_empty_analysis():

    lines = _write(return_value='{"analysis": []}')

    assert lines is None


def test_caps_at_max_bullets():

    lines = _write(
        return_value='{"analysis": ["a", "b", "c", "d", "e", "f"]}',
    )

    assert len(lines) == 4


def test_facts_feed_splits_and_interval_to_prompt():

    executed = make_enriched_activity(structure=_structure())

    context = make_context(executed=executed)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(GEN_TEXT, new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    assert "splits:" in prompt
    assert "intervalado" in prompt
    # pace + FC por km: sem a FC a IA inventava "fadiga" em treino com
    # FC caindo na segunda metade
    assert "km1 4:00 (172bpm)" in prompt


def test_facts_flag_outdoor_when_gps_present():
    """Treino com GPS (rua/parque) recebe 'AR LIVRE' explícito pra a IA NÃO
    assumir esteira a partir da prescrição (bug do Renato: correu no parque e
    a análise disse 'vi que você rodou na esteira')."""

    executed = make_enriched_activity(
        indoor=False,
        activity=make_activity(start_latitude=-23.5, start_longitude=-46.7),
    )

    facts = AIAnalysisWriter._facts(make_context(executed=executed))

    assert "AR LIVRE" in facts
    assert "ESTEIRA" not in facts


def test_executed_laps_fact_drops_phantom_laps():
    """Voltas-fantasma (relógio reiniciando: 5 m, 13 m) saem; bloco real fica."""

    laps = [
        {"distance_m": 5, "duration_s": 5, "pace": 15.7, "avg_hr": 131},
        {"distance_m": 600, "duration_s": 190, "pace": 5.27, "avg_hr": 157},
        {"distance_m": 13, "duration_s": 6, "pace": 6.9, "avg_hr": 169},
    ]

    fact = AIAnalysisWriter._executed_laps_fact(laps)

    assert "600m" in fact
    assert "; " not in fact  # só um bloco real (os 2 fantasmas caíram)


def test_facts_use_exact_block_comparison_when_present():
    """Quando o PlannedExecutionMatcher conseguiu casar com confiança, o
    fato já vem com o veredito CALCULADO -- não cai no texto cru de voltas
    (a IA não precisa mais fazer a conta sozinha)."""

    from app.domain.entities.block_comparison import (
        BlockComparison,
        ExecutedBlock,
    )

    comparison = BlockComparison(
        blocks=[
            ExecutedBlock(
                kind="interval", label="Tiro 1",
                planned_distance_m=600, planned_duration_sec=None,
                pace_min="5:15", pace_max="5:30",
                executed_distance_m=600, executed_duration_sec=190,
                executed_pace=5.27, executed_hr=157,
                within_target=True,
            ),
        ],
        missing=["Recuperação 1"],
    )

    executed = make_enriched_activity(
        activity=make_activity(raw={"_garmin_laps": [
            {"distance_m": 999, "duration_s": 1, "pace": 1, "avg_hr": 1},
        ]}),
    )

    facts = AIAnalysisWriter._facts(
        make_context(executed=executed, block_comparison=comparison)
    )

    assert "comparação EXATA, já calculada" in facts
    assert "Tiro 1" in facts
    assert "[dentro do alvo]" in facts
    assert "Não completou: Recuperação 1" in facts
    # não cai no texto cru de voltas (999m não devia aparecer)
    assert "999m" not in facts


def test_facts_include_executed_blocks_for_internal_plan():
    """A execução por bloco (voltas do Garmin) agora vai pra IA em QUALQUER
    plano, não só treinador externo — pra comparar bloco a bloco (tempo,
    progressivo, tiro...)."""

    executed = make_enriched_activity(
        activity=make_activity(
            raw={
                "_garmin_laps": [
                    {"distance_m": 600, "duration_s": 190,
                     "pace": 5.27, "avg_hr": 157},
                    {"distance_m": 400, "duration_s": 172,
                     "pace": 7.18, "avg_hr": 155},
                ]
            },
        ),
    )

    facts = AIAnalysisWriter._facts(make_context(executed=executed))

    assert "Execução por bloco" in facts
    assert "600m" in facts


def test_facts_flag_treadmill_when_indoor():

    executed = make_enriched_activity(indoor=True)

    facts = AIAnalysisWriter._facts(make_context(executed=executed))

    assert "ESTEIRA" in facts
    assert "AR LIVRE" not in facts


def test_mild_fade_fact_has_no_verdict():
    """Bug do Renato: 2ª metade ~5% mais lenta chegava pra IA como
    "apagou" e virava "você quebrou" na análise."""

    executed = make_enriched_activity(
        structure=_structure(
            is_interval=False,
            split_trend="positive_mild",
        ),
    )

    context = make_context(executed=executed)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(GEN_TEXT, new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    # o FATO é neutro ("variação normal"), não um veredito de quebra
    facts = prompt.split("REGRAS:")[0]

    assert "variação normal" in facts
    assert "apagou" not in facts
    assert "queda acentuada" not in facts


# ---- campos ricos do Garmin alimentando a IA (de acordo com o executado) ----

FULL_GARMIN = {
    "training_effect": 5.0, "training_effect_label": "LACTATE_THRESHOLD",
    "aerobic_effect_msg": "OVERREACHING_14",
    "anaerobic_effect": 0.0, "anaerobic_effect_msg": "NO_ANAEROBIC_BENEFIT_0",
    "workout_rpe": 50, "workout_feel": 75, "grade_adjusted_speed": 2.619,
    "ground_contact_ms": 284, "stride_length_cm": 97,
    "vertical_oscillation_cm": 8.7, "vertical_ratio": 9.0,
    "avg_power": 328, "normalized_power": 330, "max_power": 436,
    "body_battery_delta": -18, "vigorous_minutes": 76, "moderate_minutes": 1,
    "calories": 1176, "avg_temperature": 19.4, "max_temperature": 22,
}


def test_external_coach_prescription_from_notes_reaches_prompt():
    """Treinador externo guarda a prescrição em notes (siglas), structure
    vazio -> a IA precisa receber a prescrição E a legenda pra decodificar
    (senão analisa o fracionado do Mauricio às cegas, como 'rodagem')."""

    planned = make_planned_session(
        workout_type="Caminhada com corrida",
        notes="CCL 20' ritmo moderado + FF 25' (CCR3' + CAM2') + CAM 15'",
    )

    context = make_context(planned=planned)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(GEN_TEXT, new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    assert "Prescrição do treino:" in prompt
    assert "FF 25'" in prompt                  # a prescrição em si
    assert "Legenda das siglas" in prompt
    assert "FF = Forte e Fraco" in prompt       # a legenda decodifica


def test_executed_laps_fact_formats_and_skips_empty():

    laps = [
        {"distance_m": 548, "duration_s": 180, "pace": 5.47, "avg_hr": 144},
        {"distance_m": 0, "duration_s": 0, "pace": None, "avg_hr": None},
        {"distance_m": 311, "duration_s": 120, "pace": 6.44, "avg_hr": 141},
    ]

    fact = AIAnalysisWriter._executed_laps_fact(laps)

    assert "Execução por bloco" in fact
    assert "3'00 548m" in fact
    assert "2'00 311m" in fact
    assert fact.count(";") == 1          # só os 2 blocos válidos


def test_executed_laps_reach_prompt_for_external_coach():
    """Treinador externo: os blocos EXECUTADOS (voltas do Garmin) chegam ao
    prompt pra IA comparar com a estrutura prescrita — senão diz 'não fez o
    fracionado' quando o atleta FEZ (os km achatam a estrutura)."""

    planned = make_planned_session(
        notes="FF 25' (CCR3' ritmo moderado + CAM2' ritmo moderado)",
    )

    executed = make_enriched_activity(
        activity=make_activity(raw={"_garmin_laps": [
            {"distance_m": 548, "duration_s": 180, "pace": 5.47, "avg_hr": 144},
            {"distance_m": 311, "duration_s": 120, "pace": 6.44, "avg_hr": 141},
        ]}),
    )

    context = make_context(planned=planned, executed=executed)

    mock = AsyncMock(return_value='{"analysis": ["ok"]}')

    with patch(GEN_TEXT, new=mock):

        asyncio.run(AIAnalysisWriter.write(context))

    prompt = mock.await_args.kwargs["contents"]

    assert "Execução por bloco" in prompt
    assert "3'00 548m" in prompt


def test_garmin_facts_none_without_metrics():

    assert AIAnalysisWriter._garmin_facts(None) is None
    assert AIAnalysisWriter._garmin_facts({}) is None


def test_clean_msg_strips_garmin_code_suffix():

    assert AIAnalysisWriter._clean_msg("OVERREACHING_14") == "overreaching"
    assert AIAnalysisWriter._clean_msg("NO_ANAEROBIC_BENEFIT_0") == (
        "no anaerobic benefit"
    )
    assert AIAnalysisWriter._clean_msg(None) is None


def test_garmin_facts_render_everything_meaningful():

    facts = AIAnalysisWriter._garmin_facts(FULL_GARMIN)

    assert "efeito aeróbico 5.0/5 (LACTATE_THRESHOLD / overreaching)" in facts
    assert "efeito anaeróbico 0.0/5 (no anaerobic benefit)" in facts
    assert "esforço percebido (RPE) 5/10" in facts
    assert "sensação do atleta: bem" in facts
    assert "pace ajustado ao relevo" in facts
    assert "contato com o solo 284 ms" in facts
    assert "razão vertical 9.0%" in facts
    assert "potência média 328 W (normalizada 330 W, máx 436 W)" in facts
    assert "body battery -18" in facts
    assert "76 vigorosos + 1 moderados" in facts
    assert "1176 kcal" in facts
    assert "temperatura ~19°C (máx 22°C)" in facts


def test_garmin_facts_omit_absent_fields():

    facts = AIAnalysisWriter._garmin_facts(
        {"training_effect": 3.0, "workout_feel": 50}
    )

    assert "efeito aeróbico 3.0/5" in facts
    assert "sensação do atleta: normal" in facts
    assert "potência" not in facts
    assert "body battery" not in facts
    assert "dinâmica" not in facts
