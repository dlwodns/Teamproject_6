// 업무 근거 형광펜(FE-5b · UX-D16). 업무마다 붙은 근거 문장(AI-15 tasks.evidence_text)을 본문 문단에서 찾아 칠할 자리를 정한다.
// 근거는 '본문에 그대로 있는 문장'이라 글자 그대로 찾는다. 줄바꿈 · 겹친 공백만 하나로 보고, 다른 글자는 고쳐 맞추지 않는다.
// 찾지 못한 근거는 칠하지 않는다(지어내지 않음). 화면은 그 업무 줄에 '근거 문장 없음'을 적는다.
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
  byTask: Map<TaskId, EvidenceMark>;
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

/** 근거 문장이 본문 어디에 있는지. 같은 문장은 같은 자리를 함께 쓰고, 이미 칠한 자리와 겹치면 그 자리를 함께 쓴다 */
export function locateEvidence(paragraphs: readonly string[], tasks: readonly Pick<Task, 'id' | 'evidenceText'>[]): EvidenceMap {
  const folded = paragraphs.map(fold);
  const marks: EvidenceMark[] = [];
  const byTask = new Map<TaskId, EvidenceMark>();

  for (const t of tasks) {
    const needle = fold((t.evidenceText ?? '').trim()).folded;
    if (needle.length === 0) continue;
    for (let p = 0; p < folded.length; p++) {
      const { folded: hay, at } = folded[p]!;
      const i = hay.indexOf(needle);
      if (i < 0) continue;
      const start = at[i]!;
      const end = at[i + needle.length - 1]! + 1;
      const hit = marks.find((m) => m.paragraph === p && m.start < end && start < m.end);
      if (hit) {
        hit.taskIds.push(t.id);
        byTask.set(t.id, hit);
      } else {
        const mark: EvidenceMark = { id: `ev-${p}-${start}`, paragraph: p, start, end, taskIds: [t.id] };
        marks.push(mark);
        byTask.set(t.id, mark);
      }
      break;
    }
  }
  marks.sort((a, b) => a.paragraph - b.paragraph || a.start - b.start);
  return { marks, byTask };
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
