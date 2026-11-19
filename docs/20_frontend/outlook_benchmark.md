# 아웃룩 벤치마킹 — 메일 쓰기 리본 · 읽기 화면 번역 · 요약

> 상태: 조사 완료(구현 전) · 조사 · 결정 요청: 문규남 · 갱신: 2026-11-20
> 근거: 새 Outlook(Windows, 11-20 실제 앱 화면을 직접 열어 확인) · Microsoft 지원 문서 · Microsoft Graph 문서(맨 아래 출처)
> 목적: "아웃룩과 가장 비슷한 경험". 액션 아이템(업무) + 요약이 핵심이고(제품 철학), 쓰기 화면은 아웃룩 리본 구조를 옮긴다.

## 1. 새 메일 쓰기 화면의 탭

탭 순서: 파일 · 홈 · 보기 · 도움말 · **메시지** · **삽입** · **텍스트 서식 지정** · 그리기 · **옵션**.
쓰기 칸: 보낸 사람 ▾ · 받는 사람(오른쪽 끝 '숨은 참조') · 참조 · 제목 추가 · 본문, 위에 [보내기 ▾] · 민감도 레이블 · 삭제 · 새 창.

### 1.1 메시지 탭 (자주 쓰는 것을 한 줄에 모은 탭)
실행 취소 · 붙여넣기 · 서식 복사 · 글꼴 · 크기 · 굵게 · 기울임 · 밑줄 · 취소선 · 형광펜 · 글꼴 색 · 스타일 · 글머리 기호 · 번호 · 내어쓰기 · 줄 간격 · 서식 지우기 · … ·
주소록 확인 · 파일 첨부 ▾ · 링크 ▾ · 서명 ▾ · Teams 모임 · 받아쓰기 · 편집자 ▾ · 앱 · 중요도 높음(❗) · 중요도 낮음(↓) · 민감도 · 암호화 ▾ · 인쇄.

### 1.2 삽입 탭
| 버튼 | 내용(실제 앱) | 우리 지금 | 가져올지 |
|---|---|---|---|
| 파일 첨부 ▾ | 이 컴퓨터 찾아보기 · OneDrive · 업로드 및 공유 · 링크 · **제안된 파일**(최근 주고받은 첨부) | 파일 첨부(합 3MB 미만) | ✅ 3MB 넘는 파일은 Graph 업로드 세션(3~150MB). 제안된 파일은 나중 |
| 링크 ▾ | 본문에 링크 넣기(본문에 커서가 있을 때만 켜짐) | 없음 | ✅ |
| 서명 ▾ | 만든 서명 목록 + '서명…'(설정 열기). 서명이 없으면 '서명…'만 | 설정 서명 하나를 끝에 자동으로 붙임 | ✅ 넣기 · 고르기 · 자동 넣기 끄기 |
| 녹음/녹화 · 사진 · 그래픽 ▾ · 테이블 ▾ · 빠른 문서 요소 ▾ · Loop 구성 요소 · 앱 · 투표 · 설문 조사 예약 | HTML 본문에서만 켜짐 | 없음 | 사진 · 테이블만 서식 편집기 다음 단계, 나머지는 범위 밖 |

### 1.3 텍스트 서식 지정 탭
실행 취소 ▾ · 붙여넣기 ▾ · 서식 복사 · 글꼴(기본 Aptos) · 크기(기본 12) · **굵게 · 기울임 · 밑줄 · 취소선** · **형광펜 ▾ · 글꼴 색 ▾** · 서식 지우기 · 대소문자 ▾ · 위 첨자 · 아래 첨자 · 스타일 ▾ · 인용 · **글머리 기호 · 번호 매기기 · 내어쓰기 · 들여쓰기 · 맞춤 ▾ · 줄 간격 ▾** · 왼쪽→오른쪽 · 오른쪽→왼쪽.
- 우리: 본문이 일반 텍스트 칸(`Compose.tsx` `<textarea>`), 보낼 때는 HTML로 바꿔 보낸다(`backend/app/services/sending.py`).
- 가져올 것(굵게 표시 = 1차): 서식 있는 편집기로 바꾸고 HTML을 그대로 보낸다. 붙여넣은 HTML은 안전하게 거른다.

### 1.4 옵션 탭
| 버튼 | 내용 | 우리 지금 | 가져올지 |
|---|---|---|---|
| 편집자 ▾ · 접근성 확인 | 맞춤법 · 문체 검사 | [다듬기](polish) | 다듬기로 대신 |
| 예약 전송 | 보낼 시각 지정 | 있음(예약 보내기) | — |
| 메일 병합 시작 | 여러 받는 사람에게 개별 발송 | 없음 | 범위 밖 |
| 필드 표시 ▾ | 숨은 참조 등 칸 보이기 | 참조 · 숨은 참조 펼치기 | — |
| 추적 ▾ | 읽음 · 배달 확인 요청 | 없음 | 나중(Graph `isReadReceiptRequested` · `isDeliveryReceiptRequested`) |
| **중요도 높음 · 중요도 낮음** | 메시지 탭에도 있음 | 없음 | ✅ Graph `importance`(low · normal · high), 받은 메일도 읽어 목록에 표시 |
| 민감도 · 암호화 ▾ | 조직 레이블 · 암호화 | 없음 | 범위 밖 |
| 초안 인쇄 · 일반 텍스트로 작성(T) · 초안 저장(Ctrl+S) · 초안을 파일로 저장 · 자동 서식 옵션 · 메시지 옵션 대화 상자 · 메일 템플릿 옵션 | 아이콘 툴팁으로 확인 | 템플릿 있음, 초안 자동 저장 없음 | 초안 저장은 나중, 일반 텍스트 전환은 편집기와 함께 |

## 2. 읽기 화면

| 기능 | 실제 앱 | 문서 | 우리 지금 | 가져올 것 |
|---|---|---|---|---|
| **요약** | 제목 오른쪽 **[이 전자 메일 요약]** 버튼(Copilot) | 요약이 메일 위에 뜬다. 일부 요약은 스레드 속 메일로 가는 번호 인용이 붙는다 | 업무 + 근거 형광펜만. 메일 요약은 캐치봇 명령(T20)에서만 | ✅ 분류 때 요약을 같이 만들어(호출 수 그대로) **요약 → 업무 → 원문** 순서. 근거 형광펜 = 번호 인용 역할 |
| **번역** | 메시지 머리 **[…] → 번역** | 본문을 번역문으로 바꾸고 '원본 보기'로 되돌림, 일부 선택 번역, 자동 번역 설정, 40자 미만은 번역하지 않음, Microsoft Translator 사용 | 없음 | ✅ [번역] · [원본 보기] 전환. 엑사원으로 누를 때만 1회(외부 호출은 api.exaone.ai만), 결과 저장해 다시 부르지 않음. 자동 번역은 하루 100회 한도 때문에 나중 |
| 메시지 머리 버튼 | 이모지 반응 · 회신 · 전체 회신 · 전달 · 앱 · […](기타 회신 작업 · 삭제 · 읽지 않음 · 플래그 · 작업 사용자 지정 · 정크 · 피싱 신고 · 인쇄 · 번역 · 몰입형 리더 · 보기 · 다른 이름으로 저장 · 고급 작업) | — | 회신 · 전체 회신 · 전달 · 옮기기 | 번역만 1차 |

## 3. 순서(제안)
1. 요약(분류 때 같이 만들기 + 읽기 화면 맨 위)
2. 번역 버튼
3. 중요도 높음 · 낮음(보내기 · 받기)
4. 서식 있는 편집기(1.3 굵은 항목) + 링크 · 서명 넣기 · 고르기
5. 큰 첨부(업로드 세션)

## 출처
- 새 Outlook 실제 화면(11-20, Windows, 새 메일 · 삽입 · 텍스트 서식 지정 · 옵션 탭과 툴팁, 읽기 화면 […] 메뉴). 개인 메일이 보이는 캡처는 레포에 넣지 않았다.
- [Translator in Outlook](https://support.microsoft.com/office/3d7e12ed-99d6-406e-a453-b9db0d9653fa)
- [Summarize an email thread with Copilot in Outlook](https://support.microsoft.com/office/summarize-an-email-thread-with-copilot-a79873f2-396b-46dc-b852-7fe5947ab640)
- [Customize your email message in Outlook on the web](https://support.microsoft.com/en-us/outlook/customize-your-email-message-in-outlook-on-the-web)
- [Change the message format to HTML / plain text](https://support.microsoft.com/office/change-the-message-format-to-html-rich-text-format-or-plain-text-in-outlook-338a389d-11da-47fe-b693-cf41f792fefa)
- [Create and add an email signature in Outlook](https://support.microsoft.com/en-us/office/add-a-signature-to-messages-8ee5d4f4-68fd-464a-a1c1-0e1c80bb27f2)
- [Graph message resource](https://learn.microsoft.com/graph/api/resources/message) · [Create message](https://learn.microsoft.com/en-us/graph/api/user-post-messages) · [Large attachments](https://learn.microsoft.com/en-us/graph/outlook-large-attachments)
