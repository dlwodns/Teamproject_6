import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createBrowserStt, errorCodeOf, MAX_MS, recognitionCtorOf, SILENCE_MS, splitResults, type RecognitionLike } from './adapters/browserStt.ts';
import { sttModeOf, type SttErrorCode } from './stt.ts';
import { joinSpoken, tidySpoken, voiceErrorText, voiceHint } from './voiceText.ts';

test('들은 말은 입력칸에 있던 글 뒤에 한 칸 띄워 붙는다', () => {
  assert.equal(joinSpoken('', '김 팀장님 건', '다 처리했어'), '김 팀장님 건 다 처리했어');
  assert.equal(joinSpoken('견적 건', '내일 아침으로 미뤄', ''), '견적 건 내일 아침으로 미뤄');
  assert.equal(joinSpoken('견적 건 ', '미뤄', ''), '견적 건 미뤄');
  assert.equal(joinSpoken('  ', '이거 완료', ''), '이거 완료');
  // 아무 말도 못 들었으면 쓰던 글이 그대로
  assert.equal(joinSpoken('쓰던 글', '', '  '), '쓰던 글');
  assert.equal(tidySpoken('  회신 \n 초안   써 줘 '), '회신 초안 써 줘');
});

test('실패 문구는 이유와 할 일을 말하고, 안내 줄은 오류 > 듣는 중 > 기본 순서', () => {
  const codes: SttErrorCode[] = ['not-allowed', 'insecure', 'no-speech', 'audio-capture', 'network', 'unknown'];
  const texts = codes.map(voiceErrorText);
  assert.equal(new Set(texts).size, codes.length);
  for (const t of texts) assert.doesNotMatch(t.replace(/https/g, ''), /[A-Za-z]{4,}/, `영어 문구 섞임: ${t}`);
  assert.match(voiceErrorText('insecure'), /https/);
  for (const t of [...texts, voiceHint({ listening: true, error: null }) ?? '']) assert.doesNotMatch(t, /\p{Extended_Pictographic}/u, `그림 문자: ${t}`);
  assert.equal(voiceHint({ listening: false, error: null }), null);
  assert.match(voiceHint({ listening: true, error: null }) ?? '', /^듣는 중/);
  assert.equal(voiceHint({ listening: true, error: 'network' }), voiceErrorText('network'));
});

test('설정값: server만 서버 방식, 나머지는 브라우저 방식(D29 1차)', () => {
  assert.equal(sttModeOf(undefined), 'browser');
  assert.equal(sttModeOf(''), 'browser');
  assert.equal(sttModeOf(' Server '), 'server');
  assert.equal(sttModeOf('whisper'), 'browser');
});

test('브라우저 오류 이름 → 화면 이유. 우리가 끊은 aborted는 오류가 아니다', () => {
  assert.equal(errorCodeOf('aborted'), null);
  assert.equal(errorCodeOf('not-allowed'), 'not-allowed');
  assert.equal(errorCodeOf('service-not-allowed'), 'not-allowed');
  assert.equal(errorCodeOf('no-speech'), 'no-speech');
  assert.equal(errorCodeOf('language-not-supported'), 'unknown');
});

const result = (transcript: string, isFinal: boolean) => Object.assign([{ transcript }], { isFinal });

test('결과 목록은 확정 글자와 아직 바뀌는 글자로 나뉜다', () => {
  assert.deepEqual(splitResults([result('김 팀장님 건', true), result(' 다 처리', false)]), { finalText: '김 팀장님 건', interimText: '다 처리' });
  assert.deepEqual(splitResults([]), { finalText: '', interimText: '' });
});

test('음성인식이 없는 브라우저면 어댑터가 없다(🎤 숨김), webkit 접두사도 찾는다', () => {
  assert.equal(recognitionCtorOf(undefined), null);
  assert.equal(recognitionCtorOf({}), null);
  assert.equal(createBrowserStt({}), null);
  const Ctor = class {} as unknown as new () => RecognitionLike;
  assert.equal(recognitionCtorOf({ webkitSpeechRecognition: Ctor }), Ctor);
});

// 가짜 SpeechRecognition + 손으로 돌리는 타이머
function harness(opts: { secure?: boolean; failStart?: boolean } = {}) {
  const made: FakeRec[] = [];
  class FakeRec implements RecognitionLike {
    lang = '';
    continuous = false;
    interimResults = false;
    maxAlternatives = 0;
    onresult: RecognitionLike['onresult'] = null;
    onerror: RecognitionLike['onerror'] = null;
    onend: RecognitionLike['onend'] = null;
    calls: string[] = [];
    constructor() {
      made.push(this);
    }
    start() {
      this.calls.push('start');
      if (opts.failStart) throw new Error('InvalidStateError');
    }
    stop() {
      this.calls.push('stop');
      this.onend?.();
    }
    abort() {
      this.calls.push('abort');
      this.onend?.();
    }
  }
  const timers = new Map<number, { fn: () => void; at: number }>();
  let now = 0;
  let seq = 0;
  const clock = {
    set: (fn: () => void, ms: number) => {
      timers.set(++seq, { fn, at: now + ms });
      return seq;
    },
    clear: (id: unknown) => void timers.delete(id as number),
  };
  const advance = (ms: number) => {
    now += ms;
    for (const [id, t] of [...timers]) {
      if (t.at <= now) {
        timers.delete(id);
        t.fn();
      }
    }
  };
  const adapter = createBrowserStt({ SpeechRecognition: FakeRec, isSecureContext: opts.secure ?? true }, clock);
  assert.ok(adapter);
  const log: string[] = [];
  const handlers = {
    onText: (f: string, i: string) => log.push(`text:${f}|${i}`),
    onError: (c: SttErrorCode) => log.push(`error:${c}`),
    onEnd: () => log.push('end'),
  };
  return { adapter, made, advance, log, handlers };
}

test('한국어 · 이어 듣기 · 중간 글자 켜고 시작, 말을 멈추면 5초 뒤 스스로 멈춘다', () => {
  const h = harness();
  h.adapter.start('ko-KR', h.handlers);
  const rec = h.made[0]!;
  assert.deepEqual([rec.lang, rec.continuous, rec.interimResults], ['ko-KR', true, true]);
  rec.onresult?.({ results: [result('이거', false)] });
  h.advance(SILENCE_MS - 1);
  rec.onresult?.({ results: [result('이거 완료', true)] }); // 말이 이어지면 시계를 다시 잰다
  h.advance(SILENCE_MS - 1);
  assert.deepEqual(rec.calls, ['start']);
  h.advance(1);
  assert.deepEqual(rec.calls, ['start', 'stop']);
  assert.deepEqual(h.log, ['text:|이거', 'text:이거 완료|', 'end']);
});

test('아무리 길어도 60초에서 끊는다', () => {
  const h = harness();
  h.adapter.start('ko-KR', h.handlers);
  h.advance(MAX_MS);
  assert.deepEqual(h.made[0]!.calls, ['start', 'stop']);
  assert.deepEqual(h.log, ['end']);
});

test('abort는 뒤늦은 글자를 버리고 end를 한 번만 보낸다', () => {
  const h = harness();
  const s = h.adapter.start('ko-KR', h.handlers);
  const rec = h.made[0]!;
  const late = rec.onresult;
  s.abort();
  late?.({ results: [result('늦은 글자', true)] });
  s.abort();
  s.stop();
  assert.deepEqual(h.log, ['end']);
});

test('오류는 이유를 알리고 끝난다, aborted는 조용히 끝난다', () => {
  const h = harness();
  h.adapter.start('ko-KR', h.handlers);
  const rec = h.made[0]!;
  rec.onerror?.({ error: 'not-allowed' });
  rec.onend?.();
  assert.deepEqual(h.log, ['error:not-allowed', 'end']);

  const h2 = harness();
  h2.adapter.start('ko-KR', h2.handlers);
  h2.made[0]!.onerror?.({ error: 'aborted' });
  h2.made[0]!.onend?.();
  assert.deepEqual(h2.log, ['end']);
});

test('http 주소에서는 마이크를 열지 않고 insecure로 끝난다', async () => {
  const h = harness({ secure: false });
  h.adapter.start('ko-KR', h.handlers);
  assert.equal(h.made.length, 0);
  await Promise.resolve();
  assert.deepEqual(h.log, ['error:insecure', 'end']);
});

test('start()가 실패해도 세션을 돌려준 뒤에 오류 · 끝을 알린다(화면이 듣는 중에 멈추지 않게, #91 리뷰)', async () => {
  const h = harness({ failStart: true });
  h.adapter.start('ko-KR', h.handlers);
  assert.deepEqual(h.log, []); // 아직 세션을 받기 전이다
  await Promise.resolve();
  assert.deepEqual(h.log, ['error:unknown', 'end']);
});
