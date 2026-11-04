// [FE 임시] 대시보드 데이터 응답 형식.
// 구조도 8절과의 차이 · 정해야 할 것: docs/20_frontend/be3_contract_comparison.md (BE-3는 이 비교로 계약을 정한 뒤 구현한다)
// backend에 FE용 응답 스키마가 아직 없다(backend/app/schemas 비어 있음, BE-3 예정).
// 구조도 8절 `GET /dashboard`([제안])는 요약 + 칸별 {key, count, overdue, new, task_ids} 형식이라 이 형식과 다르다.
// 이 파일은 모의 데이터와 FE 집계를 위해 FE가 임시로 가정한 형식이며 합의된 계약이 아니다.
// 필드 이름 · 값은 backend 모델(backend/app/models/{mail,user}.py)을 따랐다. 시각은 +09:00이 붙은 ISO 문자열(D47).

export interface ProvisionalContact {
  email: string;
  name: string | null;
  position: string | null;
  is_superior: boolean;
  is_favorite: boolean;
}

export interface ProvisionalMail {
  id: number;
  source_id: string;
  direction: 'received' | 'sent';
  sender: string;
  subject: string;
  received_at: string;
  category: string | null;
}

export interface ProvisionalTask {
  id: number;
  mail_id: number;
  text: string;
  due_at: string | null;
  due_source: string;
  status: string;
  seen_at: string | null;
}

export interface ProvisionalDashboardResponse {
  as_of: string;
  contacts: ProvisionalContact[];
  mails: ProvisionalMail[];
  tasks: ProvisionalTask[];
}
