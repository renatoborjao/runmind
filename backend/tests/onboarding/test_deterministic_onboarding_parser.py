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


def test_confirm_days_correction_takes_priority():

    # atleta reescreve os dias na conferência (bug do Adolfo)
    assert parse(
        "CONFIRM", "Eu posso correr segunda terça quarta quinta e sexta"
    ) == {
        "corrections": {
            "days": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            ],
        },
    }


def test_confirm_days_range_correction_beats_negation():

    # "não, corro de seg a sex" é correção — NÃO deve cancelar o cadastro
    assert parse("CONFIRM", "não, corro de segunda a sexta") == {
        "corrections": {
            "days": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            ],
        },
    }


def test_confirm_single_day_without_cue_stays_yes():

    # "pode sim, começando segunda" é confirmação, não correção de 1 dia
    assert parse("CONFIRM", "pode sim, começando segunda") == {
        "confirmed": True,
    }


def test_confirm_single_day_with_cue_is_correction():

    assert parse("CONFIRM", "na verdade só quinta") == {
        "corrections": {"days": ["Thursday"]},
    }


def test_confirm_field_correction_defers_to_gemini():

    # correção de outro campo (rótulo/unidade) cai no Gemini pra extração
    for answer in (
        "na verdade meu peso é 130kg",
        "tenho 36 anos",
        "minha altura é 1,90",
        "meu objetivo é a maratona de SP",
    ):

        assert parse("CONFIRM", answer) is None, answer


def test_confirm_days_step_uses_corrections_shape():

    assert parse("CONFIRM_DAYS", "segunda a sexta") == {
        "corrections": {
            "days": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            ],
        },
    }
    assert parse("CONFIRM_DAYS", "sim") == {"confirmed": True}


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


def test_typical_km_range_uses_average():
    """Bug da Fernanda: "5 a 15km" pegava o 15 (colado no km) e inflava o
    volume. Faixa vira MÉDIA + guarda os extremos."""

    for text in ("5 a 15km", "5-15km", "5 a 15", "entre 5 e 15", "de 5 a 15 km"):
        assert parse("ASK_TYPICAL_KM", text) == {
            "typical_km": 10.0,
            "typical_km_min": 5.0,
            "typical_km_max": 15.0,
        }

    # faixa invertida ("15 a 5") normaliza
    assert parse("ASK_TYPICAL_KM", "entre 5 e 8") == {
        "typical_km": 6.5,
        "typical_km_min": 5.0,
        "typical_km_max": 8.0,
    }


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


def test_days_range_expands_all_days_between():

    # "segunda a sexta" = o intervalo inteiro, não só as pontas (bug do Adolfo)
    assert parse("ASK_DAYS", "segunda a sexta") == {
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }


def test_days_range_variants():

    for answer in (
        "de segunda à sexta",
        "segunda até sexta",
        "seg a sex",
        "seg-sex",
    ):

        assert parse("ASK_DAYS", answer) == {
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        }, answer


def test_days_conjunction_is_not_a_range():

    # "segunda e sexta" continua sendo só esses dois dias
    assert parse("ASK_DAYS", "segunda e sexta") == {
        "days": ["Monday", "Friday"],
    }


def test_days_range_plus_extra_day():

    assert parse("ASK_DAYS", "de terça a quinta e domingo") == {
        "days": ["Tuesday", "Wednesday", "Thursday", "Sunday"],
    }


def test_days_ordinal_forms():

    # "2ª feira" = segunda … "6ª feira" = sexta
    assert parse("ASK_DAYS", "2ª, 4ª e 6ª feira") == {
        "days": ["Monday", "Wednesday", "Friday"],
    }


def test_days_ordinal_range():

    assert parse("ASK_DAYS", "de 2ª a 6ª") == {
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    }


def test_days_bare_number_is_not_a_day():

    # "5" solto (ex.: pensando em "5 dias/semana") não vira quinta-feira
    assert parse("ASK_DAYS", "5") is None


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
# Movimento (como o iniciante se move hoje)
# ==========================================================

def test_movement_walker_only():

    assert parse("ASK_MOVEMENT", "só caminho") == {"mobility": "walker"}


def test_movement_run_walker():

    assert parse("ASK_MOVEMENT", "faço trote e caminhada") == {
        "mobility": "run_walker",
    }


def test_movement_with_numbers_defers_to_gemini():

    # texto com tempos/velocidades vai pro Gemini extrair tudo
    assert parse("ASK_MOVEMENT", "trote 1 min e caminho 3 min") is None


# ==========================================================
# Fronteiras
# ==========================================================

def test_goal_step_has_no_deterministic_handler():

    assert parse("ASK_GOAL", "correr 10km") is None


def test_empty_answer_defers():

    assert parse("ASK_STRAVA", "   ") is None
