// 서식 있는 편집기(AI-32) 붙여넣기 거르기. 서버(backend app/services/html_clean.py)와 같은 허용 목록이다.
// 붙여넣은 HTML은 DOMParser로 따로 읽어(스크립트 · 이미지가 실행 · 로드되지 않는 문서) 허용한 태그 · 속성만 새로 만든다.
// contentEditable에 HTML을 그대로 넣으면 <img onerror> 같은 것이 우리 화면에서 실행되므로 반드시 거친다.

export const TAGS = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'DEL', 'BR', 'P', 'DIV', 'SPAN', 'UL', 'OL', 'LI', 'A', 'FONT', 'BLOCKQUOTE', 'SUB', 'SUP']);
/** 안의 글자까지 버리는 태그 */
export const DROP = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'TEMPLATE', 'NOSCRIPT', 'HEAD', 'TITLE', 'TEXTAREA', 'SELECT', 'BUTTON', 'FORM', 'INPUT']);
const ATTRS = new Set(['style', 'href', 'color', 'face', 'size', 'align']);
const STYLE_PROPS = new Set([
  'color',
  'background-color',
  'font-family',
  'font-size',
  'font-weight',
  'font-style',
  'text-decoration',
  'text-decoration-line',
  'text-align',
  'line-height',
  'margin-left',
  'padding-left',
]);
const BAD_VALUE = /url\s*\(|expression\s*\(|javascript:|[<>\\]/i;

/** style 값에서 서식 속성만 남긴다 */
export function cleanStyle(style: string): string {
  return style
    .split(';')
    .map((d) => {
      const at = d.indexOf(':');
      if (at < 0) return null;
      const prop = d.slice(0, at).trim().toLowerCase();
      const value = d.slice(at + 1).trim();
      return STYLE_PROPS.has(prop) && value && !BAD_VALUE.test(value) ? `${prop}: ${value}` : null;
    })
    .filter((x) => x !== null)
    .join('; ');
}

/** 링크는 http · https · mailto만 */
export const safeHref = (href: string): boolean => /^(?:https?:|mailto:)/i.test(href.trim());

function cleanNode(src: Node, doc: Document): Node[] {
  if (src.nodeType === Node.TEXT_NODE) return [doc.createTextNode(src.textContent ?? '')];
  if (src.nodeType !== Node.ELEMENT_NODE) return [];
  const el = src as Element;
  if (DROP.has(el.tagName)) return [];
  const kids = Array.from(el.childNodes).flatMap((c) => cleanNode(c, doc));
  if (!TAGS.has(el.tagName)) return kids; // 모르는 태그는 벗기고 글자만
  const out = doc.createElement(el.tagName.toLowerCase());
  for (const { name, value } of Array.from(el.attributes)) {
    if (!ATTRS.has(name)) continue;
    const v = name === 'style' ? cleanStyle(value) : value;
    if (name === 'href' && !safeHref(v)) continue;
    if (v) out.setAttribute(name, v);
  }
  out.append(...kids);
  return [out];
}

/** 붙여넣을 HTML → 거른 조각(현재 문서 소속) */
export function sanitizeHtml(html: string, doc: Document = document): DocumentFragment {
  const parsed = new DOMParser().parseFromString(html, 'text/html');
  const frag = doc.createDocumentFragment();
  frag.append(...Array.from(parsed.body.childNodes).flatMap((n) => cleanNode(n, doc)));
  return frag;
}

/** 일반 텍스트 → 보낼 HTML 조각(템플릿 인사 · 맺음 · 서명). 줄바꿈은 <br> */
export const textToHtml = (text: string): string =>
  text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/\n/g, '<br>');

/** 편집기 HTML에 서식이 있나(없으면 글 그대로 보내 기존 동작과 같게) */
export const hasFormatting = (html: string): boolean => /<(?!br\b|\/?div\b)[a-z]/i.test(html) || /\sstyle=/i.test(html);
