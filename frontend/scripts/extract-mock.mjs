#!/usr/bin/env node
// 모의 데이터 추출: data/dummy/dummy_mails.json(v1) → src/api/mock/dashboard.v1.json
//
//   npm run mock:extract   # 다시 만든다
//   npm run mock:check     # 원본에서 다시 만든 결과가 커밋된 파일과 같은지 확인한다(다르면 종료 코드 1)
//
// - 원본은 읽기만 한다. 화면에 필요한 메일 메타데이터(발신자 · 제목 · 수신 시각 · 분류)와 정답 업무만 남긴다.
//   메일 본문 · 첨부 · gold의 action_types · urgent · tags · tasks[].format 등은 넣지 않는다.
// - 순서 · 분류는 backend 시드(backend/app/dev/seed.py)와 같게 만든다.
//   메일은 received_at 순(같으면 원본 순서)으로 id 1..N, 업무는 그 메일 순서 · 메일 안 순서로 id 1..M.
//   분류는 seed.py의 CATEGORY · category()를 그대로 옮겼다. 업무에는 분류 칸이 없고 메일 category를 따른다.
// - 시각은 원본(시간대 없는 KST)에 +09:00을 붙인다(D47: backend → frontend 응답 시각은 +09:00).
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE_REL = 'data/dummy/dummy_mails.json';
const SOURCE = resolve(here, '../..', SOURCE_REL);
const OUTPUT = resolve(here, '../src/api/mock/dashboard.v1.json');
const AS_OF = '2026-10-20T09:00:00+09:00'; // 시연 후보 B(backend/scripts/demo_expected.py CANDIDATE_B)

// backend/app/dev/seed.py CATEGORY · NO_TASK_TYPES (D39 묶음 [제안])
const CATEGORY = {
  회신요청: '회신', 자료제출요청: '요청', 수정재전송요청: '요청', 일정참석: '요청',
  검토승인요청: '검토', 공지: '공지', 참조: '기타', 회신: '기타', 기타: '기타',
};
const NO_TASK_TYPES = new Set(['공지', '참조', '회신', '기타']);

// seed.py category(): 업무가 있으면 첫 번째 '업무를 만드는 유형', 없으면 첫 유형 (D40)
function category(actionTypes, hasTasks) {
  const first = hasTasks ? (actionTypes.find((t) => !NO_TASK_TYPES.has(t)) ?? actionTypes[0]) : actionTypes[0];
  const value = CATEGORY[first];
  if (!value) throw new Error(`분류 매핑에 없는 유형: ${first}`);
  return value;
}

function kst(naive) {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(naive)) throw new Error(`예상하지 못한 시각 형식: ${naive}`);
  return `${naive}:00+09:00`;
}

function build(raw, sourceSha256) {
  if (raw.meta?.version !== 'v1') throw new Error(`v1 원본이 아니다: ${raw.meta?.version}`);
  const owner = raw.mailbox.owner;
  const superiors = new Set(raw.mailbox.superiors ?? []);
  const favorites = new Set(raw.mailbox.favorites ?? []);
  const asOfMs = Date.parse(AS_OF);

  const arrived = raw.mails
    .filter((m) => Date.parse(kst(m.mail.received_at)) <= asOfMs)
    .sort((a, b) => (a.mail.received_at < b.mail.received_at ? -1 : a.mail.received_at > b.mail.received_at ? 1 : 0));

  const mails = [];
  const tasks = [];
  for (const { mail, gold } of arrived) {
    const goldTasks = gold.tasks ?? [];
    const mailId = mails.length + 1;
    mails.push({
      id: mailId,
      source_id: mail.id,
      direction: mail.from === owner ? 'sent' : 'received',
      sender: mail.from,
      subject: mail.subject ?? '',
      received_at: kst(mail.received_at),
      category: category(gold.action_types, goldTasks.length > 0),
    });
    for (const t of goldTasks) {
      tasks.push({
        id: tasks.length + 1,
        mail_id: mailId,
        text: t.action,
        due_at: t.due_at ? kst(t.due_at) : null,
        due_source: 'none', // 시드는 due_source를 채우지 않는다(기본값 none). 기한 유무 판단에 쓰지 않는다
        status: 'pending',
        seen_at: null,
      });
    }
  }

  const senders = new Set(mails.map((m) => m.sender));
  const contacts = Object.values(raw.people)
    .filter((p) => p.email !== owner && senders.has(p.email))
    .map((p) => ({
      email: p.email,
      name: p.name ?? null,
      position: p.position ?? null,
      is_superior: superiors.has(p.email),
      is_favorite: favorites.has(p.email),
    }))
    .sort((a, b) => a.email.localeCompare(b.email));

  return {
    meta: {
      dataset: SOURCE_REL,
      version: raw.meta.version,
      source_sha256: sourceSha256,
      generator: 'frontend/scripts/extract-mock.mjs',
      category_mapping: 'backend/app/dev/seed.py CATEGORY · category()',
      note: 'FE-1 모의 데이터. 정답 라벨(gold) 업무를 시드와 같은 순서 · 분류로 옮겼다. 상태는 모두 pending(시드 직후와 같음).',
    },
    response: { as_of: AS_OF, contacts, mails, tasks },
  };
}

function main() {
  const bytes = readFileSync(SOURCE);
  const sha = createHash('sha256').update(bytes).digest('hex');
  const text = `${JSON.stringify(build(JSON.parse(bytes.toString('utf8')), sha), null, 1)}\n`;
  if (process.argv.includes('--check')) {
    let current = '';
    try {
      current = readFileSync(OUTPUT, 'utf8');
    } catch {
      // 파일이 없으면 아래에서 불일치로 처리한다
    }
    if (current !== text) {
      console.error(`불일치: ${OUTPUT}가 원본에서 다시 만든 결과와 다르다. npm run mock:extract로 다시 만든다.`);
      process.exit(1);
    }
    console.log('일치: 모의 데이터가 원본에서 다시 만든 결과와 같다.');
    return;
  }
  writeFileSync(OUTPUT, text);
  console.log(`작성: ${OUTPUT}`);
}

main();
