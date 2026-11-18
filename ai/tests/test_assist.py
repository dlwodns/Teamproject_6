from datetime import datetime

from app.agent.assist import detect_lang, draft, summarize
from app.llm.client import LLMError
from app.schemas.assist import DraftRequest, MailInput, SummarizeRequest, SummaryItem

NOW = datetime(2026, 11, 2, 9, 0)
ITEMS = [
    SummaryItem(task_id="1", text="실적 자료 제출", sender="박 팀장", due_at=datetime(2026, 11, 2, 17, 0), priority="P2"),
    SummaryItem(task_id="2", text="절차서 검토", due_at=datetime(2026, 11, 1, 18, 0), priority="P3"),
    SummaryItem(task_id="3", text="견적 확인", status="snoozed"),
]


def test_today_code_summary_orders_overdue_first(fake_llm):
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS, awaiting_reply_count=2, use_model=False), fake_llm)
    assert r.source == "code" and fake_llm.calls == []
    assert r.counts.model_dump() == {"pending": 2, "due_today": 2, "overdue": 1, "awaiting_reply": 2}  # 나중에(snoozed)는 빠진다
    assert r.text.startswith("기한이 지난 업무가 1건 있습니다.")
    assert "오늘 마감인 업무가 1건 있습니다." in r.text and "답장이 없는 보낸 메일이 2건" in r.text
    assert "견적" not in r.text


def test_today_model_gets_only_facts(fake_llm):
    fake_llm.replies = ["기한이 지난 업무는 1건입니다. 오늘 마감은 박 팀장 1건입니다."]
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS), fake_llm)
    assert r.source == "exaone" and r.prompt_version == "assist_v4"
    user = fake_llm.calls[0]["user"]
    assert "실적 자료 제출" in user and "[기한 지남 · 그 밖] 1건" in user and "견적" not in user


def test_today_falls_back_to_code(fake_llm):
    fake_llm.replies = [LLMError("down")]
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS), fake_llm)
    assert r.source == "code" and r.fallback == "down" and r.text.startswith("기한이 지난 업무가 1건")


EN_BODY = "Hi,\nPlease send the Q3 report by Friday EOD. It is needed for the board meeting.\nThanks,\nJohn"
EN_MAIL = MailInput(subject="Q3 report", body=EN_BODY)
KO_BODY = "안녕하세요. 이관 절차서 초안을 공유드립니다. 11/10(화)까지 검토 의견 부탁드립니다.\n감사합니다."


def test_detect_lang():
    assert detect_lang("Please send the report by Friday.") == "en"
    assert detect_lang("PoC 범위에 batch server 포함 여부 회신 부탁드립니다. Thanks, Kim") == "ko"  # 영문 용어 · 서명 섞임
    assert detect_lang("報告書を金曜日までに送ってください。") == "ja"
    assert detect_lang("请在周五之前发送报告。") == "zh"
    assert detect_lang("") == "ko" and detect_lang("12345 !!") == "ko"


# 영어가 아닌 라틴 문자 언어(이재운 리뷰): 카드에 '원문 언어: 영어'로 잘못 보이지 않게 'other'(기타 외국어)로 둔다.
OTHER_LATIN = {
    "fr": "Bonjour,\nPourriez-vous m'envoyer le rapport du troisième trimestre avant vendredi ? Nous en avons besoin pour la réunion.\nCordialement,\nSophie",
    "de": "Hallo Herr Kim,\nkönnen Sie mir bitte den Bericht für das dritte Quartal bis Freitag schicken? Wir brauchen ihn für die Sitzung.\nMit freundlichen Grüßen\nAnna",
    "es": "Hola,\n¿Podría enviarme el informe del tercer trimestre antes del viernes? Lo necesitamos para la reunión.\nSaludos,\nCarlos",
    "it": "Ciao,\npotresti inviarmi il rapporto del terzo trimestre entro venerdì? Ci serve per la riunione.\nGrazie,\nMarco",
    "pt": "Olá,\nvocê pode me enviar o relatório do terceiro trimestre até sexta-feira? Precisamos dele para a reunião.\nObrigado,\nJoão",
    "nl": "Hallo,\nkun je mij het rapport van het derde kwartaal voor vrijdag sturen? We hebben het nodig voor de vergadering.\nGroeten,\nPieter",
    "de_short": "Bitte den Bericht bis Freitag schicken. Danke!",
    "fr_short": "Merci pour votre retour, à demain.",
}


def test_detect_lang_other_latin_is_not_english():
    for name, text in OTHER_LATIN.items():
        assert detect_lang(text) == "other", name


def test_detect_lang_english_stays_english():
    cases = [
        "Thanks!",
        "Noted, thanks.",
        "Please send the report by Friday.",
        "Hi Minjun,\nCan you share the Q3 deck with Kim Jiho before the meeting? Thanks, Daniel",
        "Hi 김민준님,\nPlease review the attached SLA draft and reply by 11/10.\nBest regards,\nDaniel Moore",  # 한국어 이름 섞임
        EN_BODY,
        # 서명 · 인용문 포함(인용 줄 '>' · 회사 주소 · 휴대폰 서명)
        "Hi,\nSounds good, let's go with option B.\n\nBest,\nDaniel Moore | Manager\nHarborline Systems\n"
        "1200 Market St, Suite 400\nSent from my iPhone\n\nOn Tue, Nov 4, 2026, Kim wrote:\n> Could you confirm the scope?\n> Thanks",
        "Re: Café Müller order — please confirm the delivery date for José's team.",  # 고유명사 속 악센트
        "Hi team, FYI the server is down. ETA 2h.",
    ]
    for text in cases:
        assert detect_lang(text) == "en", text


def test_mail_summary_other_latin_language(fake_llm):
    fr = MailInput(subject="Rapport T3", body=OTHER_LATIN["fr"])
    fake_llm.replies = [{"gist": "3분기 보고서를 금요일 전에 보내 달라는 메일입니다.", "asks": ["3분기 보고서 보내기"],
                         "due_text": "avant vendredi"}]
    r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=fr), fake_llm)
    assert r.mail_summary.lang == "other" and "원문 언어: other" in fake_llm.calls[0]["user"]
    r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=fr, use_model=False), fake_llm)
    assert r.mail_summary is None and r.text == "" and r.fallback.startswith("외국어 메일(other) · 모델 없음")


def test_mail_summary_model_json(fake_llm):
    fake_llm.replies = [{"gist": "3분기 보고서를 이사회 회의용으로 요청한 메일입니다.", "asks": ["3분기 보고서 보내기", " "],
                         "due_text": "by Friday EOD"}]
    r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=EN_MAIL), fake_llm)
    assert r.source == "exaone" and r.prompt_version == "assist_v4" and r.fallback is None
    ms = r.mail_summary
    assert ms.lang == "en" and ms.asks == ["3분기 보고서 보내기"] and ms.due_text == "by Friday EOD"
    assert r.text == ms.gist  # v1 호출자 호환
    assert fake_llm.calls[0]["kind"] == "json" and "원문 언어: en" in fake_llm.calls[0]["user"]


def test_mail_summary_bad_json_falls_back(fake_llm):
    ko = MailInput(subject="절차서 검토", body=KO_BODY)
    bad = [LLMError("JSON 파싱 실패: x"), {"asks": []}, {"gist": "Q3 report request.", "asks": [], "due_text": None},
           {"gist": "요지", "asks": "보고서", "due_text": None}, {"gist": "요지", "asks": [], "due_text": 3}]
    fake_llm.replies = list(bad)
    for _ in bad:
        r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=ko), fake_llm)
        assert r.source == "code" and r.fallback and r.mail_summary.lang == "ko"


def test_mail_summary_foreign_without_model_hides_original(fake_llm):
    for req in (SummarizeRequest(mode="mail", now=NOW, mail=EN_MAIL, use_model=False),
                SummarizeRequest(mode="mail", now=NOW, mail=EN_MAIL)):  # 모델 응답 없음 → LLMError
        r = summarize(req, fake_llm)
        assert r.source == "code" and r.text == "" and r.mail_summary is None
        assert r.fallback.startswith("외국어 메일(en) · 모델 없음")
        assert "Please send" not in r.model_dump_json()


def test_mail_summary_korean_code_fallback(fake_llm):
    r = summarize(SummarizeRequest(mode="mail", now=NOW, mail=MailInput(subject="절차서 검토", body=KO_BODY),
                                   use_model=False), fake_llm)
    ms = r.mail_summary
    assert r.source == "code" and r.fallback == "모델 미사용" and fake_llm.calls == []
    assert ms.lang == "ko" and ms.asks == [] and ms.gist.startswith("안녕하세요. 이관 절차서") and r.text == ms.gist
    assert ms.due_text and ms.due_text.startswith("11/10")


def test_today_has_no_mail_summary(fake_llm):
    r = summarize(SummarizeRequest(mode="today", now=NOW, items=ITEMS, use_model=False), fake_llm)
    assert r.mail_summary is None


def test_draft_from_model_and_template(fake_llm):
    fake_llm.replies = [{"subject": "RE: 견적", "body": "확인했습니다."}, LLMError("down")]
    req = DraftRequest(kind="reply", mail=MailInput(subject="견적 요청", body="견적 부탁드립니다", sender="박 책임"))
    assert draft(req, fake_llm).source == "exaone"
    t = draft(req, fake_llm)
    assert t.source == "template" and t.subject == "RE: 견적 요청" and "[확인 필요" in t.body


def test_endpoints(client, fake_llm):
    fake_llm.replies = [LLMError("down")]
    r = client.post("/draft", json={"kind": "new", "recipient": "오 책임", "topic": "장애 보고 일정"})
    assert r.status_code == 200 and r.json()["subject"] == "[문의] 장애 보고 일정"
    r = client.post("/summarize", json={"mode": "today", "now": "2026-11-02T09:00", "items": [], "use_model": True})
    assert r.json()["text"] == "오늘까지 기한인 업무는 없습니다." and r.json()["counts"]["pending"] == 0
    r = client.post("/summarize", json={"mode": "mail", "now": "2026-11-02T09:00", "use_model": False,
                                        "mail": {"subject": "Q3", "body": EN_BODY}})
    assert r.status_code == 200 and r.json()["mail_summary"] is None and r.json()["text"] == ""
