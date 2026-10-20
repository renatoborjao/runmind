"""A higiene de TODA fala do coach (nº 73). A auditoria do resumo de domingo e do chat (18-20/10)
achou, na narrativa da semana e nas respostas, os vícios que a análise e o plano já não deixavam
passar: "cravando os 100%", "cravou o limiar" (na esteira, com pace estimado), "ACWR em 1.7",
"segurar a ansiedade" (que o atleta nunca disse), "cravar a tua inscrição". As mesmas regras agora
valem na leitura da semana e no chat — sem estragar a conversa: o que o ATLETA disse ele mesmo o
coach pode responder no termo dele, e as linhas, listas e emojis do WhatsApp ficam como estão."""

import asyncio
import json
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.application.coach.conversation.coach_brain import CoachBrain
from app.application.coach.conversation.coach_conversation_engine import (
    CoachConversationEngine,
)
from app.application.coach.writer.analysis_hygiene import (
    athlete_words,
    swap_tics,
    voice_text,
)
from app.application.coach.writer.coach_persona import COACH_VOICE
from app.application.review.weekly_review_builder import WeeklyReviewBuilder
from app.application.review.weekly_review_message_formatter import (
    WeeklyReviewMessageFormatter,
)
from app.application.review.weekly_review_narrative_writer import (
    WeeklyReviewNarrativeWriter,
)
from app.domain.entities.training_history import TrainingHistory
from tests.coach.factories import make_activity, make_runner

ENGINE = "app.application.coach.conversation.coach_conversation_engine"
BRAIN = "app.application.coach.conversation.coach_brain"
WRITER = "app.application.review.weekly_review_narrative_writer"


# --- o filtro ---------------------------------------------------------------------------------


def test_the_real_phrases_of_the_audit_lose_the_tics():

    assert voice_text(
        "Mauricio, fechamos uma semana excelente, cravando os 100% de aderência."
    ) == "Mauricio, fechamos uma semana excelente, mantendo os 100% de aderência."

    assert "cravou" not in voice_text("Fer, você cravou o limiar na esteira a 5:36/km.")


def test_crav_ar_the_registration_means_closing_it_not_keeping_it():
    """"Cravar a tua inscrição" é fechar a inscrição — a troca cega diria "manter"."""

    assert voice_text("Bora cravar a tua inscrição hoje.") == "Bora fechar a tua inscrição hoje."

    assert swap_tics("Cravou a vaga!") == "Fechou a vaga!"


def test_load_jargon_leaves_the_voice_but_the_numbers_stay():

    text = voice_text(
        "Você fez 47, 32, 39 e 43 km nas últimas semanas. A carga disparou, elevando o risco "
        "de lesão com ACWR em 1.7. Segue firme no plano."
    )

    assert "ACWR" not in text
    assert "47, 32, 39 e 43 km" in text
    assert "Segue firme no plano." in text


def test_an_invented_inner_state_is_dropped():
    """Renato2 18/10: "segurar a ansiedade" — ele nunca disse que estava ansioso."""

    text = voice_text(
        "Sua prioridade é rodar o leve no ritmo planejado. Segure a ansiedade e a empolgação."
    )

    assert "ansiedade" not in text and "empolgação" not in text
    assert text == "Sua prioridade é rodar o leve no ritmo planejado."


def test_what_the_athlete_said_himself_can_be_answered_in_his_own_terms():

    said = athlete_words(
        [
            {"role": "user", "text": "tô muito ansioso pra prova"},
            {"role": "assistant", "text": "ok"},
        ],
        "e agora?",
    )

    assert "ansioso" in said and "ok" not in said

    reply = "Normal sentir ansiedade antes da prova. Bora manter o plano."

    assert voice_text(reply, athlete_said=said) == reply

    # sem ele ter dito, a frase sai
    assert voice_text(reply) == "Bora manter o plano."

    # e se ELE perguntou da sigla, ela pode ser respondida
    asked = "qual o meu ACWR?"

    answer = "Seu ACWR está em 1.1, na faixa boa. Segue o plano da semana."

    assert "ACWR" in voice_text(answer, athlete_said=asked)
    assert voice_text(answer) == "Segue o plano da semana."


def test_no_heart_rate_for_whoever_runs_without_a_monitor():

    text = voice_text(
        "Você fez 5 km em 28:00 no pace médio de 5:36/km e frequência cardíaca na Z4.",
        has_hr=False,
    )

    assert "frequência" not in text and "Z4" not in text
    assert "5:36/km" in text

    assert "Z4" in voice_text("Rodou na Z4 o tempo todo.", has_hr=True)


def test_the_chat_layout_survives():
    """Linhas, listas "•", linhas em branco, emoji e *negrito* do WhatsApp ficam como estão."""

    reply = (
        "*Plano da semana* 💪\n"
        "\n"
        "• Terça: 8 km leve (6:30-6:50/km)\n"
        "• Quinta: 6x 800 m (4:50-5:00/km)\n"
        "\n"
        "Bora?"
    )

    assert voice_text(reply) == reply


def test_a_dirty_bullet_is_cleaned_in_place_and_keeps_its_marker():

    reply = "• Terça: crave o ritmo\n• Quinta: 8 km leve"

    assert voice_text(reply) == "• Terça: mantenha o ritmo\n• Quinta: 8 km leve"


def test_a_voice_is_never_emptied():

    assert voice_text("Segure a ansiedade.") != ""
    assert voice_text("") == "" and voice_text(None) == ""


# --- o chat -----------------------------------------------------------------------------------


def test_the_chat_reply_goes_through_the_hygiene():

    with patch(f"{ENGINE}.generate_text") as generate:

        generate.return_value = "Show! Dá pra cravar a tua inscrição hoje, Renato."

        reply = asyncio.run(
            CoachConversationEngine.reply(
                runner_name="Renato",
                context_facts="",
                conversation_history=[],
                incoming_text="posso me inscrever?",
            )
        )

    assert reply == "Show! Dá pra fechar a tua inscrição hoje, Renato."


def test_the_chat_lets_the_coach_echo_the_athletes_own_words():

    with patch(f"{ENGINE}.generate_text") as generate:

        generate.return_value = "Entendo a ansiedade, é normal antes da prova."

        reply = asyncio.run(
            CoachConversationEngine.reply(
                runner_name="Renato",
                context_facts="",
                conversation_history=[],
                incoming_text="tô com uma ansiedade enorme",
            )
        )

    assert "ansiedade" in reply


def test_the_brain_voice_is_cleaned_but_the_decision_is_untouched():

    raw = json.dumps(
        {
            "say": "Beleza! Segure a empolgação e rode o leve de verdade.",
            "answer_card": "weekly_plan",
            "cobranca": "Leve saindo forte, com ACWR em 1.7 e muita empolgação.",
        }
    )

    with patch(f"{BRAIN}.generate_json", new=AsyncMock(side_effect=_parse_with(raw))):

        decision = asyncio.run(
            CoachBrain.decide(
                runner_name="Renato",
                context_facts="",
                incoming_text="e o plano?",
            )
        )

    assert "empolgação" not in decision.say and "Beleza!" in decision.say
    assert decision.answer_card == "weekly_plan"
    assert "ACWR" not in (decision.cobranca or "") and "empolgação" not in (decision.cobranca or "")


def _parse_with(raw: str):

    async def run(**kwargs):

        return kwargs["parse"](raw)

    return run


def test_the_voice_rules_are_in_the_shared_persona():

    for rule in (
        "LINGUAGEM QUE VOCÊ NÃO USA",
        "Muleta de torcida",
        "Garantia que o dado não dá",
        "Mecanismo do corpo sem lastro",
        "Sigla de métrica interna",
        "Promessa sobre o sistema",
        "Corrida na ESTEIRA",
    ):

        assert rule in COACH_VOICE

    # entra como valor num .format() de prompt: sem chaves
    assert "{" not in COACH_VOICE and "}" not in COACH_VOICE


# --- a leitura da semana ------------------------------------------------------------------------


def _review(**extra) -> dict:

    review = {
        "comparison": {
            "current_week": {"runs": 3, "distance_km": 30.4, "avg_pace_min_km": 5.9},
            "previous_week": {"runs": 1, "distance_km": 4.1, "avg_pace_min_km": 5.8},
            "delta": {"volume_delta_percent": 641.5, "distance_km": 26.3, "runs": 2},
            "week_start": "2026-10-12",
        },
        "week_start": "2026-10-12",
        "trends": {},
        "goal": {},
        "adherence": {"planned": 3, "done": 3},
        "longest_km": 11.5,
    }

    review.update(extra)

    return review


def test_the_week_narrative_goes_through_the_hygiene_before_it_is_recorded():

    raw = json.dumps(
        {
            "reading": [
                "Fer, você cravou o limiar e fechou 30.4 km na semana.",
                "A carga disparou com ACWR em 1.7, elevando o risco de lesão.",
            ],
            "attention": "Segure a ansiedade e rode o leve no ritmo planejado.",
        }
    )

    with (
        patch(f"{WRITER}.generate_json", new=AsyncMock(side_effect=_parse_with_writer(raw))),
        patch(
            "app.infrastructure.persistence.coach_attention_log.CoachAttentionLog.record"
        ) as record,
    ):

        lines = asyncio.run(WeeklyReviewNarrativeWriter.write("Fernanda", _review(), profile=None))

    text = " ".join(lines)

    assert "cravou" not in text and "ACWR" not in text and "ansiedade" not in text
    assert "30.4 km" in text
    assert "Rode o leve no ritmo planejado" in text
    record.assert_not_called()


def _parse_with_writer(raw: str):

    async def run(**kwargs):

        return kwargs["parse"](raw)

    return run


def test_the_week_narrative_records_the_clean_attention():

    raw = json.dumps(
        {"reading": ["Semana firme, 30.4 km."], "attention": "Crave o leve no ritmo planejado."}
    )

    with (
        patch(f"{WRITER}.generate_json", new=AsyncMock(side_effect=_parse_with_writer(raw))),
        patch(
            "app.infrastructure.persistence.coach_attention_log.CoachAttentionLog.record"
        ) as record,
        patch(f"{WRITER}.WeeklyReviewNarrativeWriter._facts", return_value="fatos"),
    ):

        asyncio.run(WeeklyReviewNarrativeWriter.write("Fernanda", _review(), profile="fernanda"))

    assert record.call_args.args[2] == "Mantenha o leve no ritmo planejado."


def test_the_week_narrative_knows_when_the_athlete_has_no_heart_rate():

    raw = json.dumps(
        {
            "reading": [
                "Você correu 20 km no ritmo planejado.",
                "A frequência cardíaca média ficou em 150 bpm na semana.",
            ]
        }
    )

    with patch(f"{WRITER}.generate_json", new=AsyncMock(side_effect=_parse_with_writer(raw))):

        lines = asyncio.run(
            WeeklyReviewNarrativeWriter.write("Hélio", _review(has_hr=False), profile=None)
        )

    assert lines == ["Você correu 20 km no ritmo planejado."]


def test_the_facts_flag_the_treadmill_and_the_break_week():

    facts = WeeklyReviewNarrativeWriter._facts(
        "Fernanda",
        _review(
            previous_week_break=True,
            indoor_runs=[{"day": "16/10", "km": 5.4}],
        ),
    )

    assert "ESTEIRA" in facts and "16/10 (5.4 km)" in facts and "ESTIMADOS" in facts
    assert "RECESSO" in facts and "NÃO um salto de carga" in facts
    assert "+641" not in facts


# --- o recesso e a esteira nos números -----------------------------------------------------------

MONDAY = datetime(2026, 10, 12, 7, 0, 0)

REFERENCE = date(2026, 10, 18)


def _week(weeks_ago: int, km: float, **extra):

    return make_activity(
        id=int(weeks_ago * 100 + km),
        start_date=MONDAY - timedelta(weeks=weeks_ago),
        distance=km * 1000,
        moving_time=int(km * 330),
        **extra,
    )


def _build(history_weeks: dict[int, float], **extra):

    activities = [_week(weeks, km, **extra) for weeks, km in history_weeks.items()]

    return WeeklyReviewBuilder.build(
        make_runner(), TrainingHistory(activities=activities), reference_date=REFERENCE,
    )


def test_a_week_after_a_break_is_flagged_and_the_percent_is_not_shown():
    """Fernanda: 4,1 km na semana anterior depois de semanas de ~28-30 km."""

    review = _build({0: 30.4, 1: 4.1, 2: 28.0, 3: 30.0, 4: 27.0, 5: 29.0})

    assert review["previous_week_break"] is True

    line = WeeklyReviewMessageFormatter._volume_line(
        review["comparison"]["current_week"],
        review["comparison"]["previous_week"],
        review["comparison"]["delta"],
        previous_break=review["previous_week_break"],
    )

    assert line == "• Volume: 30.4 km (4.1 km na anterior, semana de recesso)"
    assert "%" not in line


def test_a_normal_week_keeps_its_percent():

    review = _build({0: 32.0, 1: 28.0, 2: 27.0, 3: 30.0, 4: 26.0, 5: 29.0})

    assert review["previous_week_break"] is False

    line = WeeklyReviewMessageFormatter._volume_line(
        review["comparison"]["current_week"],
        review["comparison"]["previous_week"],
        review["comparison"]["delta"],
    )

    assert line.endswith("(28.0 km na anterior, +14.3%)")


def test_no_baseline_means_no_break():
    """Quem está começando (menos de 2 semanas de corrida antes) não tem "normal" pra recesso."""

    assert _build({0: 12.0, 1: 3.0})["previous_week_break"] is False

    assert _build({0: 12.0, 1: 3.0, 2: 9.0})["previous_week_break"] is False


def test_the_treadmill_runs_of_the_week_are_listed():

    activities = [
        _week(0, 5.4, raw={"trainer": True}),
        _week(1, 10.0),
    ]

    review = WeeklyReviewBuilder.build(
        make_runner(), TrainingHistory(activities=activities), reference_date=REFERENCE,
    )

    assert review["indoor_runs"] == [{"day": "12/10", "km": 5.4}]


def test_has_hr_follows_the_week():

    with_hr = _build({0: 10.0, 1: 8.0})

    assert with_hr["has_hr"] is True

    without = WeeklyReviewBuilder.build(
        make_runner(),
        TrainingHistory(activities=[_week(0, 10.0, average_heartrate=None)]),
        reference_date=REFERENCE,
    )

    assert without["has_hr"] is False


# --- a esteira sobrevive ao arquivo ---------------------------------------------------------------


def test_the_archive_keeps_the_treadmill_flag_and_a_plain_rewrite_does_not_erase_it(tmp_path):
    """O arquivo reduzido guardava tudo MENOS a esteira: lido de volta, a corrida de esteira
    virava "corrida normal" e a leitura da semana provava ritmo com um pace estimado."""

    from app.infrastructure.persistence.activity_archive_repository import (
        ActivityArchiveRepository,
    )

    repo = ActivityArchiveRepository()
    repo.storage = tmp_path

    repo.upsert_many("f", [_week(0, 5.4, raw={"trainer": True}), _week(1, 10.0)])

    by_km = {round(a.distance / 1000, 1): a for a in repo.load_activities("f")}

    assert by_km[5.4].raw.get("trainer") is True
    assert not by_km[10.0].raw.get("trainer")

    # a MESMA corrida regravada por uma fonte sem a marca (lista do Strava) não apaga a esteira
    repo.upsert_many("f", [_week(0, 5.4)])

    again = {round(a.distance / 1000, 1): a for a in repo.load_activities("f")}

    assert again[5.4].raw.get("trainer") is True
