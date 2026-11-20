// AI-42 받은 메일 HTML 본문(아웃룩처럼 굵게 · 목록 · 표 · 붙여넣은 그림이 보이게). 서버가 이미 걸렀지만 화면에서도 한 번 더 거른다(richText).
// 근거 형광펜은 글 본문에서 찾은 자리(evidence.ts)의 글을 HTML 글자 노드에서 다시 찾아 <mark>로 감싼다. 못 찾은 줄은 칠하지 않는다.
import { useEffect, useLayoutEffect, useRef } from 'react';
import { api } from '../../api/client.ts';
import { locateInPieces } from './evidence.ts';
import { ORIGINAL_MARK, parseQuoteHead, startsQuoteHead } from './quote.ts';
import { sanitizeHtml } from './richText.ts';
import styles from './ReadingPane.module.css';

export interface HtmlMark {
  domId: string; // 업무 줄이 가리키는 요소 id(글 본문과 같은 id)
  markId: string;
  text: string;
}

export function HtmlBody({ html, marks, active }: { html: string; marks: readonly HtmlMark[]; active: readonly string[] | null }) {
  const box = useRef<HTMLDivElement>(null);
  const key = marks.map((m) => `${m.domId}\u0000${m.text}`).join('\u0001');

  useLayoutEffect(() => {
    const root = box.current;
    if (!root) return;
    const frag = sanitizeHtml(html);
    // 본문 그림(서버 '/api/…' 주소)은 <img src>로 부르면 사용자 머리가 빠진다 → 머리를 붙여 받아 blob 주소로 보인다(#276 리뷰)
    const imgs = [...frag.querySelectorAll('img')].flatMap((img) => {
      const path = img.getAttribute('src') ?? '';
      if (!path.startsWith('/api/')) return [];
      img.removeAttribute('src'); // 문서에 넣기 전에 빼야 머리 없는 요청이 나가지 않는다
      return [{ img, path }];
    });
    frag.querySelectorAll('a[href]').forEach((a) => {
      a.setAttribute('target', '_blank'); // 앱 탭이 바깥 사이트로 넘어가지 않게
      a.setAttribute('rel', 'noopener noreferrer');
    });
    root.replaceChildren(frag);
    let alive = true;
    const urls: string[] = [];
    for (const { img, path } of imgs) {
      api.loadImage(path).then(
        (b) => {
          if (!alive) return;
          const u = URL.createObjectURL(b);
          urls.push(u);
          img.src = u;
        },
        () => img.remove(),
      );
    }
    splitQuotes(root);
    const nodes: Text[] = [];
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) nodes.push(n as Text);
    // 범위를 먼저 모두 만든 뒤 감싼다(Range는 글자 노드가 나뉘어도 따라간다)
    const plans = marks.flatMap((m) => {
      const at = locateInPieces(nodes.map((n) => n.data), m.text); // '[그림]' · 공백 차이는 locateInPieces가 맞춘다
      if (!at) return [];
      return at.map((p, i) => {
        const r = document.createRange();
        r.setStart(nodes[p.piece]!, p.start);
        r.setEnd(nodes[p.piece]!, p.end);
        return { r, m, first: i === 0 };
      });
    });
    for (const { r, m, first } of plans) {
      const el = document.createElement('mark');
      el.className = styles.mark ?? '';
      el.dataset.markId = m.markId;
      if (first) {
        el.id = m.domId;
        el.tabIndex = -1;
        const sr = document.createElement('span');
        sr.className = 'sr-only';
        sr.textContent = '업무 근거: ';
        el.append(sr);
      }
      el.append(r.extractContents());
      r.insertNode(el);
    }
    return () => {
      alive = false;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [html, key]);

  useEffect(() => {
    box.current?.querySelectorAll<HTMLElement>('mark[data-mark-id]').forEach((el) => {
      el.toggleAttribute('data-active', !!active?.includes(el.dataset.markId ?? ''));
    });
  }, [active, html, key]);

  return <div ref={box} className={styles.htmlBody} />;
}

/** 인용 시작 자리: 가로줄 뒤 '보낸 사람: · From:' 머리, 또는 '-----Original Message-----'가 든 줄 */
function quoteStart(root: HTMLElement): Node | null {
  const walk = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    if (n instanceof HTMLHRElement) {
      const after = document.createRange();
      after.setStartAfter(n);
      after.setEnd(root, root.childNodes.length);
      if (startsQuoteHead(after.toString().slice(0, 200))) return n;
    } else if (n.nodeType === Node.TEXT_NODE && ORIGINAL_MARK.test(n.textContent ?? '')) {
      return n.parentElement && n.parentElement !== root ? n.parentElement : n;
    }
  }
  return null;
}

/**
 * 이전 메일(인용)을 카드로 나눈다(AI-42). 접지 않고 한 번에 다 보인다(사용자 결정 11-20). 첫 인용 자리부터 끝까지를 카드 하나에 넣고,
 * 카드 안에서 다시 나눠 더 이전 메일은 그 안의 카드가 된다. 카드 머리는 '이전 메일 · 보낸 사람 · 보낸 날짜'
 */
function splitQuotes(container: HTMLElement, depth = 0): void {
  const start = depth < 10 ? quoteStart(container) : null;
  if (!start) return;
  const r = document.createRange();
  r.setStartBefore(start);
  r.setEnd(container, container.childNodes.length);
  const frag = r.extractContents();
  frag.querySelector('hr')?.remove(); // 나누는 가로줄은 카드 테두리가 대신한다
  const body = document.createElement('div');
  body.append(frag);
  const { from, sent } = parseQuoteHead(body.textContent ?? '');
  const card = document.createElement('section');
  card.className = styles.quote ?? '';
  const head = document.createElement('p');
  head.className = styles.quoteHead ?? '';
  head.textContent = ['이전 메일', from, sent].filter(Boolean).join(' · ');
  body.className = styles.quoteBody ?? '';
  card.setAttribute('aria-label', head.textContent);
  card.append(head, body);
  container.append(card);
  splitQuotes(body, depth + 1);
}

