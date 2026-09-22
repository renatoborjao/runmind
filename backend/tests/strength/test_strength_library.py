from app.application.strength.strength_library import CATEGORIES, library


def test_all_exercises_enriched_and_structured():
    exs = library()["exercises"]

    assert len(exs) >= 15

    for e in exs:
        # campos de conteúdo do coach
        for k in ("common_mistake", "feel_where", "regression", "progression", "breathing"):
            assert e.get(k), f"{e['id']} sem {k}"

        # categoria válida
        assert e["category"] in CATEGORIES

        # prescrição estruturada coerente (rep OU tempo, nunca os dois vazios)
        ex = e.get("execution")
        assert ex, f"{e['id']} sem execution"
        assert ex["sets"] >= 1
        assert (ex["reps"] is None) != (ex["hold_seconds"] is None), (
            f"{e['id']}: use reps XOR hold_seconds"
        )
        assert isinstance(ex["per_side"], bool)
        assert ex["rest_seconds"] >= 0


def test_new_exercises_present():
    ids = {e["id"] for e in library()["exercises"]}
    for new in ("single_leg_calf_raise", "monster_walk", "clamshell", "dead_bug", "bird_dog"):
        assert new in ids
