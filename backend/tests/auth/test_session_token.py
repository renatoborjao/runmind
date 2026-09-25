from app.infrastructure.security.session_token import SessionToken


def test_issue_then_verify_roundtrip():

    token = SessionToken.issue("renato2")

    assert SessionToken.verify(token) == "renato2"


def test_tampered_token_is_rejected():

    token = SessionToken.issue("renato2")

    payload, sig = token.rsplit(".", 1)

    # troca o perfil no payload sem reassinar -> assinatura não bate
    forged = payload[:-2] + ("aa" if not payload.endswith("aa") else "bb")

    assert SessionToken.verify(f"{forged}.{sig}") is None


def test_expired_token_is_rejected():

    token = SessionToken.issue("renato2", ttl_days=-1)

    assert SessionToken.verify(token) is None


def test_garbage_is_rejected():

    assert SessionToken.verify(None) is None
    assert SessionToken.verify("") is None
    assert SessionToken.verify("sem-ponto") is None
    assert SessionToken.verify("a.b.c") is None


def test_purpose_token_only_verifies_with_same_purpose():
    """Token de uso restrito (ex.: state do OAuth do Strava) nunca vale como
    sessão, e sessão nunca vale como token de uso restrito."""

    scoped = SessionToken.issue("renato2", purpose="strava_connect", ttl_seconds=60)
    session = SessionToken.issue("renato2")

    assert SessionToken.verify(scoped, purpose="strava_connect") == "renato2"
    assert SessionToken.verify(scoped) is None
    assert SessionToken.verify(scoped, purpose="outro") is None
    assert SessionToken.verify(session, purpose="strava_connect") is None


def test_purpose_token_expires_by_seconds():

    token = SessionToken.issue("renato2", purpose="strava_connect", ttl_seconds=-1)

    assert SessionToken.verify(token, purpose="strava_connect") is None
