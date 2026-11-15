"""개인정보 가리기 (BE-6 · D34 · 구조도 6 · 10절). ai로 보내기 전에 가리고, ai 응답은 되돌려 저장한다."""
from app.privacy.mask import Masker, enabled, masker_for

__all__ = ["Masker", "enabled", "masker_for"]
