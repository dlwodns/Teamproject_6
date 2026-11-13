#!/usr/bin/env node
// 모의 데이터 v2 추출: docs/20_frontend/ui_reference/cne_v31.html(시안) → src/api/mock/*.v2.json · *.v1.json
//
//   npm run mock:extract-v2   # 다시 만든다
//   npm run mock:check-v2     # 시안에서 다시 만든 결과가 커밋된 파일과 같은지 확인한다(다르면 종료 코드 1)
//
// 만드는 파일 4개
//   dashboard.v2.json      { meta, response } — provisional.ts 계약 + 선택 필드(as_of · contacts · mails · tasks · awaiting)
//   mails.v2.json          메일 id별 상세(받는 사람 · 본문 문단 · 언어 · 요약)
//   notifications.v1.json  알림 센터(리마인더 탭 + 알림 탭)
//   settings.v1.json       설정 기본값 + 답장 템플릿
//
// 왜 시안에서 만드나: 화면 합의 테스트(wireframe.md 13-9, V-1~V-27)가 시안의 시연 데이터를 기준으로 적혀 있다.
// 시안 JS의 배열 리터럴(mails · tasks · awaiting · reminders · TPL)을 글자 그대로 잘라 node:vm 빈 컨텍스트에서 평가한다.
// 우리 레포 파일이라 평가해도 된다. 알림 탭 항목은 renderPop() 안 HTML 문자열이라 정규식으로 읽는다.
//
// 결정(meta.decisions에도 같은 내용)
// - 메일 id: 시안 배열 순서대로 1..N(m1~m12 → 1~12, c1~c5 → 13~17, r1~r7 → 18~24). source_id에 시안 id를 둔다.
// - 업무 id: t1..t23 → 1..23. 받은 날은 메일 received_at의 날짜(계약에 업무별 받은 날이 없다).
// - 시안에서 mail:'x'(화면에 메일이 없는 완료 · 나중에 업무 9건)는 새 메일을 만들지 않고 '같은 받은 날'의 기존 메일에 붙인다.
//   새 메일을 만들면 메일함 수(V-12)가 바뀌기 때문이다. 고르는 차례: 같은 날 · 할 일 칸 · 같은 분류 → 같은 날 · 할 일 칸
//   → 같은 날 · 같은 분류 → 같은 날 아무 메일(각각 시안 배열 순서의 첫 메일). 이렇게 붙인 업무의 evidence_text는 null.
// - seen_at: 시안 isNew면 null, 아니면 메일 received_at. read_at(메일): 새 업무가 있거나 확인 칸이면 null, 아니면 received_at.
// - ASAP: due_at null · due_source 'none' · due_raw 'ASAP'. 기한이 있으면 due_source 'mail', due_raw null.
// - 근거 문장: 시안 규칙(업무 순서 = 본문 <mark> 순서)대로 그 메일의 원래 업무 i번째 ↔ i번째 <mark>.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { runInNewContext } from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE_REL = 'docs/20_frontend/ui_reference/cne_v31.html';
const SOURCE = resolve(here, '../..', SOURCE_REL);
const MOCK_DIR = resolve(here, '../src/api/mock');
const OUT = {
  dashboard: resolve(MOCK_DIR, 'dashboard.v2.json'),
  mails: resolve(MOCK_DIR, 'mails.v2.json'),
  notifications: resolve(MOCK_DIR, 'notifications.v1.json'),
  settings: resolve(MOCK_DIR, 'settings.v1.json'),
};

// 가상 연락처 주소. 실존 인물 · 회사 아님. 사내는 cne.example, 거래처는 회사별 .example
const EMAIL = {
  이서준: 'seojun.lee@cne.example',
  박지호: 'jiho.park@partner.example',
  김민준: 'minjun.kim@cne.example',
  정하늘: 'haneul.jung@cne.example',
  최유진: 'yujin.choi@cne.example',
  인재개발팀: 'hrd@cne.example',
  한도윤: 'doyun.han@cne.example',
  오세린: 'serin.oh@cne.example',
  재무팀: 'finance@cne.example',
  'Daniel Moore': 'daniel.moore@harborline.example',
  구매팀: 'purchasing@cne.example',
  정보보호팀: 'infosec@cne.example',
  '모니터링 시스템': 'monitoring@cne.example',
  IT지원팀: 'itsupport@cne.example',
  '사내 소식': 'news@cne.example',
  고객경험팀: 'cx@cne.example',
  '외부 세미나': 'invite@aiseminar.example',
  경영지원팀: 'management@cne.example',
  'Sophie Laurent': 'sophie.laurent@ateliernord.example',
};

// 시안에 시각이 없는 알림 · 응답 대기 값. 기준 시각(11/6 10:42) 앞으로 정했다
const TIMES = {
  reminderOverdue: '2026-11-06T08:30:00+09:00', // 기한 지남 리마인더: 아침 점검 때 만듦
  reminderDueSoon: '2026-11-06T10:42:00+09:00', // '기한 7시간 전': 기준 시각에 막 뜬 것으로
  replyConfirm: '2026-11-06T10:20:00+09:00', // Outlook 답장 확인
  morningRead: '2026-11-06T08:35:00+09:00', // 아침 알림을 읽은 시각(시안에서 읽음 표시)
  awaitingSentHour: '10:00',
};

const strip = (s) => s.replace(/<[^>]+>/g, '');

function between(html, start, end) {
  const a = html.indexOf(start);
  if (a < 0) throw new Error(`시안에서 찾지 못함: ${start}`);
  const b = html.indexOf(end, a);
  if (b < 0) throw new Error(`시안에서 찾지 못함: ${end}`);
  return html.slice(a, b);
}

function extract(html) {
  const dataSrc = between(html, "const TODAY='", '/* ───────── 화면 상태');
  const data = runInNewContext(`${dataSrc}\n;({TODAY,NOW_T,ME,mails,tasks,awaiting,reminders})`, {});
  const tplSrc = between(html, 'const TPL={', '\n};');
  const TPL = runInNewContext(`(${tplSrc.slice('const TPL='.length)}\n})`, {});
  const popSrc = between(html, `<div class="grp">오늘</div>`, '<div class="ios">');
  const noti = [];
  const re = /<div class="nt( unread)?"><span class="ic"[^>]*>[^<]*<\/span><b>([^<]*)<\/b><span class="s">([^<]*)<\/span>(.*?)<\/div>/g;
  for (const m of popSrc.matchAll(re)) {
    const yes = /data-noti-yes="([^"]+)"/.exec(m[4] ?? '');
    noti.push({ unread: !!m[1], title: m[2], body: m[3], yesTask: yes ? yes[1] : null });
  }
  return { ...data, TPL, noti };
}

const iso = (date, time) => `${date}T${time}:00+09:00`;
const recvIso = (m) => iso(m.date, m.time.split(' ')[1].padStart(5, '0'));

function build(src, sha) {
  const { TODAY, NOW_T, ME, mails: pm, tasks: pt, awaiting: pa, reminders: pr, TPL, noti } = src;
  if (TODAY !== '2026-11-06' || NOW_T !== '10:42') throw new Error(`기준 시각이 바뀌었다: ${TODAY} ${NOW_T}`);
  const asOf = iso(TODAY, NOW_T);
  const mailId = new Map(pm.map((m, i) => [m.id, i + 1]));
  const taskId = new Map(pt.map((t, i) => [t.id, i + 1]));
  const byPid = new Map(pm.map((m) => [m.id, m]));

  // 'x' 업무 → 같은 받은 날 기존 메일
  const xMap = {};
  for (const t of pt) {
    if (t.mail !== 'x') continue;
    const day = pm.filter((m) => m.date === t.recv);
    const pick =
      day.find((m) => m.lane === '할 일' && m.cat === t.type) ??
      day.find((m) => m.lane === '할 일') ??
      day.find((m) => m.cat === t.type) ??
      day[0];
    if (!pick) throw new Error(`${t.id}: ${t.recv}에 받은 메일이 없다`);
    xMap[t.id] = pick.id;
  }
  const mailOf = (t) => (t.mail === 'x' ? xMap[t.id] : t.mail);

  // 연락처: 발신자 이름마다 하나
  const contacts = [];
  const seen = new Set();
  for (const m of pm) {
    if (seen.has(m.from)) continue;
    seen.add(m.from);
    const email = EMAIL[m.from];
    if (!email) throw new Error(`가상 주소가 없는 발신자: ${m.from}`);
    const [position = '', org] = m.title ? m.title.split(' · ') : [];
    const c = { email, name: m.from, position, is_superior: !!m.sup, is_favorite: !!m.fav };
    if (org) c.org = org;
    c.is_client = !!m.client;
    contacts.push(c);
  }
  contacts.sort((a, b) => a.email.localeCompare(b.email));

  const newMail = new Set(pt.filter((t) => t.isNew).map((t) => t.mail));
  const mails = pm.map((m) => ({
    id: mailId.get(m.id),
    source_id: m.id,
    direction: 'received',
    sender: EMAIL[m.from],
    subject: m.subject,
    received_at: recvIso(m),
    category: m.cat,
    lane: m.lane,
    reasons: m.reason ? [m.reason] : [],
    to: [ME],
    account: m.acc,
    lang: m.lang ?? 'ko',
    read_at: newMail.has(m.id) || m.lane === '확인' ? null : recvIso(m),
  }));

  const marks = (m) => m.body.flatMap((p) => [...p.matchAll(/<mark>(.*?)<\/mark>/g)].map((x) => strip(x[1])));
  const tasks = pt.map((t) => {
    const mid = mailOf(t);
    const m = byPid.get(mid);
    let evidence = null;
    if (t.mail !== 'x') {
      const idx = pt.filter((x) => x.mail === t.mail).indexOf(t);
      evidence = marks(m)[idx] ?? null;
    }
    return {
      id: taskId.get(t.id),
      mail_id: mailId.get(mid),
      text: t.text,
      due_at: t.due ? iso(t.due.d, t.due.t) : null,
      due_source: t.due ? 'mail' : 'none',
      status: t.status,
      seen_at: t.isNew ? null : recvIso(m),
      due_raw: t.asap ? 'ASAP' : null,
      type: t.type,
      evidence_text: evidence,
    };
  });

  const dayBefore = (n) => {
    const d = new Date(Date.parse(`${TODAY}T00:00:00Z`) - n * 86400000).toISOString().slice(0, 10);
    return iso(d, TIMES.awaitingSentHour);
  };
  const awaiting = pa.map((w, i) => ({ mail_id: 1001 + i, subject: w.subject, to: w.to, sent_at: dayBefore(w.days), days: w.days }));

  const decisions = [
    `시안 mail:'x' 업무 ${Object.keys(xMap).length}건은 새 메일을 만들지 않고 같은 받은 날의 기존 메일에 붙였다(새 메일을 만들면 메일함 수 V-12가 바뀜). 차례: 같은 날·할 일 칸·같은 분류 → 같은 날·할 일 칸 → 같은 날·같은 분류 → 같은 날 첫 메일. 결과: ${Object.entries(xMap).map(([t, m]) => `${t}→${m}`).join(', ')}. 이 업무들의 evidence_text는 null.`,
    '메일 id는 시안 배열 순서 1..N, 업무 id는 t1..tN 순서 1..N. 시안 id는 source_id에 둔다.',
    'seen_at: 시안 isNew면 null, 아니면 메일 received_at. 메일 read_at: 새 업무가 있거나 확인 칸이면 null, 아니면 received_at.',
    "ASAP 업무: due_at null, due_source 'none', due_raw 'ASAP'. 기한이 있으면 due_source 'mail'.",
    '업무 type은 시안 업무 유형(회신·요청·검토·기타). 메일 category와 다를 수 있다(t12·t23).',
    'evidence_text: 시안 규칙(메일 안 업무 순서 = 본문 <mark> 순서)으로 i번째 업무 ↔ i번째 <mark> 문장(태그 제거).',
    'awaiting: 보낸 메일은 mails[]에 넣지 않고 mail_id 1001부터. sent_at = 기준일 - days일 10:00.',
    '받은 날 집계(N1)의 미처리 = 전체 - 처리(나중에 포함, 제외는 전체에서 뺌). 긴급·유형 칸은 status pending만(시안 isOpen).',
  ];

  const dashboard = {
    meta: {
      dataset: 'cne_v31 시안 시연 데이터',
      version: 'v2',
      source: SOURCE_REL,
      source_sha256: sha,
      generator: 'frontend/scripts/extract-mock-v2.mjs',
      note: '화면 합의 테스트(wireframe.md 13-9)의 기준 데이터. 계약(provisional.ts) 필드 + 선택 필드(lane · reasons · to · account · lang · read_at · due_raw · type · evidence_text · org · is_client · awaiting). 인물 · 회사 · 주소는 모두 가상.',
      decisions,
    },
    response: { as_of: asOf, contacts, mails, tasks, awaiting },
  };

  // 메일 상세
  const detail = {};
  for (const m of pm) {
    let summary = null;
    if (m.summary) {
      const open = pt.filter((t) => t.mail === m.id && t.status === 'pending');
      summary = {
        lang: m.lang ?? 'ko',
        gist: m.summary.gist,
        asks: m.summary.asks ?? (m.lane === '할 일' ? open.map((t) => t.text) : []),
        due_text: m.summary.dueRaw ?? null,
      };
    }
    const d = { to: [ME], body: m.body.map(strip), lang: m.lang ?? 'ko', summary };
    if (m.sumFail) d.summary_fail_first = true;
    detail[String(mailId.get(m.id))] = d;
  }

  // 알림
  const items = [];
  for (const r of pr) {
    const t = pt.find((x) => x.id === r.task);
    const at = r.over ? TIMES.reminderOverdue : TIMES.reminderDueSoon;
    items.push({
      id: items.length + 1,
      kind: 'reminder',
      title: r.kind,
      body: t.text,
      task_ids: [taskId.get(r.task)],
      rule: 'R-기한',
      scheduled_at: at,
      read_at: r.unread ? null : at,
      answered_at: null,
      created_at: at,
    });
  }
  const morningOpen = pt
    .filter((t) => t.status === 'pending' && recvIso(byPid.get(mailOf(t))) < iso(TODAY, '08:30'))
    .map((t) => taskId.get(t.id));
  for (const n of noti) {
    let item;
    if (n.yesTask) {
      item = { kind: 'reply_confirm', task_ids: [taskId.get(n.yesTask)], rule: null, scheduled_at: null, created_at: TIMES.replyConfirm };
    } else if (n.title.startsWith('아침 알림')) {
      const hm = /(\d{2}:\d{2})/.exec(n.title)[1];
      item = { kind: 'reminder', task_ids: morningOpen, rule: 'R-아침', scheduled_at: iso(TODAY, hm), created_at: iso(TODAY, hm) };
    } else if (n.title.startsWith('새 업무')) {
      const hm = /~(\d{2}:\d{2})/.exec(n.body)[1];
      item = { kind: 'new_tasks', task_ids: pt.filter((t) => t.isNew).map((t) => taskId.get(t.id)), rule: null, scheduled_at: null, created_at: iso(TODAY, hm) };
    } else {
      throw new Error(`모르는 알림 항목: ${n.title}`);
    }
    items.push({
      id: items.length + 1,
      kind: item.kind,
      title: n.title,
      body: n.body,
      task_ids: item.task_ids,
      rule: item.rule,
      scheduled_at: item.scheduled_at,
      read_at: n.unread ? null : TIMES.morningRead,
      answered_at: null,
      created_at: item.created_at,
    });
  }

  // 설정 · 템플릿
  const KEYS = { '기본 회신': 'basic', '자료 송부': 'material', '일정 회신': 'schedule', 확인했습니다: 'ack' };
  const templates = Object.keys(TPL).map((name) => {
    const full = TPL[name]('{수신자명}', '{발신자명}', '{내용}');
    const [greeting, rest] = full.split('\n\n{내용}\n\n');
    if (rest === undefined) throw new Error(`템플릿 형식이 바뀌었다: ${name}`);
    const lines = rest.split('\n');
    const signature = lines.pop();
    if (!KEYS[name]) throw new Error(`템플릿 키가 없다: ${name}`);
    return { key: KEYS[name], name, greeting, closing: lines.join('\n'), signature, pattern: full };
  });
  const settings = {
    remind_time: '08:30',
    awaiting_reply_days: 3,
    quiet_start: null,
    quiet_end: null,
    reduce_motion: false,
    stt_mode: 'browser',
    reply_confirm_skip_until: null, // 완료 확인 시트 '오늘 다시 보지 않음'(FE-5, DB settings 칸)
    templates,
  };

  return { dashboard, mails: detail, notifications: { items }, settings };
}

function main() {
  const bytes = readFileSync(SOURCE);
  const sha = createHash('sha256').update(bytes).digest('hex');
  const out = build(extract(bytes.toString('utf8')), sha);
  const check = process.argv.includes('--check');
  let bad = 0;
  for (const [k, path] of Object.entries(OUT)) {
    const text = `${JSON.stringify(out[k], null, 1)}\n`;
    if (check) {
      let current = '';
      try {
        current = readFileSync(path, 'utf8');
      } catch {
        // 파일이 없으면 불일치
      }
      if (current !== text) {
        console.error(`불일치: ${path}가 시안에서 다시 만든 결과와 다르다. npm run mock:extract-v2로 다시 만든다.`);
        bad++;
      }
    } else {
      writeFileSync(path, text);
      console.log(`작성: ${path}`);
    }
  }
  if (check) {
    if (bad) process.exit(1);
    console.log('일치: 모의 데이터 v2가 시안에서 다시 만든 결과와 같다.');
  }
}

main();
