# -*- coding: utf-8 -*-
# 개발 세트 dev10(dev10-v1) — 외국어 · 스팸 · 피싱 36통(DE-13 후속, 11/22). FINAL TEST에서 네 모델이 함께 약했던 두 곳
# (스팸 · 피싱을 할 일로 잡음, 외국어 마감)의 원인을 보는 개발 세트. 규칙 · 프롬프트를 고칠 때 써도 된다.
# 작성: Claude(문규남 요청) · 2026-11-22. 봉인 세트(FINAL TEST · 테스트 A · B)의 메일 · 오답은 보지 않았다(개수 표만 봄).
# 정답은 라벨 가이드 2절(11/21 스팸 · 피싱 · 외국어)과 4절 외국어 마감 표를 따른다. 수신일 2026-11-05(목).
# 묶음: 영어 12(할 일 9) · 일본어 9(할 일 7) · 스팸 · 피싱 12(할 일 0) · 비교용 3(사내 보안 2 — 사내 시스템 계정 조치는 할 일,
#       실제 거래처의 포털 등록 1 — 사외 · 링크 · 로그인이 있어도 진행 중인 업무 요청은 할 일). 엣지: 시간대(PT → KST) · 전각 숫자
from people import X

MAILS = []
EXTRA = {  # 세트에서만 쓰는 외부 인물. 도메인은 .example, 전화는 02-0000-xxxx
    "olv": X("Olivia Grant", "Program Manager", "Northwind Logistics", "IT Transformation",
             "olivia.grant@northwind.example", "02-0000-9301"),
    "rkp": X("Rahul Kapoor", "Delivery Lead", "Bluepeak Software", "Cloud Services",
             "rahul.kapoor@bluepeak.example", "02-0000-9302"),
    "mts": X("Marcus Teo", "Solutions Architect", "Tidewave Networks", "APAC Engineering",
             "marcus.teo@tidewave.example", "02-0000-9303"),
    "tnk": X("田中 健一", "課長", "ミライシステムズ", "クラウド事業部", "kenichi.tanaka@miraisys.example", "02-0000-9401"),
    "szk": X("鈴木 美咲", "主任", "ミライシステムズ", "購買部", "misaki.suzuki@miraisys.example", "02-0000-9402"),
    "jnl": X("Jenna Lee", "Engineering Manager", "Cascadia Cloud", "Platform Team",
             "jenna.lee@cascadiacloud.example", "02-0000-9304"),
    "ymd": X("山田 翔", "部長", "東和データ", "システム企画部", "sho.yamada@towadata.example", "02-0000-9403"),
    # 스팸 · 피싱 발신(실제 거래처 · 사내 시스템이 아님)
    "ph1": X("메일 보안센터", "", "메일 보안센터", "", "security@lgcns-mail-verify.example", "02-0000-9901"),
    "ph2": X("Microsoft 365 Support", "", "M365 Support", "", "no-reply@m365-support-center.example", "02-0000-9902"),
    "ph3": X("한빛은행 정산팀", "", "한빛은행", "정산팀", "settle@hanbitbank-pay.example", "02-0000-9903"),
    "ph4": X("한상우", "", "개인", "", "hansangwoo.cns@freemail.example", "02-0000-9904"),
    "ph5": X("アカウント管理センター", "", "アカウント管理センター", "", "support@account-jp-check.example", "02-0000-9905"),
    "ph6": X("택배 배송안내", "", "빠른택배", "", "notice@fast-parcel-kr.example", "02-0000-9906"),
    "sp1": X("오피스몰", "", "오피스몰", "", "marketing@officemall.example", "02-0000-9911"),
    "sp2": X("Growth Team", "", "RankUp Digital", "", "hello@rankup-digital.example", "02-0000-9912"),
    "sp3": X("머니론", "", "머니론", "", "ad@moneyloan.example", "02-0000-9913"),
    "sp4": X("CloudTalk 이벤트", "", "CloudTalk", "", "event@cloudtalk.example", "02-0000-9914"),
    "sp5": X("Cloud Weekly", "", "Cloud Weekly", "", "newsletter@cloudweekly.example", "02-0000-9915"),
    "sp6": X("경품 이벤트팀", "", "럭키박스", "", "win@luckybox-event.example", "02-0000-9916"),
}
TARGET = {"자료제출요청": 3, "수정재전송요청": 2, "회신요청": 5, "검토승인요청": 3, "일정참석": 2, "조치요청": 3,
          "회신": 2, "공유": 2, "공지": 1, "기타": 13}  # 받은 메일의 주 유형 개수


def m(t, frm, subj, body, types, tasks=(), att=(), to=None, cc=(), urgent=False, fu=False,
      tags=(), th=None, men=None, day="11-05", raw=False, lang="ko"):
    MAILS.append(dict(t=t, frm=frm, subj=subj, body=body, types=types, tasks=list(tasks), att=list(att),
                      to=list(to or ["me"]), cc=list(cc), urgent=urgent, fu=fu, tags=list(tags),
                      th=th, men=men, day=day, raw=raw, lang=lang))


# ───────────────────────── 영어 10통 (할 일 7) ─────────────────────────

m("0905", "olv", "Updated migration runbook needed today",
  """Thanks for the walkthrough yesterday. Our change advisory board meets tomorrow morning and they asked for the latest version of the warehouse system migration runbook, including the rollback steps you mentioned.

Could you send us the updated runbook by EOD? A PDF is fine.

The board will also look at the network diagram, but we already have that from last week.""",
  "자제", [("업데이트된 이전 런북(롤백 절차 포함) 송부", "pdf", "by EOD", "11-05 18:00")],
  tags=["영어메일", "영문표현"], lang="en")

m("0912", "rkp", "Cutover window confirmation",
  """We are finalizing the resource plan for the database cutover. Two windows are still open on our side: Saturday 11/14 22:00–06:00 or Saturday 11/21 22:00–06:00.

Please confirm which window works for your team by noon. Our on-call roster has to be published this afternoon.""",
  "회요", [("DB 전환 작업 일정(11/14 · 11/21 중) 회신", "없음", "by noon", "11-05 12:00")],
  tags=["영어메일", "영문표현"], lang="en")

m("0930", "mts", "Draft SOW for Phase 2 network upgrade",
  """Attached is the draft statement of work for the Phase 2 network upgrade. Sections 3 (scope) and 5 (acceptance criteria) changed the most since our last call.

Please review the draft SOW and share your comments by the end of this week so that we can submit the final version to procurement on Monday.""",
  "검승", [("2단계 네트워크 고도화 SOW 초안 검토 후 의견 회신", "없음", "by the end of this week", "11-06 18:00")],
  att=["Phase2_SOW_draft_v0.3.docx"], tags=["영어메일", "영문표현", "상대날짜"], lang="en")

m("1004", "olv", "Joint workshop invitation – data platform roadmap",
  """We'd like to invite you to a joint workshop on the data platform roadmap for 2027.

Date/time: Monday next week at 2:00 PM (KST), about 90 minutes
Location: Northwind Seoul office, 12F Meeting Room B (Teams link for remote attendees)

Please attend on Monday next week at 2:00 PM. Our CIO will join for the first half.""",
  "일정", [("데이터 플랫폼 로드맵 공동 워크숍 참석", "없음", "Monday next week at 2:00 PM", "11-09 14:00")],
  tags=["영어메일", "영문표현", "상대날짜"], lang="en")

m("1021", "rkp", "RE: Cost sheet for managed services",
  """Thank you for the cost sheet. Our finance team could not open the embedded tables in the PDF, and two line items (backup storage and DR site) seem to be missing.

Could you add those two items and resend the cost sheet in Excel format by next week?""",
  "수정", [("관리 서비스 비용표에 백업 스토리지 · DR 항목 추가 후 엑셀로 재송부", "xlsx", "by next week", "11-13 18:00")],
  th="cost-sheet", tags=["영어메일", "영문표현", "상대날짜"], lang="en")

m("1040", "mts", "Headcount for the on-site training",
  """We are arranging the on-site Kubernetes operations training for your engineers in December. The venue holds up to 20 people.

Please let me know how many people from your team will join by 10 November. Names are not needed yet.""",
  "회요", [("12월 쿠버네티스 운영 교육 참석 인원 회신", "없음", "by 10 November", "11-10 18:00")],
  tags=["영어메일"], lang="en")

m("1105", "olv", "Weekly status report – week 45",
  """Please find this week's status report below for your reference.

- Inventory module: UAT 82% complete, 3 open defects (all minor)
- Interface with the carrier API: performance test scheduled next Wednesday
- Risks: none new this week

No action is needed from your side. We will share the next report next Thursday.""",
  "공유", tags=["영어메일", "TO정보공유"], lang="en")

m("1130", "rkp", "RE: Firewall rule change request",
  """As requested, we have completed the firewall rule change for the new monitoring subnet. The rules were applied at 08:40 today and our tests passed.

The change ticket CHG-2231 is now closed.""",
  "회신", th="fw-change", tags=["영어메일", "완료회신"], lang="en")

m("1150", "mts", "Introducing our new edge security appliance",
  """We are excited to introduce the TW-9000, our new edge security appliance with built-in zero-trust access.

Join our launch webinar on November 18 to see a live demo. Register now and receive a free evaluation unit.""",
  "기타", tags=["영어메일", "사외행사"], lang="en")

m("1310", "olv", "Change request CR-118 – approval needed",
  """The change request CR-118 (moving the nightly batch window from 01:00 to 02:30) is attached. Our operations team has already reviewed the impact.

Please approve the change request before our sync on Tuesday at 10:00 AM, so that we can schedule it for the following weekend.""",
  "검승", [("CR-118 야간 배치 시간 변경 요청 승인", "없음", "before our sync on Tuesday at 10:00 AM", "11-10 10:00")],
  att=["CR-118.pdf"], tags=["영어메일", "영문표현"], lang="en")

# 시간대를 밝힌 기한(라벨 가이드 4절): 11/5(목) 09:00 KST는 PT로 11/4(수) 16:00(11/1 서머타임 끝, PST -8).
# 'Thursday 5 PM PT' = 11/5 17:00 PST = 11/6(금) 10:00 KST
m("0900", "jnl", "Load test results – need your sign-off data",
  """We finished the second round of load tests on the shared API gateway. To close the report we still need your team's peak traffic profile for December.

Could you send the traffic profile (CSV is fine) by 5 PM PT Thursday? Our release review is Friday morning Pacific time.""",
  "자제", [("12월 피크 트래픽 프로파일 송부", "csv", "by 5 PM PT Thursday", "11-06 10:00")],
  tags=["영어메일", "영문표현", "시간대변환"], lang="en")

m("1230", "olv", "Invitation to the shared project workspace",
  """As discussed in yesterday's kickoff, we have set up a shared workspace for the data platform project. All design documents and meeting notes will be kept there from now on.

You should have received an invitation from our collaboration portal. Please accept the invitation and sign in by Friday so that we can assign document owners on Monday.""",
  "조치", [("공동 프로젝트 워크스페이스 초대 수락 · 로그인", "없음", "by Friday", "11-06 18:00", "Northwind 협업 포털")],
  tags=["영어메일", "영문표현"], lang="en")

# ───────────────────────── 일본어 9통 (할 일 7) ─────────────────────────

m("1315", "tnk", "保守契約更新に関するご回答のお願い",
  """来年度の保守契約更新について、契約形態（年額／月額）のご希望を伺っております。

お手数ですが、１１月１０日（火）までにご回答いただけますでしょうか。""",
  "회요", [("내년도 유지보수 계약 형태(연액 · 월액) 회신", "없음", "１１月１０日（火）までに", "11-10 18:00")],
  tags=["일본어메일"], lang="ja")

m("0920", "szk", "お見積書送付のお願い",
  """先日お打ち合わせいたしましたクラウド監視サービスの件で、社内稟議にかけるためお見積書が必要となりました。

お手数ですが、明日までにお見積書をご送付いただけますでしょうか。""",
  "자제", [("클라우드 모니터링 서비스 견적서 송부", "없음", "明日までに", "11-06 18:00")],
  tags=["일본어메일"], lang="ja")

m("0945", "tnk", "移行リハーサル日程のご確認",
  """来月予定しております移行リハーサルについて、弊社の作業員の手配を進めております。

11月28日（土）と12月5日（土）のどちらがご都合よろしいか、本日中にご返信いただけますと幸いです。""",
  "회요", [("이전 리허설 일정(11/28 · 12/5 중) 회신", "없음", "本日中に", "11-05 18:00")],
  tags=["일본어메일"], lang="ja")

m("1015", "ymd", "要件定義書（第2版）のご確認",
  """要件定義書の第2版を添付いたします。前回いただいたご指摘はすべて反映しております。

内容をご確認のうえ、来週月曜までにご意見をいただけますでしょうか。""",
  "검승", [("요구사항 정의서 2판 검토 후 의견 회신", "없음", "来週月曜までに", "11-09 18:00")],
  att=["要件定義書_第2版.docx"], tags=["일본어메일", "상대날짜"], lang="ja")

m("1050", "tnk", "定例会議のご案内",
  """次回の定例会議を下記のとおり開催いたします。

日時：11月12日（木）15時～16時
場所：オンライン（Teams）

ご多忙のところ恐縮ですが、ご出席くださいますようお願いいたします。""",
  "일정", [("정례 회의 참석", "없음", "11月12日（木）15時", "11-12 15:00")],
  tags=["일본어메일"], lang="ja")

m("0902", "szk", "発注数量のご確認（至急ではありません）",
  """ライセンスの追加発注について、数量を最終確認させてください。前回は30ライセンスと伺っております。

変更がある場合もない場合も、午前中にご連絡いただけますと助かります。""",
  "회요", [("라이선스 추가 발주 수량 확정 회신", "없음", "午前中に", "11-05 12:00")],
  tags=["일본어메일"], lang="ja")

m("1120", "ymd", "Re: 運用手順書の修正について",
  """運用手順書をお送りいただきありがとうございます。障害時の連絡先一覧が旧版のままになっているようです。

お手数ですが、連絡先一覧を最新のものに差し替えて、今週中に修正版を再送していただけますでしょうか。""",
  "수정", [("운영 절차서 연락처 목록 최신화 후 수정본 재송부", "없음", "今週中に", "11-06 18:00")],
  th="ops-manual", tags=["일본어메일", "상대날짜"], lang="ja")

m("1400", "tnk", "進捗報告（11月第1週）",
  """今週の進捗をご報告いたします。

・基盤構築：計画どおり完了
・アプリ移行：12本中9本完了、残り3本は来週完了予定
・課題：特になし

ご確認のほどよろしくお願いいたします。特にご対応いただく事項はございません。""",
  "공유", tags=["일본어메일", "TO정보공유"], lang="ja")

m("1430", "szk", "Re: 請求書の再発行について",
  """ご依頼いただいた請求書の再発行が完了いたしました。宛名を「LG CNS クラウド転換1チーム」に修正しております。

本日、原本を郵送いたしました。""",
  "회신", th="invoice-jp", tags=["일본어메일", "완료회신"], lang="ja")

# ───────────────────────── 스팸 · 피싱 12통 (할 일 0, 기타, urgent False) ─────────────────────────

m("0810", "ph1", "[보안 경고] 메일 계정이 24시간 후 잠깁니다",
  """[LG CNS 메일 보안센터]

비정상적인 로그인 시도가 감지되어 귀하의 메일 계정이 24시간 후 잠길 예정입니다.
계정 잠금을 막으려면 아래 링크에서 사번과 비밀번호로 본인 확인을 완료해 주세요.

▶ 본인 확인하기: http://lgcns-mail-verify.example/login

본 메일은 발신 전용입니다.""",
  "기타", tags=["피싱"], raw=True)

m("0822", "ph2", "Action required: your mailbox storage is full",
  """Your Microsoft 365 mailbox has reached 99% of its storage limit. Incoming messages will be rejected.

Verify your account within 24 hours to get 50 GB of free additional storage:
https://m365-support-center.example/verify

Microsoft 365 Support Team""",
  "기타", tags=["피싱", "영어메일"], raw=True)

m("0840", "ph3", "[한빛은행] 정산 계좌 변경 안내 및 미결제 대금 송금 요청",
  """안녕하세요, 한빛은행 정산팀입니다.

내부 감사로 기존 정산 계좌가 동결되어 이번 달부터 아래 계좌로 대금을 받습니다.
미결제 대금 4,850만 원을 금일 중 아래 계좌로 송금해 주시기 바랍니다.

새 계좌: 해외은행 123-456-789012 (예금주: HB Settlement Ltd.)

기존 담당자에게는 따로 연락하지 마시고 이 메일로만 회신 부탁드립니다.""",
  "기타", tags=["피싱"], raw=True)

m("0855", "ph4", "급한 부탁",
  """이 팀장, 회의 중이라 전화를 못 받네. 고객사 임원 선물로 상품권이 급히 필요해.
온라인으로 10만 원권 20장 사서 카드 뒷면 번호를 사진 찍어서 이 메일로 보내 줘. 비용은 내가 나중에 정산할게.

한상우""",
  "기타", tags=["피싱"], raw=True)

m("0915", "ph5", "【重要】アカウント停止のお知らせ",
  """お客様のアカウントは不正利用の可能性があるため一時停止されました。

本日中に以下のリンクから再認証を行ってください。期限を過ぎるとアカウントは削除されます。
https://account-jp-check.example/verify

アカウント管理センター""",
  "기타", tags=["피싱", "일본어메일"], raw=True)

m("1000", "ph6", "[배송 보류] 주소 확인이 필요합니다",
  """고객님의 택배가 주소 불일치로 배송 보류 중입니다.
48시간 안에 아래 링크에서 주소와 휴대폰 번호를 확인하지 않으면 반송 처리됩니다.

주소 확인: http://fast-parcel-kr.example/check""",
  "기타", tags=["피싱"], raw=True)

m("1110", "sp6", "축하합니다! 최신 노트북 당첨 안내",
  """축하합니다! 11월 고객 감사 이벤트에서 최신 노트북에 당첨되셨습니다.
경품 발송을 위해 오늘 자정까지 아래 링크에서 성함 · 주민등록번호 · 주소를 입력해 주세요.

http://luckybox-event.example/claim""",
  "기타", tags=["피싱"], raw=True)

m("0830", "sp1", "[광고] 사무용 의자 · 책상 최대 60% 할인",
  """(광고) 오피스몰 블랙프라이데이 특가!
사무용 의자 · 책상 · 수납장 최대 60% 할인, 이번 주 금요일까지만 진행합니다.
지금 바로 주문하세요.

수신을 원치 않으시면 수신 거부를 눌러 주세요.""",
  "기타", tags=["스팸"], raw=True)

m("0950", "sp2", "Rank your website #1 on Google",
  """Hi there,

We noticed your website is not ranking on the first page of Google. Our SEO experts can get you to #1 in 30 days, guaranteed.

Reply by Friday to get 40% off our premium package.

Unsubscribe""",
  "기타", tags=["스팸", "영어메일"], raw=True)

m("1200", "sp3", "(광고) 직장인 전용 저금리 대출 승인 안내",
  """(광고) 직장인이시라면 서류 없이 최대 1억 원까지 당일 승인!
상담 신청은 오늘까지 우대 금리가 적용됩니다.

수신 거부: 080-000-0000""",
  "기타", tags=["스팸"], raw=True)

m("1330", "sp4", "[CloudTalk] 클라우드 비용 절감 웨비나 — 선착순 100명 커피 쿠폰",
  """클라우드 비용을 30% 줄이는 방법, 궁금하지 않으세요?
11월 19일(목) 오후 2시 온라인 웨비나에 지금 등록하시면 선착순 100명께 커피 쿠폰을 드립니다.

등록하기: https://cloudtalk.example/webinar

수신을 원치 않으시면 수신 거부를 눌러 주세요.""",
  "기타", tags=["스팸"], raw=True)

m("1500", "sp5", "Cloud Weekly #212: Serverless trends, FinOps tips",
  """This week in Cloud Weekly:

1. Serverless adoption hits a new high
2. Five FinOps tips you can apply today
3. Interview: scaling Kubernetes at a global retailer

You are receiving this because you subscribed to Cloud Weekly. Unsubscribe anytime.""",
  "기타", tags=["스팸", "영어메일"], raw=True)

# ───────────────────────── 비교용 3통 ─────────────────────────
# 실제 거래처(한빛은행, 조직도 도메인)의 포털 등록 요청: 사외 · 링크 · 로그인이 있어도 진행 중인 업무 요청이라 할 일이다
m("1415", "jmh", "[한빛은행] 2단계 검수 확인서 협력사 포털 등록 요청",
  """지난주 완료된 2단계 이행 건의 검수 절차를 진행하려고 합니다.

검수 확인서에 서명하신 뒤 협력사 포털(https://partner.hanbitbank.example)에 로그인하셔서 '검수 > 확인서 등록' 메뉴로 올려 주세요.
대금 지급 일정 때문에 11/10(화)까지 등록 부탁드립니다.""",
  "조치", [("2단계 검수 확인서 서명 후 협력사 포털 등록", "없음", "11/10(화)까지", "11-10 18:00", "한빛은행 협력사 포털")])

# 사내 보안 메일
# 사내 시스템 · 정보보안팀이 보낸 메일은 스팸 · 피싱이 아니다. 기한 · 불이익을 밝힌 계정 조치는 할 일이다(라벨 가이드 2절)

m("0800", "his", "[IT운영] 사내 계정 비밀번호 만료 안내",
  """사내 통합계정 비밀번호가 11/9(월)에 만료됩니다.
만료 전까지 사내 포털(Portal > 내 정보 > 비밀번호 변경)에서 변경하지 않으면 계정이 잠기고, 잠금 해제는 IT 헬프데스크 방문으로만 가능합니다.

11/9(월)까지 비밀번호를 변경해 주시기 바랍니다.""",
  "조치", [("사내 통합계정 비밀번호 변경", "없음", "11/9(월)까지", "11-09 18:00", "사내 포털")])

m("1530", "bsm", "[정보보안] '계정 잠김' 사칭 피싱 메일 주의",
  """최근 사내 메일 보안센터를 사칭해 '24시간 후 계정이 잠긴다'며 로그인 링크를 누르게 하는 피싱 메일이 돌고 있습니다.

사내 시스템은 메일로 비밀번호 입력을 요구하지 않습니다. 의심 메일은 열지 말고 삭제해 주시기 바랍니다.
이미 링크에 비밀번호를 입력하신 분은 정보보안팀(내선 2101)으로 연락 주세요.""",
  "공지", to=["@all"], tags=["지목없는당부"])
