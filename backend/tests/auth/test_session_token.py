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
