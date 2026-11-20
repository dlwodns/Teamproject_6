// 업무 근거 형광펜(FE-5b · UX-D16). 업무마다 붙은 근거 문장(AI-15 tasks.evidence_text)을 본문 문단에서 찾아 칠할 자리를 정한다.
// 근거는 '본문에 그대로 있는 문장을 줄바꿈으로 이은 것'(AI-D14)이라 줄마다 글자 그대로 찾는다. 줄바꿈 · 겹친 공백만 하나로 보고, 다른 글자는 고쳐 맞추지 않는다.
// 찾지 못한 줄은 칠하지 않는다(지어내지 않음). 한 줄도 못 찾으면 화면은 그 업무 줄에 '근거 문장 없음'을 적는다.
import type { Task, TaskId } from '../../api/types.ts';

export interface EvidenceMark {
  id: string; // 'ev-문단-시작'. 화면 요소 id 끝에 붙인다
  paragraph: number;
  start: number; // 문단 원문 기준 [start, end)
  end: number;
  taskIds: TaskId[]; // 같은 문장을 근거로 쓴 업무가 여럿이면 모두
}

export interface Segment {
  text: string;
  mark?: EvidenceMark;
}

export interface EvidenceMap {
  marks: EvidenceMark[]; // 본문 순서(문단 → 시작 위치)
  byTask: Map<TaskId, EvidenceMark>; // 근거 첫 줄(업무 줄을 누르면 옮겨 갈 자리)
  linesByTask: Map<TaskId, EvidenceMark[]>; // 찾은 근거 줄 전부(함께 강조)
}

/** 공백을 하나로 접은 글과, 접은 글의 각 글자가 원문 몇 번째 글자였는지 */
function fold(text: string): { folded: string; at: number[] } {
  let folded = '';
  const at: number[] = [];
  let prevSpace = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (/\s/.test(ch)) {
      if (prevSpace) continue;
      prevSpace = true;
      folded += ' ';
    } else {
      prevSpace = false;
      folded += ch;
    }
    at.push(i);
  }
  return { folded, at };
}

/**
 * 근거 문장이 본문 어디에 있는지(AI-D14 형식: 본문 문장을 줄바꿈으로 이은 것 → 줄마다 찾아 칠한다).
 * - 근거 전체가 한 문단에 그대로 있으면 한 자리로 칠한다
 * - 아니면 줄마다 따로(다른 문단이어도) 찾아 찾은 줄만 칠한다. 기한 문장이 다음 줄에 붙은 근거(ai _with_due)가 이 경우다
 * - 같은 문장(같은 자리)은 형광펜 하나를 함께 쓴다. 일부만 겹치는 자리는 함께 쓰지 않고 다음에 나오는 같은 글을 찾는다
 */
export function locateEvidence(paragraphs: readonly string[], tasks: readonly Pick<Task, 'id' | 'evidenceText'>[]): EvidenceMap {
  const folded = paragraphs.map(fold);
  const marks: EvidenceMark[] = [];
  const byTask = new Map<TaskId, EvidenceMark>();
  const linesByTask = new Map<TaskId, EvidenceMark[]>();

  /** needle을 본문에서 찾아 칠할 자리를 정한다. 못 찾으면 null */
  const place = (needle: string, id: TaskId): EvidenceMark | null => {
    for (let p = 0; p < folded.length; p++) {
      const { folded: hay, at } = folded[p]!;
      for (let i = hay.indexOf(needle); i >= 0; i = hay.indexOf(needle, i + 1)) {
        const start = at[i]!;
        const end = at[i + needle.length - 1]! + 1;
        const same = marks.find((m) => m.paragraph === p && m.start === start && m.end === end);
        if (same) {
          if (!same.taskIds.includes(id)) same.taskIds.push(id);
          return same;
        }
        if (marks.some((m) => m.paragraph === p && m.start < end && start < m.end)) continue; // 다른 문장과 일부만 겹침
        const mark: EvidenceMark = { id: `ev-${p}-${start}`, paragraph: p, start, end, taskIds: [id] };
        marks.push(mark);
        return mark;
      }
    }
    return null;
  };

  for (const t of tasks) {
    const raw = (t.evidenceText ?? '').trim();
    if (raw.length === 0) continue;
    const whole = place(fold(raw).folded, t.id);
    const found = whole
      ? [whole]
      : raw.split('\n').flatMap((line) => {
          const needle = fold(line.trim()).folded;
          const m = needle.length > 0 ? place(needle, t.id) : null;
          return m ? [m] : [];
        });
    if (found.length === 0) continue;
    byTask.set(t.id, found[0]!); // 업무 줄을 누르면 옮겨 갈 자리 = 근거 첫 줄
    linesByTask.set(t.id, found);
  }
  marks.sort((a, b) => a.paragraph - b.paragraph || a.start - b.start);
  return { marks, byTask, linesByTask };
}

/** 문단 하나를 칠한 조각과 칠하지 않은 조각으로 나눈다 */
export function segmentParagraph(text: string, paragraph: number, marks: readonly EvidenceMark[]): Segment[] {
  const mine = marks.filter((m) => m.paragraph === paragraph);
  const out: Segment[] = [];
  let pos = 0;
  for (const m of mine) {
    if (m.start > pos) out.push({ text: text.slice(pos, m.start) });
    out.push({ text: text.slice(m.start, m.end), mark: m });
    pos = m.end;
  }
  if (pos < text.length || out.length === 0) out.push({ text: text.slice(pos) });
  return out;
}

/**
 * AI-42 HTML 본문: 글 조각들(화면 글자 노드 순서)을 이어 붙인 글에서 needle을 찾아, 조각마다 칠할 [start, end)를 돌려준다.
 * 공백은 locateEvidence와 같이 하나로 접어 비교한다. 못 찾으면 null
 */
export function locateInPieces(pieces: readonly string[], needle: string): { piece: number; start: number; end: number }[] | null {
  const want = fold(needle.trim()).folded;
  if (!want) return null;
  const { folded, at } = fold(pieces.join(''));
  const i = folded.indexOf(want);
  if (i < 0) return null;
  const from = at[i]!;
  const to = at[i + want.length - 1]! + 1;
  const out: { piece: number; start: number; end: number }[] = [];
  let pos = 0;
  pieces.forEach((p, k) => {
    const s = Math.max(from, pos);
    const e = Math.min(to, pos + p.length);
    if (s < e) out.push({ piece: k, start: s - pos, end: e - pos });
    pos += p.length;
  });
  return out;
}

/** 업무 줄 순서를 본문의 형광펜 순서와 맞춘다. 근거를 찾은 업무가 본문 순서로 먼저, 나머지는 원래 순서(급한 순) 그대로 뒤에 */
export function orderByEvidence<T extends Pick<Task, 'id'>>(tasks: readonly T[], map: EvidenceMap): T[] {
  const rank = new Map(map.marks.map((m, i) => [m, i]));
  const pos = (t: T) => {
    const m = map.byTask.get(t.id);
    return m ? rank.get(m)! : Infinity;
  };
  return tasks
    .map((t, i) => ({ t, i }))
    .sort((a, b) => pos(a.t) - pos(b.t) || a.i - b.i)
    .map(({ t }) => t);
}
