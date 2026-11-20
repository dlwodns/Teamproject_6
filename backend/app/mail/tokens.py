"""메일 계정 토큰 암호화 (BE-6 · 구조도 10절 '토큰은 암호화 저장, 키는 .env').

키는 TOKEN_ENCRYPTION_KEY(Fernet 키, urlsafe base64 32바이트). 키를 바꾸면 저장된 토큰을 풀 수 없다 → 계정을 다시 연결한다.
토큰 값은 로그 · 오류 메시지에 넣지 않는다.
"""
import os

from cryptography.fernet import Fernet, InvalidToken


class TokenKeyError(RuntimeError):
    """키가 없거나 틀려 토큰을 풀 수 없다. 사용자는 계정을 다시 연결해야 한다."""


def valid_key(key: str) -> bool:
    try:
        Fernet(key.encode())
    except ValueError:
        return False
    return True


def _fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPTION_KEY", "").strip()
    if not key or not valid_key(key):
        raise TokenKeyError("TOKEN_ENCRYPTION_KEY가 없거나 Fernet 키가 아니다")
    return Fernet(key.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as e:  # 키가 바뀌었거나 값이 깨졌다
        raise TokenKeyError("저장된 토큰을 풀 수 없다(키가 바뀌었나?)") from e
