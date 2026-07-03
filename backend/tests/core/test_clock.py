from datetime import UTC, date, datetime
from unittest.mock import patch

from app.core.clock import DEFAULT_TIMEZONE, today_local

MODULE = "app.core.clock"


def test_default_timezone_is_sao_paulo():

    assert DEFAULT_TIMEZONE.key == "America/Sao_Paulo"


def test_today_local_uses_wall_clock_not_utc():

    # Domingo 05/07 21:30 no Brasil = segunda 06/07 00:30 em UTC.
    # A data "de hoje" tem que continuar sendo domingo.
    late_sunday_utc = datetime(2026, 7, 6, 0, 30, tzinfo=UTC)

    with patch(f"{MODULE}.datetime") as mock_datetime:

        mock_datetime.now.return_value = late_sunday_utc.astimezone(
            DEFAULT_TIMEZONE
        )

        assert today_local() == date(2026, 7, 5)

        mock_datetime.now.assert_called_once_with(DEFAULT_TIMEZONE)
