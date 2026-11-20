// 모의 명령 해석(규칙) — mockClient의 runAgentCommand가 쓴다(components.md 4.4 · FE-7). 화면(features/agent)은 이 파일을 모른다.
// 실제 서비스에서는 backend가 AI `/agent/plan`을 불러 받는 응답(ai/app/schemas/agent.py PlanResponse)을 여기서 같은 모양으로 만든다.
// 이 결과를 agentExecutor.ts가 backend executor.py처럼 AgentResult로 바꾼다.
//
// 규칙은 실제 규칙(ai/app/agent/rules_v1.py v1.4)의 일부만 옮긴 것이다. 모의가 실제로 처리할 수 있는 행동만 알아듣는다:
//   T01 오늘_요약 · T02 미처리_조회 · T03 일괄_완료 · T04 되돌리기 · T05 나중에_처리 · T06 무응답_확인 · T07 회신_초안
// 나머지(T08~T14)와 규칙에 안 걸린 문장은 엑사원 경로를 흉내 내어(3초 넘게 기다린 뒤) '지원하지 않는 요청'으로 끝낸다.
// 실제 규칙은 '점심 메뉴 추천해줘' 같은 업무 밖 문장을 모델 없이 바로 거절하지만, 와이어프레임 V-17이 엑사원 대기 문구를
// 확인하는 장면이라 모의는 모델 경로로 보낸다.
// 값이 빠진 명령(때 없는 '미뤄', 대상 없는 '다 처리했어')은 여기서 거절하지 않고 빈 칸으로 넘긴다. 되묻기는 executor가 한다(backend와 같게).

// ── AI 계약(ai/app/schemas/agent.py)과 같은 모양. 칸 이름도 서버 그대로(snake_case) ──

export type ActionId = 'T01' | 'T02' | 'T03' | 'T04' | 'T05' | 'T06' | 'T07' | 'T08' | 'T09' | 'T10' | 'T11' | 'T12' | 'T13' | 'T14' | 'T17';

export interface ActionSpec {
  id: ActionId;
  name: string;
  description: string | null;
}

export interface PlanContext {
  /** 시간대 없는 KST 시각(예: 2026-11-06T10:42:00) */
  now: string;
  selected_mail_ids: string[];
  last_result_ids: string[];
}

export interface PlanRequest {
  text: string;
  actions: ActionSpec[];
  context: PlanContext;
}

export type PlanCategory = '회신' | '요청' | '검토' | '공지' | '기타';

export interface PlanTarget {
  sender: string | null;
  category: PlanCategory | null;
  date_range: { start: string; end: string } | null;
  keyword: string | null;
  mail_ids: string[];
  awaiting_reply: boolean;
}

export interface PlanResponse {
  action: ActionId | null;
  action_name: string | null;
  target: PlanTarget;
  params: Record<string, string | number | boolean | null>;
  source: 'rule' | 'model';
  reason: 'unsupported' | 'ambiguous' | null;
  candidates: string[];
  prompt_version: string | null;
  rules_version: string;
  fallback: string | null;
}

/** 행동 목록(docs/40_ai/detail.md 2절). backend 행동 레지스트리가 AI에 보내는 것과 같은 이름 */
export const ACTIONS: readonly ActionSpec[] = [
  { id: 'T01', name: '오늘_요약', description: '오늘 할 일을 요약해 보여 준다' },
  { id: 'T02', name: '미처리_조회', description: '조건에 맞는 미처리 업무를 보여 준다' },
  { id: 'T03', name: '일괄_완료', description: '대상 업무를 완료로 바꾼다' },
  { id: 'T04', name: '되돌리기', description: '방금 한 행동을 되돌린다' },
  { id: 'T05', name: '나중에_처리', description: '대상 업무를 정한 시각까지 미룬다' },
  { id: 'T06', name: '무응답_확인', description: '보낸 메일 중 답장이 없는 것을 보여 준다' },
  { id: 'T07', name: '회신_초안', description: '고른 메일의 회신 초안을 만든다' },
  { id: 'T08', name: '근거_설명', description: '업무로 잡힌 이유를 설명한다' },
  { id: 'T09', name: '리마인드_설정', description: '알림 시각을 바꾼다' },
  { id: 'T10', name: '제외_처리', description: '대상을 업무에서 뺀다' },
  { id: 'T11', name: '중요_발신자_지정', description: '발신자를 상급자 · 즐겨찾기로 정한다' },
  { id: 'T12', name: '초안_작성', description: '새 메일 초안을 쓴다' },
  { id: 'T13', name: '기한_보기', description: '기한을 모아 보여 준다' },
  { id: 'T14', name: '템플릿_전송', description: '템플릿 메일을 보낸다' },
  { id: 'T17', name: '사람_조회', description: '그 사람이 누구고 무엇을 보냈는지 보여 준다' },
];

/** 모의가 실제로 끝까지 처리하는 행동. 이 밖의 행동은 고르지 않는다(있는 척하지 않음) */
export const MOCK_SUPPORTED: readonly ActionId[] = ['T01', 'T02', 'T03', 'T04', 'T05', 'T06', 'T07', 'T17'];

export const MOCK_RULES_VERSION = 'agent_rules_v1.4-fe-mock';
export const MOCK_PROMPT_VERSION = 'agent_v1-fe-mock';

/** 모의 응답 지연. 규칙 경로는 짧게, 엑사원 경로는 3초를 넘겨 '엑사원이 해석하는 중' 문구가 보이게 한다 */
export const MOCK_DELAY_MS = { rule: 500, model: 5000 } as const;

// ── 시각(KST, 시간대 없는 ISO 글자) ──

const KST_OFFSET_MS = 9 * 3600_000;
const DAY_MS = 24 * 3600_000;
const pad = (n: number) => String(n).padStart(2, '0');

/** epoch 밀리초 → 시간대 없는 KST 시각 글자(초까지) */
export function kstNaive(ms: number): string {
  const d = new Date(ms + KST_OFFSET_MS);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}

/** 시간대 없는 KST 시각 글자 → epoch 밀리초. 형식이 틀리면 null */
export function parseKstNaive(text: string): number | null {
  const ms = Date.parse(`${text.length === 10 ? `${text}T00:00:00` : text}+09:00`);
  return Number.isNaN(ms) ? null : ms;
}

function kstDay(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS);
}

function kstAt(day: number, hour: number, minute: number): number {
  return day * DAY_MS - KST_OFFSET_MS + (hour * 60 + minute) * 60_000;
}

/** 0 = 일요일 … 6 = 토요일 */
function kstWeekday(day: number): number {
  return (((day + 4) % 7) + 7) % 7;
}

// ── 규칙(rules_v1.py에서 옮긴 부분) ──

const TITLES = '팀장|책임|선임|차장|부장|과장|대리|사원|사업단장|담당|상무|전무|이사|매니저|프로';
const SENDER = new RegExp(`([가-힣]{1,4})\\s?(${TITLES})\\s?님?`);
const CATEGORY = /(회신|요청|검토|공지|기타)\s*(?:메일|건|업무)|(회신|요청|검토|공지)\s*(?:은|는|도|들은?)?\s*(?:다|전부|모두|싹)(?:\s|$)/;
const KEYWORD = /([가-힣A-Za-z0-9]{2,})\s*(?:건(?:은|는|을|를|도|이|만)?|관련(?:해서|된|한|으로|하여)?)(?=\s|$)/g;
const NOT_KEYWORD = new Set(['이번', '다음', '오늘', '내일', '방금', '모든', '전체', '남은', '그', '이', '공지', '회신', '요청', '검토', '기타',
  '어제', '아까', '메일', '업무', '처리', '완료', '미처리', '선택한']);
const TITLE_WORD = new RegExp(`(?:${TITLES})님?$`);
const SELECT_REF = /(?<![가-힣])(?:이거|이것|이건|이걸|이게|요거|요것|요건)|선택한|선택된|고른|체크한|(?:^|\s)이\s+(?:메일|건|거|것)/;
const LAST_REF_MANY = /그\s*\d+\s*(?:건|개|통)|(?:그|저)\s*(?:메일|것|거|건)들|(?:방금|아까)\s*(?:목록|나온|본|뜬|찾은)/;

const PATTERNS: Partial<Record<ActionId, RegExp>> = {
  T04: /취소|되돌려|되돌리|원래대로|원상\s*복구|복구|복원|없던\s*(?:걸로|일로)|(?:원래|이전|직전|방금|아까)\s*(?:\S+\s*){0,2}?돌려\s*(?:놔|놓|줘|둬)/,
  T03: /(?:처리|완료|끝|마무리|해결)\s*(?:했|됐|냈|함|완료)|(?:끝냈|마쳤|끝났|다\s*했)|완료\s*(?:해|처리|로|표시|체크|상태로)|^\s*(?:이거|이것|그거|요거|이건)\s*(?:는|은)?\s*(?:다\s*)?완료/,
  T05: /다시\s*(?:알려|띄워|보여|올려)|나중에|이따가?(?:\s|$)|미뤄|미루|미룰|연기\s*(?:해|시켜|좀)|스누즈|보류|(?:로|으로)\s*넘겨|(?:에|때)\s*(?:다시\s*)?알려\s*(?:줘|주세요|줄래)/,
  T06: /(?:답장|회신|답변|답|응답)\s*(?:이)?\s*(?:안\s*(?:온|왔|오|준)|없는|없어|못\s*받)|무응답|(?:답|회신|답장)\s*(?:을|를)?\s*기다리는/,
  T07: /(?:회신|답장|답변)\s*(?:은|을|를|용)?\s*(?:초안|문안|문구|드래프트)|(?:답장|회신|답변|답)\s*(?:좀\s*)?(?:써|작성|만들|잡아)|(?:답장|회신)\s*(?:좀\s*)?해\s*(?:줘|주세요|줄래)/,
  T01: /(?:오늘|금일|내일).*(?:뭐\s*(?:해야|있)|할\s*(?:일|거|것)|해야\s*할|요약|정리해서\s*(?:보여|알려))|하루\s*요약|브리핑/,
  // T17은 서버에서는 엑사원이 고른다. 모의는 '이름 직급' + 누구 · 뭐라고 했 · 보낸 메일만 알아듣는다(AI-44)
  T17: new RegExp(`(?:${TITLES})\\s?님?\\s?(?:이|가|은|는|이랑)?\\s?(?:누구|(?:나한테|저한테|내게)?\\s?뭐라고\\s?(?:했|하)|(?:나한테|저한테|내게)?\\s?(?:보낸|보냈))`),
  T02: /(?:뭐|무엇|뭣)\s*(?:이|가)?\s*남았|(?:남은|미처리|안\s*끝난|밀린)\s*(?:업무|일|거|건)\s*(?:보여|알려|뭐|있|목록)/,
};
// 앞 행동이 걸리면 뒤 행동 후보를 지운다(rules_v1 BEATS에서 모의가 쓰는 것만)
const BEATS: Partial<Record<ActionId, readonly ActionId[]>> = {
  T04: ['T03', 'T05'],
  T03: ['T07', 'T06', 'T01', 'T02'],
  T05: ['T01', 'T02'],
  T06: ['T01', 'T02'],
  T01: ['T02'],
};
// '회의 취소 메일 써줘' · '구독 취소해줘'의 취소는 되돌리기가 아니다
const NOT_UNDO = /(?:구독|수신|회의|미팅|일정|약속|예약|주문|결제|신청|출장|발송|보낸\s*메일|참석)\s*(?:을|를|은|는)?\s*취소|취소\s*(?:메일|공지|안내|요청|건|관련)/;
// 부정 · 의문으로 끝나는 지시는 상태를 바꾸지 않는다('완료하지 마' · '다 처리했나?')
const NEGATED = /지\s*(?:마|말)|하면\s*안\s*(?:돼|되)|\?\s*$|(?:했|됐)(?:나|니|냐)\s*$/;

const MUTATING = new Set<ActionId>(['T03', 'T04', 'T05']);

// 기간 낱말 → 숫자('이틀 뒤' · '일주일 넘게'). 기간 뒤에 오는 말이 있을 때만 바꾼다(rules_v1 normalize의 일부)
const DAY_WORDS: Record<string, number> = { 하루: 1, 이틀: 2, 사흘: 3, 나흘: 4, 닷새: 5, 일주일: 7, '1주일': 7, 열흘: 10 };
const DAY_WORD = /(?<![가-힣\d])(하루|이틀|사흘|나흘|닷새|일주일|1주일|열흘)(?=\s*(?:이상|넘|뒤|후|째|지난|동안|있다가|지나))/g;

function normalize(text: string): string {
  return text.trim().replace(/\s+/g, ' ').replace(DAY_WORD, (_, w: string) => `${DAY_WORDS[w]}일`);
}

function hits(text: string): ActionId[] {
  const found = (Object.keys(PATTERNS) as ActionId[]).filter((id) => PATTERNS[id]!.test(text));
  let list = found;
  if (list.includes('T04') && NOT_UNDO.test(text) && !/되돌|원래대로|방금|아까/.test(text)) list = list.filter((a) => a !== 'T04');
  if (NEGATED.test(text.trim())) list = list.filter((a) => !MUTATING.has(a));
  for (const winner of [...list]) {
    for (const loser of BEATS[winner] ?? []) {
      if (list.includes(winner)) list = list.filter((a) => a !== loser);
    }
  }
  return list;
}

function emptyTarget(): PlanTarget {
  return { sender: null, category: null, date_range: null, keyword: null, mail_ids: [], awaiting_reply: false };
}

export function extractTarget(text: string, ctx: PlanContext): PlanTarget {
  const t = emptyTarget();
  const s = SENDER.exec(text);
  if (s) t.sender = `${s[1]} ${s[2]}`;
  const c = CATEGORY.exec(text);
  if (c) t.category = (c[1] ?? c[2]) as PlanCategory;
  if (SELECT_REF.test(text)) t.mail_ids = [...ctx.selected_mail_ids];
  else if (LAST_REF_MANY.test(text)) t.mail_ids = [...(ctx.last_result_ids.length ? ctx.last_result_ids : ctx.selected_mail_ids)];
  for (const m of text.matchAll(KEYWORD)) {
    const word = m[1]!;
    if (!NOT_KEYWORD.has(word) && !/^\d+$/.test(word) && !TITLE_WORD.test(word)) {
      t.keyword = word;
      break;
    }
  }
  return t;
}

const WEEKDAY_INDEX: Record<string, number> = { 일: 0, 월: 1, 화: 2, 수: 3, 목: 4, 금: 5, 토: 6 };
const MORNING = [8, 30] as const; // 리마인드 기본 시각(rules_v1 MORNING_DEFAULT)

/** 시각 표현('오후 3시' · '10시 반' · '9:30'). 앞에 오전 · 오후가 없고 1~7시면 업무 시간 기준 오후로 본다(dates.py) */
function findClock(text: string): [number, number] | null {
  const m = /(오전|오후|아침|저녁|밤)?\s*(\d{1,2})\s*(?:시(?!간)\s*(?:(\d{1,2})\s*분|(반))?|:(\d{2}))/.exec(text);
  if (!m) return null;
  let h = Number(m[2]);
  const mi = Number(m[3] ?? m[5] ?? (m[4] ? 30 : 0));
  if (h > 24 || mi > 59) return null;
  if ((m[1] === '오후' || m[1] === '저녁' || m[1] === '밤') && h < 12) h += 12;
  else if (m[1] === undefined && h >= 1 && h <= 7) h += 12;
  return [h % 24, mi];
}

/** 시각 없는 날짜의 시각: 오전 → 12:00, 오후 · 퇴근 → 18:00(dates.py), 그 밖(아침 · 아무 말 없음) → 08:30(rules_v1 remind_at) */
function vagueClock(text: string): [number, number] {
  if (/점심|정오|오전/.test(text)) return [12, 0];
  if (/오후|퇴근|저녁/.test(text)) return [18, 0];
  return [MORNING[0], MORNING[1]];
}

/**
 * T05 다시 볼 시각(rules_v1 remind_at의 일부). 모르면 null.
 * 'N분 · N시간 · N일 뒤', 오늘 · 내일 · 모레, (다음 주) X요일(오늘 제외 가장 가까운), 다음 주(월요일), 시각만 있으면 오늘(지났으면 내일).
 */
export function remindAt(text: string, nowMs: number): number | null {
  const rel = /(\d+)\s*(분|시간|일|주)\s*(?:뒤|후|있다가|지나서)/.exec(text);
  const today = kstDay(nowMs);
  if (rel) {
    const n = Number(rel[1]);
    if (rel[2] === '분') return nowMs + n * 60_000;
    if (rel[2] === '시간') return nowMs + n * 3600_000;
    const clock = findClock(text) ?? vagueClock(text);
    return kstAt(today + n * (rel[2] === '주' ? 7 : 1), clock[0], clock[1]);
  }
  let day: number | null = null;
  if (/모레/.test(text)) day = today + 2;
  else if (/내일/.test(text)) day = today + 1;
  else if (/오늘|이따/.test(text)) day = today;
  const wd = /(다음\s*주|이번\s*주|차주)?\s*([월화수목금토일])요일/.exec(text);
  if (day === null && wd) {
    const target = WEEKDAY_INDEX[wd[2]!]!;
    const now = kstWeekday(today);
    if (wd[1] && /다음|차주/.test(wd[1])) {
      const monday = today - ((now + 6) % 7) + 7;
      day = monday + ((target + 6) % 7);
    } else {
      day = today + ((target - now + 7) % 7 || 7);
    }
  }
  if (day === null && /다음\s*주|차주/.test(text)) day = today - ((kstWeekday(today) + 6) % 7) + 7;
  const clock = findClock(text);
  if (day === null) {
    if (!clock) return null;
    const at = kstAt(today, clock[0], clock[1]);
    return at > nowMs ? at : at + DAY_MS;
  }
  const [h, mi] = clock ?? vagueClock(text);
  return kstAt(day, h, mi);
}

function nameOf(id: ActionId): string {
  return ACTIONS.find((a) => a.id === id)?.name ?? id;
}

function reject(reason: 'unsupported' | 'ambiguous', source: 'rule' | 'model', candidates: string[] = []): PlanResponse {
  return {
    action: null,
    action_name: null,
    target: emptyTarget(),
    params: {},
    source,
    reason,
    candidates,
    prompt_version: source === 'model' ? MOCK_PROMPT_VERSION : null,
    rules_version: MOCK_RULES_VERSION,
    fallback: null,
  };
}

/**
 * 명령 한 줄 → PlanResponse(모의). 순수 함수: 같은 입력이면 같은 결과.
 * 실제 서비스처럼 '행동을 고르고 대상 단서 · 값을 뽑는' 데까지만 한다. 단서를 실제 업무로 바꾸는 일 · 확인 판단은 agentExecutor.ts가 한다.
 */
export function planCommand(text: string, context: PlanContext): PlanResponse {
  const t = normalize(text);
  const found = hits(t);
  if (found.length !== 1) return reject('unsupported', 'model', found);
  const action = found[0]!;
  const nowMs = parseKstNaive(context.now) ?? Date.now();
  const target = extractTarget(t, context);
  const params: PlanResponse['params'] = {};

  if (action === 'T01') params.date = kstNaive(kstAt(kstDay(nowMs) + (/내일/.test(t) ? 1 : 0), 0, 0)).slice(0, 10);
  if (action === 'T05') {
    // 언제인지 모르면('나중에 다시 알려줘') null로 둔다 → executor가 '다시 알림 받을 시각을 알려 주십시오'로 되묻는다
    const until = remindAt(t, nowMs);
    params.until = until === null ? null : kstNaive(until).slice(0, 16) + ':00';
  }
  if (action === 'T06') {
    const m = /(\d+)\s*(일|주)\s*(?:이상|넘|지난|째|동안)/.exec(t);
    params.min_days = m ? Number(m[1]) * (m[2] === '주' ? 7 : 1) : 3;
  }
  if (action === 'T07') {
    params.tone = /짧게|간단/.test(t) ? 'short' : 'polite';
    if (target.mail_ids.length === 0) target.mail_ids = [...context.selected_mail_ids];
  }

  return {
    action,
    action_name: nameOf(action),
    target,
    params,
    source: 'rule',
    reason: null,
    candidates: [],
    prompt_version: null,
    rules_version: MOCK_RULES_VERSION,
    fallback: null,
  };
}

/** 모의 응답이 걸리는 시간(규칙 경로 · 엑사원 경로) */
export function mockDelayMs(plan: PlanResponse, delay: { rule: number; model: number } = MOCK_DELAY_MS): number {
  return plan.source === 'model' ? delay.model : delay.rule;
}

/** 모의 회신 초안(T07). 실제로는 AI `/draft`가 만든다. 사용자는 '하고 싶은 말'만 받고, 인사 · 맺음은 답장 화면 템플릿이 붙인다(UX-D5) */
export function mockReplyDraft(taskTexts: readonly string[], tone: 'polite' | 'short'): string {
  if (tone === 'short') return '확인했습니다. 곧 회신드리겠습니다.';
  const first = taskTexts[0];
  return first
    ? `요청하신 '${first}' 건 확인했습니다. 검토 후 다시 회신드리겠습니다.`
    : '보내 주신 내용 확인했습니다. 검토 후 다시 회신드리겠습니다.';
}
