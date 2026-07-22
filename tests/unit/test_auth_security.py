"""密码和登录标识安全工具的单元测试。"""

import pytest

from app.modules.auth.security import (
    hash_password,
    hash_session_token,
    normalize_identifiers,
    validate_new_password,
    verify_password,
)


def test_password_hash_does_not_contain_plaintext_and_can_be_verified() -> None:
    password_hash = hash_password("StrongPass2026")

    assert "StrongPass2026" not in password_hash
    assert password_hash.startswith("$argon2id$")
    assert verify_password(password_hash, "StrongPass2026") is True
    assert verify_password(password_hash, "wrong-password") is False


def test_identifier_normalization_supports_employee_number_and_phone() -> None:
    assert "DEV-E0001" in normalize_identifiers(" dev-e0001 ")
    assert "13800138000" in normalize_identifiers("138-0013-8000")


def test_new_password_requires_letters_and_digits() -> None:
    validate_new_password("Secure2026Pass")
    with pytest.raises(ValueError, match="字母和数字"):
        validate_new_password("onlyletters")


def test_session_hash_is_stable_and_not_the_token() -> None:
    token_hash = hash_session_token("opaque-session-token")
    assert token_hash == hash_session_token("opaque-session-token")
    assert token_hash != "opaque-session-token"
    assert len(token_hash) == 64
