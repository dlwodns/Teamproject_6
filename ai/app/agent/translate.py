"""메일 번역 (POST /translate, AI-32). 누를 때만 한 번 부른다(하루 한도 100회). 결과는 backend가 저장한다.

아웃룩 번역과 같게 40자 미만은 번역하지 않는다(Microsoft 지원 문서 'Translator in Outlook'). 이미 한국어인 글도 부르지 않는다.
모델 결과에 한국어가 없으면(원문을 그대로 돌려줌) 번역 실패로 본다 — 원문을 번역처럼 보이지 않게."""
from app.agent.assist import _HANGUL, detect_lang
from app.llm.client import LLMClient, LLMError
from app.prompts import translate_v1 as prompts
from app.schemas.assist import TranslateRequest, TranslateResponse

MIN_CHARS = 40
MAX_CHARS = 12000  # 아주 긴 본문은 앞부분만(출력이 잘리지 않게). ponytail: 나눠 부르기는 실제로 잘릴 때


def translate(req: TranslateRequest, llm: LLMClient) -> TranslateResponse:
    text = req.text.strip()
    lang = detect_lang(text)
    base = TranslateResponse(text="", lang=lang, source="none", prompt_version=prompts.PROMPT_VERSION)
    if len(text) < MIN_CHARS:
        return base.model_copy(update={"fallback": "40자 미만"})
    if lang == "ko":
        return base.model_copy(update={"fallback": "이미 한국어"})
    try:
        out = llm.chat_json(prompts.SYSTEM, f"원문 언어: {lang}\n본문:\n{text[:MAX_CHARS]}", prompts.SCHEMA)
    except LLMError as e:
        return base.model_copy(update={"fallback": f"모델 호출 실패: {e}"})
    ko = str(out.get("text") or "").strip() if isinstance(out, dict) else ""
    if not ko or not _HANGUL.search(ko):
        return base.model_copy(update={"fallback": "번역문이 한국어가 아님"})
    return base.model_copy(update={"text": ko, "source": "exaone", "truncated": len(text) > MAX_CHARS})
