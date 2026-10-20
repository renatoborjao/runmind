"""A ANÁLISE DE TREINO é o coração do produto (Renato, 20/10). Auditoria das 9 análises reais das
últimas 72 h achou 6 com defeito de VERDADE — o coach afirmou o que não sabia ou leu o dado
errado. Cada teste aqui nasce de uma mensagem real:

- Hélio (sem relógio, 0 de 92 corridas com FC): "frequência cardíaca na Z4" e "manter a
  frequência abaixo de 141 bpm" — a zona vinha estimada do PACE, o teto da idade.
- Fernanda 16/10 (esteira): "cravou o ritmo de limiar" com FC 110, esforço 2/10 e parciais que
  não fecham com a média.
- Leonardo 19/10 (rodagem com acelerações): "5 tiros · pace médio 5:17" com "Tiro 1: 5000 m" e
  "Pausa 4: 488 m ⚠️" (a última volta absorveu o desaquecimento).
- Hélio: "carga aguda subindo para 1.48" (jargão) e "pela quinta/sexta vez recente" (bronca que
  conta vezes sem datas e se repete a cada corrida)."""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.application.coach.writer.ai_analysis_writer import (
    PROMPT_TEMPLATE,
    AIAnalysis,
    AIAnalysisWriter,
)
from app.application.coach.writer.analysis_hygiene import (
    clean_text,
    sanitize,
    strip_repeat_counts,
)
from app.application.history.planned_execution_matcher import PlannedExecutionMatcher
from app.domain.entities.workout_step import INTERVAL, RECOVERY, RUN, WorkoutStep
from app.domain.entities.workout_structure import WorkoutStructure
from app.infrastructure.integrations.garmin.garmin_activity_source import (
    GarminActivitySource,
    _drop_oversized_efforts,
)
from tests.coach.factories import (
    make_activity,
    make_context,
    make_enriched_activity,
    make_planned_session,
)

DOSSIER = "app.application.coach.context.athlete_dossier.AthleteDossier.render"
DAY_CONTEXT = "app.application.coach.context.day_context_reader.DayContextReader.facts"


# ---- sem FC: nada de frequência cardíaca pra quem não tem ------------------------------------


def test_the_real_helio_sentences_lose_the_heart_rate_but_keep_the_truth():

    pace = (
        "A orientação era recuperar entre 6:45 e 7:15/km, mas você fez 6 km com pace médio "
        "de 5:40/km e frequência cardíaca na Z4."
    )

    assert clean_text(pace, has_hr=False) == (
        "A orientação era recuperar entre 6:45 e 7:15/km, mas você fez 6 km com pace médio "
        "de 5:40/km."
    )

    next_step = (
        "Na quarta-feira, na rodagem com acelerações, trave o ritmo dos 5 km base "
        "rigorosamente entre 6:45 e 7:15/km para manter a frequência abaixo de 141 bpm."
    )

    assert clean_text(next_step, has_hr=False) == (
        "Na quarta-feira, na rodagem com acelerações, trave o ritmo dos 5 km base "
        "rigorosamente entre 6:45 e 7:15/km."
    )


def test_a_sentence_that_is_only_heart_rate_is_dropped():

    text = "A frequência cardíaca ficou em 124 bpm, com 94% do tempo na Z2 de recuperação."

    assert clean_text(text, has_hr=False) is None
    # quem TEM FC mantém tudo
    assert clean_text(text, has_hr=True) == text


def test_a_fragment_is_never_left_behind():
    """Sobrar só "Rodar 2 km a mais." de uma frase longa vira nada, não fragmento."""

    text = (
        "Rodar 2 km a mais e num ritmo moderado em Z3 gera um desgaste acumulado que "
        "prejudica sua recuperação."
    )

    assert clean_text(text, has_hr=False) is None


def test_zone_terms_and_the_aerobic_ceiling_count_as_heart_rate():

    for text in (
        "Você ficou na Z3 quase todo o tempo.",
        "Respeite o teto aeróbico de 141 durante a rodagem leve.",
        "A zona 4 pesou no fim do treino, e isso cobra a conta.",
    ):

        assert clean_text(text, has_hr=False) is None


# ---- jargão de carga -------------------------------------------------------------------------


def test_the_load_jargon_never_reaches_the_athlete_even_with_heart_rate():

    text = (
        "Com a carga aguda subindo para 1.48, o corpo pede cautela nesta semana. "
        "Segure o ritmo na faixa leve."
    )

    assert clean_text(text, has_hr=True) == (
        "O corpo pede cautela nesta semana. Segure o ritmo na faixa leve."
    )

    for term in ("ACWR 1.4", "a carga crônica caiu", "STRAINED", "razão aguda:crônica alta"):

        cleaned = clean_text(f"Hoje {term} e o treino mudou bastante.", has_hr=True)

        assert cleaned is None or term not in cleaned


# ---- contar vezes ----------------------------------------------------------------------------


def test_counting_times_without_dates_is_stripped_but_the_message_stays():

    assert strip_repeat_counts(
        "Pela quinta vez recente você passou do combinado no volume e na intensidade."
    ) == "Você passou do combinado no volume e na intensidade."

    assert clean_text(
        "É a sexta vez recente que você passa do combinado em intensidade e volume "
        "nos dias leves.",
        has_hr=True,
    ) == "Você passa do combinado em intensidade e volume nos dias leves."

    # sem contagem, nada muda
    plain = "Você passou do combinado hoje."

    assert strip_repeat_counts(plain) == plain


# ---- a análise inteira -----------------------------------------------------------------------


def _analysis(**kw) -> AIAnalysis:

    base = dict(
        headline="Hélio, você voltou a acelerar num dia leve.",
        analysis=[
            "Você fez 6 km com pace médio de 5:40/km e frequência cardíaca na Z4.",
            "A frequência cardíaca ficou em 160 bpm, com 80% do tempo na Z4.",
        ],
        attention="Pela sexta vez recente você passou do combinado nos dias leves.",
        next_step=(
            "Na quarta, trave o ritmo dos 5 km entre 6:45 e 7:15/km para manter a "
            "frequência abaixo de 141 bpm."
        ),
    )

    base.update(kw)

    return AIAnalysis(**base)


def test_sanitize_cleans_every_field_for_an_athlete_without_heart_rate():

    clean = sanitize(_analysis(), has_hr=False)

    assert clean.analysis == ["Você fez 6 km com pace médio de 5:40/km."]
    assert clean.attention == "Você passou do combinado nos dias leves."
    assert clean.next_step == "Na quarta, trave o ritmo dos 5 km entre 6:45 e 7:15/km."
    assert "frequência" not in " ".join(clean.analysis + [clean.attention, clean.next_step])


def test_an_athlete_with_heart_rate_keeps_it():

    clean = sanitize(_analysis(), has_hr=True)

    assert "Z4" in clean.analysis[0] and "160 bpm" in clean.analysis[1]
    assert "141 bpm" in clean.next_step
    # mas a contagem sem datas sai pra todos
    assert clean.attention == "Você passou do combinado nos dias leves."


def test_when_nothing_true_is_left_the_analysis_falls_back():

    only_hr = _analysis(analysis=["A frequência cardíaca ficou em 160 bpm, na Z4."])

    assert sanitize(only_hr, has_hr=False) is None


def _write(analysis, executed_hr):

    context = SimpleNamespace(
        executed=SimpleNamespace(activity=SimpleNamespace(average_heartrate=executed_hr)),
    )

    with (
        patch.object(AIAnalysisWriter, "_facts", return_value="fatos"),
        patch(
            "app.application.coach.writer.ai_analysis_writer.generate_json",
            new=AsyncMock(return_value=analysis),
        ),
    ):

        return asyncio.run(AIAnalysisWriter.write(context))


def test_the_writer_applies_the_hygiene_to_what_the_model_wrote():

    without = _write(_analysis(), executed_hr=None)
    with_hr = _write(_analysis(), executed_hr=155)

    assert "Z4" not in " ".join(without.analysis)
    assert any("Z4" in line for line in with_hr.analysis)
    assert _write(None, executed_hr=None) is None


# ---- os fatos: sem FC e esteira --------------------------------------------------------------


def _facts(activity=None, executed=None, planned=None):

    activity = activity or make_activity(average_heartrate=None, max_heartrate=None)

    executed = executed or make_enriched_activity(activity=activity)

    with patch(DOSSIER, return_value=""), patch(DAY_CONTEXT, return_value=""):

        return AIAnalysisWriter._facts(make_context(executed=executed, planned=planned))


def test_without_heart_rate_the_facts_say_so_and_drop_the_pace_estimated_zone():
    """O enricher estima a "zona" pelo PACE; rotulá-la "FC média na zona" fazia a IA citar
    frequência cardíaca de quem corre sem monitor."""

    executed = make_enriched_activity(
        activity=make_activity(average_heartrate=None, max_heartrate=None),
        estimated_zone="Z4", intensity="HIGH",
    )

    facts = _facts(executed=executed)

    assert "SEM FC: este treino NÃO tem frequência cardíaca" in facts
    assert "FC média na zona" not in facts
    assert "NÃO cite FC, bpm, zonas (Z1–Z5) nem teto aeróbico" in facts


def test_with_heart_rate_the_zone_and_the_bpm_stay():

    executed = make_enriched_activity(
        activity=make_activity(average_heartrate=156.0, max_heartrate=177.0),
        estimated_zone="Z4",
    )

    facts = _facts(executed=executed)

    assert "FC média na zona Z4" in facts
    assert "FC média 156, máx 177 bpm" in facts
    assert "SEM FC" not in facts


def test_the_treadmill_pace_is_labeled_as_an_estimate():

    executed = make_enriched_activity(
        activity=make_activity(average_heartrate=110.0), indoor=True,
    )

    facts = _facts(executed=executed)

    assert "Ambiente: ESTEIRA — distância e pace são ESTIMADOS pelo relógio" in facts
    assert "NÃO elogie nem cobre cumprimento de pace/distância" in facts
    assert "(ESTIMADO pela esteira)" in facts
    assert "NÃO cite desacoplamento" in facts


def test_a_treadmill_pace_that_does_not_close_with_the_splits_is_flagged():
    """Fernanda 16/10: média 5:36 com parciais 6:37 · 6:38 · 6:07 · 5:47."""

    structure = WorkoutStructure(
        km_splits=[6.62, 6.63, 6.12, 5.78], km_hr=[131, 98, 102, 105], lap_count=0,
        lap_paces=[], fastest_km_pace=5.78, slowest_km_pace=6.63, pace_spread=0.1,
        split_trend="negative", is_interval=False, cadence_spm=161, hr_avg=110,
        hr_max=142, has_detail=True,
    )

    executed = make_enriched_activity(
        activity=make_activity(average_heartrate=110.0), indoor=True,
        pace_min_km=5.6, structure=structure,
    )

    facts = _facts(executed=executed)

    assert "DADO DE ESTEIRA INCONSISTENTE" in facts
    assert "NÃO cite pace como cumprido" in facts

    # parciais que fecham com a média: sem aviso
    consistent = make_enriched_activity(
        activity=make_activity(average_heartrate=110.0), indoor=True,
        pace_min_km=6.3, structure=structure,
    )

    assert "INCONSISTENTE" not in _facts(executed=consistent)


def test_the_decoupling_never_comes_from_an_estimated_treadmill_pace_or_a_run_without_hr():

    planned = make_planned_session(workout_type="Rodagem Leve")

    structure = WorkoutStructure(
        km_splits=[6.0, 6.0, 6.2, 6.4], km_hr=[130, 132, 136, 140], lap_count=0,
        lap_paces=[], fastest_km_pace=6.0, slowest_km_pace=6.4, pace_spread=0.1,
        split_trend="positive_mild", is_interval=False, cadence_spm=170, hr_avg=135,
        hr_max=150, has_detail=True,
    )

    outdoor = _facts(
        executed=make_enriched_activity(
            activity=make_activity(average_heartrate=135.0), structure=structure,
        ),
        planned=planned,
    )

    treadmill = _facts(
        executed=make_enriched_activity(
            activity=make_activity(average_heartrate=135.0), structure=structure, indoor=True,
        ),
        planned=planned,
    )

    assert "Desacoplamento FC×pace" in outdoor
    assert "Desacoplamento FC×pace (1ª × 2ª metade)" not in treadmill


# ---- o prompt --------------------------------------------------------------------------------


def test_the_prompt_teaches_the_new_rules():

    assert "SEM FC:" in PROMPT_TEMPLATE
    assert "ESTEIRA: o pace/distância são estimados" in PROMPT_TEMPLATE
    assert "CAUSA SÓ COM LASTRO" in PROMPT_TEMPLATE
    assert "NÃO CONTE VEZES" in PROMPT_TEMPLATE
    assert "NUNCA mande \"recuperar\"/\"compensar\" volume que faltou" in PROMPT_TEMPLATE
    assert "cravou/cravada/cravado" in PROMPT_TEMPLATE


# ---- tiros: a base contínua não é tiro -------------------------------------------------------


def _leonardo_typed():
    """Rodagem com acelerações (19/10): 5 km de base + 4 acelerações de ~20 s com pausas."""

    def split(kind, distance, speed, hr):

        return {"type": kind, "distance": distance, "averageSpeed": speed,
                "averageHR": hr, "maxHR": hr + 6}

    return {
        "splits": [
            split("INTERVAL_ACTIVE", 5000, 2.24, 127),     # a BASE, rotulada como esforço
            split("INTERVAL_ACTIVE", 63, 3.13, 132),
            split("INTERVAL_RECOVERY", 81, 2.02, 129),
            split("INTERVAL_ACTIVE", 70, 3.51, 122),
            split("INTERVAL_RECOVERY", 76, 1.91, 127),
            split("INTERVAL_ACTIVE", 73, 3.66, 126),
            split("INTERVAL_RECOVERY", 82, 2.04, 132),
            split("INTERVAL_ACTIVE", 77, 3.85, 127),
            split("INTERVAL_RECOVERY", 488, 2.30, 135),
        ]
    }


def test_the_continuous_base_is_not_counted_as_a_rep():

    interval = GarminActivitySource._exact_interval(_leonardo_typed())

    assert interval is not None
    assert interval.rep_count == 4
    assert [rep["distance_m"] for rep in interval.reps] == [63, 70, 73, 77]
    # o pace médio dos tiros é o das acelerações (~4:30), não 5:17 puxado pelos 5 km
    assert interval.avg_rep_pace < 4.9


def test_real_interval_shapes_are_untouched_by_the_size_filter():

    def reps(distances):

        return [{"distance_m": d, "pace": 4.5, "peak_hr": 170, "_speed": 3.7} for d in distances]

    for shape in (
        [800] * 6,                       # 6x800
        [200, 400, 600, 800, 600, 400, 200],   # pirâmide: 4×
        [1600, 1200, 800, 400],          # Michigan
        [400, 400],                      # só 2: sem mediana que sustente
    ):

        assert len(_drop_oversized_efforts(reps(shape))) == len(shape)

    # nunca deixa < 2
    assert len(_drop_oversized_efforts(reps([5000, 60, 70]))) == 2


# ---- blocos: a última volta absorve o resto do treino ----------------------------------------


def _strides_session():

    strides = WorkoutStep(
        kind="repeat", reps=2,
        steps=[
            WorkoutStep(kind=INTERVAL, duration_sec=20),
            WorkoutStep(kind=RECOVERY, duration_sec=40),
        ],
    )

    return make_planned_session(
        workout_type="Rodagem com acelerações",
        steps=[WorkoutStep(kind=RUN, distance_m=5000, pace_min="7:05", pace_max="7:35"), strides],
    )


def _block(kind, distance, duration, pace, hr=130):

    return {
        "kind": kind, "distance_m": distance, "duration_s": duration, "pace": pace,
        "avg_hr": hr,
    }


def test_the_last_pause_lap_that_absorbed_the_cooldown_has_no_verdict():
    """"Pausa 4: 488 m, alvo 0:40 ⚠️" — o relógio não fechou a volta; não é pausa longa demais."""

    activity = make_activity(raw={"_garmin_typed_blocks": [
        _block("other", 5000, 2240, 7.4),
        _block("effort", 63, 20, 5.3),
        _block("recovery", 81, 40, 8.2),
        _block("effort", 70, 20, 4.7),
        _block("recovery", 488, 210, 7.2),      # a ÚLTIMA volta: absorveu o desaquecimento
    ]})

    comparison = PlannedExecutionMatcher.match(_strides_session(), activity)

    last = comparison.blocks[-1]

    assert last.kind == RECOVERY
    assert last.within_target is None


def test_a_long_pause_in_the_middle_is_still_a_miss():

    activity = make_activity(raw={"_garmin_typed_blocks": [
        _block("other", 5000, 2240, 7.4),
        _block("effort", 63, 20, 5.3),
        _block("recovery", 400, 190, 7.5),      # pausa de 3 min NO MEIO: não é a última volta
        _block("effort", 70, 20, 4.7),
        _block("recovery", 80, 40, 8.2),
    ]})

    comparison = PlannedExecutionMatcher.match(_strides_session(), activity)

    middle = comparison.blocks[2]

    assert middle.kind == RECOVERY
    assert middle.within_target is False
    # e a última, dentro do tempo, segue com veredito normal
    assert comparison.blocks[-1].within_target is True


# ---- tique de linguagem ("cravou") ----------------------------------------------------------


def test_the_cravou_tic_becomes_plain_words():
    """"Ritmo e acelerações cravados dentro do alvo" voltou na checagem com o modelo real."""

    assert clean_text(
        "Excelente execução: ritmo e acelerações cravados dentro do alvo.", has_hr=True,
    ) == "Excelente execução: ritmo e acelerações firmes dentro do alvo."

    assert clean_text("Você cravou o tempo do bloco.", has_hr=True) == (
        "Você fechou o tempo do bloco."
    )
    assert clean_text("Cravou a base em 7:26/km.", has_hr=True) == "Fechou a base em 7:26/km."
    assert clean_text("A FC média ficou cravada em 124 bpm.", has_hr=True) == (
        "A FC média ficou firme em 124 bpm."
    )
    assert clean_text("Tente cravar o pace nos tiros.", has_hr=True) == (
        "Tente manter o pace nos tiros."
    )
    # o que não é a muleta fica
    assert clean_text("Você cravou? Não: a regra é crave.", has_hr=True).count("crave") == 1


# ---- estado interno inventado ("segure a ansiedade") -------------------------------------


def test_an_invented_inner_state_is_dropped_from_the_next_step():
    """Leonardo 19/10: "segure a ansiedade nos primeiros tiros" — ele nunca disse que estava
    ansioso (a voz do coach proíbe; o modelo escorrega)."""

    text = (
        "Na sexta-feira, o desafio é no treino de VO2 (6x 400m de 5:40 a 5:55/km): segure a "
        "ansiedade nos primeiros tiros para não estourar antes da metade do treino."
    )

    cleaned = clean_text(text, has_hr=True)

    assert "ansiedade" not in cleaned
    assert cleaned.startswith("Na sexta-feira, o desafio é no treino de VO2")


# ---- o que você já cobrou ------------------------------------------------------------------

OUTBOX = (
    "app.infrastructure.persistence.coach_outbox_repository.CoachOutboxRepository.recent"
)
TODAY = "app.application.coach.writer.ai_analysis_writer.today_local"


def _entry(day, attention):

    return {
        "timestamp": f"2026-10-{day}T18:26:21+00:00",
        "text": (
            "🏃 Ritmind\n\nHélio, ...\n\n📊 Análise\n• algo\n\n⚠️ Ponto de atenção\n"
            f"• {attention}\n\n🎯 Próximo treino\n• Dia: quarta-feira"
        ),
    }


def test_the_analysis_is_told_what_the_coach_already_charged_with_the_dates():

    entries = [
        _entry("17", "Pela quinta vez recente você passou do combinado."),
        {"timestamp": "2026-10-18T10:00:00+00:00", "text": "Bom dia, Hélio! Hoje é treino."},
        _entry("19", "É a sexta vez recente que você passa do combinado nos dias leves."),
    ]

    with patch(OUTBOX, return_value=entries), patch(TODAY, return_value=date(2026, 10, 20)):

        fact = AIAnalysisWriter._previous_attentions_fact("helio")

    assert fact.startswith(
        "PONTOS DE ATENÇÃO que você JÁ deu nas últimas análises (17/10: Pela quinta"
    )
    assert "19/10: É a sexta vez recente" in fact
    assert "NÃO o repita nem conte as vezes" in fact
    assert 'deixe "attention" null' in fact
    # só o bloco do ponto de atenção — nem o próximo treino nem a análise
    assert "quarta-feira" not in fact and "algo" not in fact


def test_old_attentions_and_failures_say_nothing():

    old = [_entry("01", "Algo de setembro.")]

    with patch(OUTBOX, return_value=old), patch(TODAY, return_value=date(2026, 10, 20)):

        assert AIAnalysisWriter._previous_attentions_fact("helio") is None

    with patch(OUTBOX, side_effect=OSError("disco")):

        assert AIAnalysisWriter._previous_attentions_fact("helio") is None


def test_the_facts_carry_the_previous_attentions_and_the_sleep_rule_is_in_the_prompt():

    with patch.object(
        AIAnalysisWriter, "_previous_attentions_fact",
        return_value="PONTOS DE ATENÇÃO que você JÁ deu (17/10: x).",
    ):

        facts = _facts()

    assert "PONTOS DE ATENÇÃO que você JÁ deu (17/10: x)." in facts
    assert "o SONO (curto OU longo)" in PROMPT_TEMPLATE
    assert "nem culpe a noite curta nem premie a noite boa" in PROMPT_TEMPLATE
