from app.application.onboarding.deterministic_onboarding_parser import (
    DeterministicOnboardingParser,
)

parse = DeterministicOnboardingParser.parse


# ==========================================================
# Sim / Não (Strava, treinador, confirmação)
# ==========================================================

def test_yes_variants_resolve_to_true():

    for answer in ("sim", "Sim!", "já tenho", "claro que sim", "tenho conta"):

        assert parse("ASK_STRAVA", answer) == {"has_strava": True}, answer


def test_no_variants_resolve_to_false():

    for answer in ("não", "nao", "n", "ainda não", "não tenho"):

        assert parse("ASK_STRAVA", answer) == {"has_strava": False}, answer


def test_negation_beats_contained_affirmation():

    # "não tenho" contém "tenho", mas a negação tem prioridade
    assert parse("ASK_COACH", "não tenho treinador") == {"has_coach": False}


def test_ambiguous_yes_no_defers_to_gemini():

    assert parse("ASK_STRAVA", "sei lá, talvez") is None


def test_confirm_maps_to_confirmed_key():

    assert parse("CONFIRM", "pode sim") == {"confirmed": True}
    assert parse("CONFIRM", "não, deixa pra lá") == {"confirmed": False}


# ==========================================================
# Nome
# ==========================================================

def test_plain_name():

    assert parse("ASK_NAME", "Renato") == {"name": "Renato"}


def test_name_with_filler_prefix():

    assert parse("ASK_NAME", "meu nome é Renato") == {"name": "Renato"}
    assert parse("ASK_NAME", "pode me chamar de Rê") == {"name": "Rê"}
    assert parse("ASK_NAME", "sou o João Pedro") == {"name": "João Pedro"}


def test_long_sentence_name_defers_to_gemini():

    assert parse("ASK_NAME", "então é o seguinte eu me chamo assim") is None


# ==========================================================
# Corpo, uma medida por vez (idade / peso / altura)
# ==========================================================

def test_age_variants():

    assert parse("ASK_AGE", "33") == {"age": 33}
    assert parse("ASK_AGE", "tenho 33 anos") == {"age": 33}


def test_age_ambiguous_defers():

    assert parse("ASK_AGE", "entre 30 e 40") is None


def test_weight_variants():

    assert parse("ASK_WEIGHT", "91kg") == {"weight": 91.0}
    assert parse("ASK_WEIGHT", "91") == {"weight": 91.0}
    assert parse("ASK_WEIGHT", "72,5 kg") == {"weight": 72.5}


def test_height_variants():

    assert parse("ASK_HEIGHT", "1,78 m") == {"height": 1.78}
    assert parse("ASK_HEIGHT", "1.78") == {"height": 1.78}
    assert parse("ASK_HEIGHT", "178cm") == {"height": 1.78}
    assert parse("ASK_HEIGHT", "178") == {"height": 1.78}


# ==========================================================
# Experiência, uma pergunta por vez
# ==========================================================

def test_runs_today_yes_no():

    assert parse("ASK_RUNS_TODAY", "sim") == {"runs_today": True}
    assert parse("ASK_RUNS_TODAY", "não") == {"runs_today": False}


def test_runs_today_non_runner_phrases():

    assert parse("ASK_RUNS_TODAY", "sou iniciante") == {"runs_today": False}
    assert parse("ASK_RUNS_TODAY", "nunca corri") == {"runs_today": False}


def test_runs_per_week_variants():

    assert parse("ASK_RUNS_PER_WEEK", "3x") == {"runs_per_week": 3}
    assert parse("ASK_RUNS_PER_WEEK", "3 vezes") == {"runs_per_week": 3}
    assert parse("ASK_RUNS_PER_WEEK", "umas 4") == {"runs_per_week": 4}


def test_typical_km_variants():

    assert parse("ASK_TYPICAL_KM", "5km") == {"typical_km": 5.0}
    assert parse("ASK_TYPICAL_KM", "uns 5") == {"typical_km": 5.0}
    assert parse("ASK_TYPICAL_KM", "7,5 km") == {"typical_km": 7.5}


def test_typical_km_ambiguous_defers():

    assert parse("ASK_TYPICAL_KM", "entre 5 e 8") is None


# ==========================================================
# Pace
# ==========================================================

def test_pace_variants():

    assert parse("ASK_PACE", "uns 32 minutos") == {"typical_minutes": 32.0}
    assert parse("ASK_PACE", "meia hora") == {"typical_minutes": 30.0}
    assert parse("ASK_PACE", "1h") == {"typical_minutes": 60.0}
    assert parse("ASK_PACE", "30") == {"typical_minutes": 30.0}


def test_pace_ambiguous_multiple_numbers_defers():

    assert parse("ASK_PACE", "sei lá, entre 30 e 40") is None


# ==========================================================
# Dias
# ==========================================================

def test_days_full_names():

    assert parse("ASK_DAYS", "terça, quinta e sábado") == {
        "days": ["Tuesday", "Thursday", "Saturday"],
    }


def test_days_abbreviations():

    assert parse("ASK_DAYS", "seg, qua e sex") == {
        "days": ["Monday", "Wednesday", "Friday"],
    }


def test_days_weekend_and_everyday():

    assert parse("ASK_DAYS", "final de semana") == {
        "days": ["Saturday", "Sunday"],
    }

    assert parse("ASK_DAYS", "todos os dias") == {
        "days": [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ],
    }


def test_days_none_found_defers():

    assert parse("ASK_DAYS", "qualquer dia serve") is None


# ==========================================================
# Semana (esta vs próxima) e "mando depois"
# ==========================================================

def test_week_choice():

    assert parse("ASK_WEEK_CHOICE", "essa mesmo") == {"start_week": "current"}
    assert parse("ASK_WEEK_CHOICE", "prefiro a próxima") == {
        "start_week": "next",
    }


def test_await_plan_media_skip():

    assert parse("AWAIT_PLAN_MEDIA", "mando depois") == {"skip": True}
    assert parse("AWAIT_PLAN_MEDIA", "não tenho aqui agora") == {"skip": True}


# ==========================================================
# Fronteiras
# ==========================================================

def test_goal_step_has_no_deterministic_handler():

    assert parse("ASK_GOAL", "correr 10km") is None


def test_empty_answer_defers():

    assert parse("ASK_STRAVA", "   ") is None
