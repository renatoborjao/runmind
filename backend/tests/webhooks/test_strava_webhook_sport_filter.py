from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from tests.coach.factories import make_activity

MODULE = "app.presentation.api.v1.webhooks"

PAYLOAD = {
    "object_type": "activity",
    "aspect_type": "create",
    "object_id": 123,
    "owner_id": 111,
}


def _post_webhook(sport: str, distance: float = 10000.0):

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
        patch(f"{MODULE}.ProcessedActivityGuard") as mock_guard_cls,
    ):

        mock_resolver.resolve.return_value = "renato"

        mock_client = mock_client_cls.return_value
        mock_client.get_activity = AsyncMock(
            return_value=make_activity(sport=sport, distance=distance),
        )

        mock_event.execute = AsyncMock()

        # atividade nova: libera o processamento
        mock_guard_cls.return_value.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json=PAYLOAD,
        )

        return response.json(), mock_event


def test_ride_is_ignored_and_does_not_trigger_feedback():

    # ack rápido: responde "queued" na hora; o filtro de esporte roda no
    # background e não dispara feedback pra pedalada
    body, mock_event = _post_webhook("Ride")

    assert body["queued"] is True

    mock_event.execute.assert_not_awaited()


def test_run_triggers_training_completed_event():

    # corrida: responde "queued" e o background dispara o feedback
    body, mock_event = _post_webhook("Run")

    assert body["queued"] is True

    mock_event.execute.assert_awaited_once()


def test_run_without_distance_is_ignored():

    # corrida sem distância (esteira/HIIT sem sensor): não dá pra analisar
    # pace — pula no background sem crashar nem gerar feedback
    body, mock_event = _post_webhook("Run", distance=0.0)

    assert body["queued"] is True

    mock_event.execute.assert_not_awaited()


def _post_delete(
    feedback_was_sent: bool,
    removed_from_archive: bool = True,
):

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
        patch(f"{MODULE}.ProcessedActivityGuard") as mock_guard_cls,
        patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive_cls,
        patch(f"{MODULE}.RunnerProfileRepository") as mock_profile_cls,
        patch(f"{MODULE}.NotificationService") as mock_notify,
    ):

        mock_resolver.resolve.return_value = "renato"

        mock_guard = mock_guard_cls.return_value
        mock_guard.is_marked.return_value = feedback_was_sent

        mock_archive = mock_archive_cls.return_value
        mock_archive.remove.return_value = removed_from_archive

        mock_notify.send = AsyncMock()

        mock_event.execute = AsyncMock()

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json={**PAYLOAD, "aspect_type": "delete"},
        )

        return (
            response.json(),
            mock_archive,
            mock_guard,
            mock_notify,
            mock_event,
            mock_client_cls,
        )


def test_delete_event_removes_from_archive():

    body, mock_archive, mock_guard, _, mock_event, mock_client_cls = (
        _post_delete(feedback_was_sent=False)
    )

    assert body["deleted"] is True
    assert body["removed_from_archive"] is True

    # tira do arquivo permanente e solta a marca de idempotência
    mock_archive.remove.assert_called_once_with("renato", 123)
    mock_guard.unmark.assert_called_once_with(123)

    # não busca a atividade (já não existe) nem gera feedback
    mock_client_cls.return_value.get_activity.assert_not_called()
    mock_event.execute.assert_not_called()


def test_delete_after_feedback_sends_retraction():

    # atleta recebeu a análise e apagou o treino (ex.: teste na
    # esteira): coach avisa que pode desconsiderar
    body, _, _, mock_notify, _, _ = _post_delete(
        feedback_was_sent=True,
    )

    assert body["retraction_queued"] is True

    mock_notify.send.assert_awaited_once()

    message = mock_notify.send.await_args.args[1]
    assert "desconsiderar" in message


def test_delete_without_feedback_sends_nothing():

    # treino antigo (de antes do RunMind) apagado: some do arquivo,
    # mas não houve análise — retratação seria sem sentido
    body, _, _, mock_notify, _, _ = _post_delete(
        feedback_was_sent=False,
    )

    assert body["retraction_queued"] is False

    mock_notify.send.assert_not_awaited()


def test_delete_of_ride_sends_no_retraction():

    # pedalada: passou pelo webhook (marca no guard) mas nunca gerou
    # análise (não está no arquivo) — nada de retratação
    body, _, _, mock_notify, _, _ = _post_delete(
        feedback_was_sent=True,
        removed_from_archive=False,
    )

    assert body["retraction_queued"] is False

    mock_notify.send.assert_not_awaited()


def test_delete_event_from_unknown_owner_does_not_500():

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
        patch(f"{MODULE}.ActivityArchiveRepository") as mock_archive_cls,
    ):

        # atleta não cadastrado: resolve levanta exceção
        mock_resolver.resolve.side_effect = Exception(
            "Nenhum perfil encontrado",
        )

        mock_event.execute = AsyncMock()

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json={**PAYLOAD, "aspect_type": "delete"},
        )

        # 200 mesmo assim — senão o Strava reentrega pra sempre
        assert response.status_code == 200
        assert response.json()["ignored"] is True

        mock_archive_cls.return_value.remove.assert_not_called()
        mock_event.execute.assert_not_called()


def test_activity_404_does_not_500():

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
        patch(f"{MODULE}.ProcessedActivityGuard") as mock_guard_cls,
        patch(f"{MODULE}.GarminClient") as mock_garmin,
    ):

        mock_resolver.resolve.return_value = "renato2"

        # força o caminho Strava (independe do estado real do Garmin em disco)
        mock_garmin.is_connected.return_value = False
        mock_garmin.analysis_enabled.return_value = False

        mock_client = mock_client_cls.return_value
        mock_client.get_activity = AsyncMock(
            side_effect=RuntimeError("404 Not Found"),
        )

        mock_event.execute = AsyncMock()

        mock_guard = mock_guard_cls.return_value
        mock_guard.check_and_mark.return_value = True

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json=PAYLOAD,
        )

        # ack rápido: 200 imediato mesmo com a busca falhando no background
        assert response.status_code == 200
        assert response.json()["queued"] is True
        mock_event.execute.assert_not_called()

        # background falhou: solta a marca pra o Strava poder reentregar
        mock_guard.unmark.assert_called_once_with(123)


def test_duplicate_activity_is_ignored():

    with (
        patch(f"{MODULE}.OwnerResolver") as mock_resolver,
        patch(f"{MODULE}.StravaClient") as mock_client_cls,
        patch(f"{MODULE}.TrainingCompletedEvent") as mock_event,
        patch(f"{MODULE}.ProcessedActivityGuard") as mock_guard_cls,
    ):

        mock_event.execute = AsyncMock()

        # atividade já processada: reentrega do Strava não gera 2ª msg
        mock_guard_cls.return_value.check_and_mark.return_value = False

        client = TestClient(app)

        response = client.post(
            "/api/v1/webhooks/strava",
            json=PAYLOAD,
        )

        body = response.json()
        assert body["ignored"] is True
        assert "duplicate" in body["reason"]

        # não resolve dono, não busca atividade, não envia feedback
        mock_resolver.resolve.assert_not_called()
        mock_event.execute.assert_not_awaited()
