"""Padrão da análise via Garmin: quem está CONECTADO é analisado pelo Garmin
por padrão (sem marcador pra ligar); `analysis_off` é a válvula de escape que
força a análise de volta ao Strava."""

from app.infrastructure.integrations.garmin.garmin_client import GarminClient


def _connect(tmp_path, profile: str) -> None:
    """Simula um atleta conectado: token salvo no diretório dele."""

    token_dir = tmp_path / profile

    token_dir.mkdir(parents=True, exist_ok=True)

    (token_dir / "garmin_tokens.json").write_text("{}", encoding="utf-8")


def _point_storage(monkeypatch, tmp_path) -> None:

    monkeypatch.setattr(GarminClient, "token_dir", staticmethod(lambda p: tmp_path / p))


def test_connected_is_analyzed_by_garmin_by_default(monkeypatch, tmp_path):
    """Conectou -> análise via Garmin, sem precisar ligar marcador nenhum."""

    _point_storage(monkeypatch, tmp_path)

    _connect(tmp_path, "joaosoares")

    assert GarminClient.is_connected("joaosoares") is True
    assert GarminClient.analysis_enabled("joaosoares") is True


def test_not_connected_is_never_garmin_analyzed(monkeypatch, tmp_path):
    """Sem token, a análise NUNCA é via Garmin (cai no Strava)."""

    _point_storage(monkeypatch, tmp_path)

    assert GarminClient.is_connected("ninguem") is False
    assert GarminClient.analysis_enabled("ninguem") is False


def test_opt_out_forces_strava(monkeypatch, tmp_path):
    """set_analysis(False) grava o override e tira do Garmin, mesmo conectado."""

    _point_storage(monkeypatch, tmp_path)

    _connect(tmp_path, "renato2")

    GarminClient.set_analysis("renato2", False)

    assert (tmp_path / "renato2" / "analysis_off").exists()
    assert GarminClient.analysis_enabled("renato2") is False


def test_opt_out_is_reversible(monkeypatch, tmp_path):
    """set_analysis(True) remove o override e volta ao padrão (Garmin)."""

    _point_storage(monkeypatch, tmp_path)

    _connect(tmp_path, "renato2")

    GarminClient.set_analysis("renato2", False)

    GarminClient.set_analysis("renato2", True)

    assert not (tmp_path / "renato2" / "analysis_off").exists()
    assert GarminClient.analysis_enabled("renato2") is True


def test_legacy_analysis_on_marker_is_ignored(monkeypatch, tmp_path):
    """O antigo marcador `analysis_on` não é mais necessário nem atrapalha:
    o que decide é conexão + ausência de `analysis_off`."""

    _point_storage(monkeypatch, tmp_path)

    _connect(tmp_path, "fernanda")

    # marcador legado presente: irrelevante — segue analisando via Garmin
    (tmp_path / "fernanda" / "analysis_on").write_text("1", encoding="utf-8")

    assert GarminClient.analysis_enabled("fernanda") is True
