"""ai 서비스 호출 (BE-9). backend가 ai를 부르는 곳은 이 패키지 한 곳이다(D34)."""
from app.ai_client.client import AIClient, AIError, get_ai_client

__all__ = ["AIClient", "AIError", "get_ai_client"]
