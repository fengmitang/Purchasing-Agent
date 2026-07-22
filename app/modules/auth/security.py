"""密码和会话令牌的单向摘要工具。"""

import hashlib
import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_password_hasher = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4)
_phone_cleanup = re.compile(r"[\s\-()]+")


def normalize_identifiers(value: str) -> set[str]:
    """同时生成工号和电话号码可能采用的规范化形式。"""
    stripped = value.strip()
    return {stripped.upper(), _phone_cleanup.sub("", stripped)}


def hash_password(password: str) -> str:
    """使用 Argon2id 生成不可逆密码摘要。"""
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """验证密码且不向调用方暴露摘要解析错误。"""
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False


def validate_new_password(password: str) -> None:
    """执行基础密码强度规则。"""
    if (
        len(password) < 10
        or not any(char.isalpha() for char in password)
        or not any(char.isdigit() for char in password)
    ):
        raise ValueError("新密码至少 10 位，并且同时包含字母和数字")


def hash_session_token(token: str) -> str:
    """数据库仅保存会话令牌的 SHA-256 摘要。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
