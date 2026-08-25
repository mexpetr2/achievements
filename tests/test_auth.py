from web.auth import check_password, hash_password


def test_hash_password_produces_verifiable_hash():
    stored = hash_password("secret-du-nas")
    assert check_password(stored, "secret-du-nas") is True


def test_check_password_rejects_wrong_password():
    stored = hash_password("secret-du-nas")
    assert check_password(stored, "mauvais") is False


def test_hash_password_uses_random_salt():
    assert hash_password("meme-mot-de-passe") != hash_password("meme-mot-de-passe")


def test_check_password_rejects_malformed_stored_value():
    assert check_password("n-importe-quoi", "secret") is False


def test_check_password_rejects_empty_stored_value():
    assert check_password("", "secret") is False
