from unittest.mock import MagicMock, patch

from app.main import create_app

MODULE = "app.main"


def _settings(app_env: str):

    settings = MagicMock()
    settings.app_env = app_env
    settings.app_version = "0.0.0"
    settings.cors_origin_list = []
    return settings


def test_docs_open_in_development():

    with patch(f"{MODULE}.get_settings", return_value=_settings("development")):

        app = create_app()

    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_docs_closed_in_production():
    """Em produção a planta pública da API (Swagger/ReDoc/OpenAPI) fica fechada
    — não há front consumindo, e expor o schema num host público é superfície
    à toa."""

    with patch(f"{MODULE}.get_settings", return_value=_settings("production")):

        app = create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
