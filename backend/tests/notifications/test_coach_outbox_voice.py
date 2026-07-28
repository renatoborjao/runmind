import asyncio
from unittest.mock import AsyncMock, patch

from app.application.notifications.coach_outbox import CoachOutbox
from tests.coach.factories import make_runner

MODULE = "app.application.notifications.coach_outbox"


def _send(voice, profile, wants_audio=True):
    with (
        patch(f"{MODULE}.NotificationService") as notif,
        patch(f"{MODULE}.CoachVoice") as coach_voice,
        patch(f"{MODULE}.VoicePreferenceRepository") as pref,
        patch(f"{MODULE}.CoachOutboxRepository"),
    ):

        notif.send = AsyncMock()
        coach_voice.voice_only = AsyncMock()
        pref.wants_audio.return_value = wants_audio

        asyncio.run(
            CoachOutbox.send(
                make_runner(channel="telegram", telegram_id="42"),
                "É hoje! Sua prova chegou.",
                voice=voice,
                profile=profile,
            )
        )

        return notif, coach_voice, pref


def test_text_only_when_voice_false():

    notif, coach_voice, _ = _send(voice=False, profile="renato2")

    notif.send.assert_awaited_once()
    coach_voice.voice_only.assert_not_awaited()


def test_voice_added_when_enabled_and_preferred():

    notif, coach_voice, pref = _send(voice=True, profile="renato2")

    notif.send.assert_awaited_once()
    coach_voice.voice_only.assert_awaited_once()
    pref.wants_audio.assert_called_once_with("renato2")


def test_voice_suppressed_when_athlete_opted_out():

    notif, coach_voice, _ = _send(
        voice=True, profile="renato2", wants_audio=False,
    )

    notif.send.assert_awaited_once()
    coach_voice.voice_only.assert_not_awaited()
