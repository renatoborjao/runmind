from app.application.strength.strength_library import CATEGORIES, library


def test_only_demoed_exercises_are_served():
    """Regra do Renato: só entra exercício COM demonstração. library() nunca
    serve card sem imagem."""

    exs = library()["exercises"]

    assert len(exs) >= 10
    assert all(e.get("images") for e in exs), "há exercício sem demo sendo servido"

    # dead_bug (tem foto no acervo) entra; os 4 sem foto ficam ocultos
    ids = {e["id"] for e in exs}
    assert "dead_bug" in ids
    for hidden in ("single_leg_calf_raise", "monster_walk", "clamshell", "bird_dog"):
        assert hidden not in ids


def test_all_exercises_enriched_and_structured():
    exs = library()["exercises"]

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


def test_hidden_exercises_stay_defined_for_later():
    """Os exercícios sem demo continuam definidos no código (conteúdo pronto),
    só não são servidos — voltam quando ganharem mídia."""

    from app.application.strength.strength_library import EXERCISES

    defined = {e["id"] for e in EXERCISES}
    for pending in ("single_leg_calf_raise", "monster_walk", "clamshell", "bird_dog"):
        assert pending in defined
