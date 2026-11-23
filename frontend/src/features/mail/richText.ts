// 서식 있는 편집기(AI-32) 붙여넣기 거르기. 서버(backend app/services/html_clean.py)와 같은 허용 목록이다.
// 붙여넣은 HTML은 DOMParser로 따로 읽어(스크립트 · 이미지가 실행 · 로드되지 않는 문서) 허용한 태그 · 속성만 새로 만든다.
// contentEditable에 HTML을 그대로 넣으면 <img onerror> 같은 것이 우리 화면에서 실행되므로 반드시 거친다.

export const TAGS = new Set(['B', 'STRONG', 'I', 'EM', 'U', 'S', 'STRIKE', 'DEL', 'BR', 'P', 'DIV', 'SPAN', 'UL', 'OL', 'LI', 'A', 'FONT', 'BLOCKQUOTE', 'SUB', 'SUP',
  // AI-42 받은 메일 읽기: 표 · 메일 안 그림(서버가 cid를 /api/mails/…/inline/… 으로 바꿔 둔 것만)
  'TABLE', 'THEAD', 'TBODY', 'TFOOT', 'TR', 'TD', 'TH', 'CAPTION', 'IMG', 'HR']);
/** 안의 글자까지 버리는 태그 */
export const DROP = new Set(['SCRIPT', 'STYLE', 'IFRAME', 'OBJECT', 'EMBED', 'SVG', 'MATH', 'TEMPLATE', 'NOSCRIPT', 'HEAD', 'TITLE', 'TEXTAREA', 'SELECT', 'BUTTON', 'FORM', 'INPUT']);
const ATTRS = new Set(['style', 'href', 'color', 'face', 'size', 'align', 'colspan', 'rowspan', 'width', 'height', 'alt', 'border', 'src']);
/** 그림은 우리 서버가 내주는 메일 안 그림과, 쓰는 중 넣은 · 붙여넣은 그림(data: png · jpeg · gif · webp, AI-39)만. 바깥 주소는 지운다 */
const safeSrc = (src: string): boolean => /^\/api\/mails\/\d+\/inline\//.test(src.trim()) || /^data:image\/(?:png|jpeg|gif|webp);base64,/i.test(src.trim());
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
  // AI-39 표 · 사진(서버 html_clean과 같다)
  'border',
  'border-collapse',
  'padding',
  'width',
  'max-width',
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
  if (el.tagName === 'IMG' && !safeSrc(el.getAttribute('src') ?? '')) return [];
  const out = doc.createElement(el.tagName.toLowerCase());
  for (const { name, value } of Array.from(el.attributes)) {
    if (!ATTRS.has(name)) continue;
    const v = name === 'style' ? cleanStyle(value) : value;
    if (name === 'href' && !safeHref(v)) continue;
    if (name === 'src' && el.tagName !== 'IMG') continue;
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

/** AI-39 표 넣기: 행 × 열 빈 표. 테두리 · 칸 여백은 받는 쪽 아웃룩에서도 보이게 속성 · 인라인 스타일로. 뒤에 빈 줄을 둬 표 밖으로 나올 수 있게 */
export function tableHtml(rows: number, cols: number): string {
  const cell = '<td style="padding: 4px 8px">&nbsp;</td>';
  const tr = `<tr>${cell.repeat(cols)}</tr>`;
  return `<table border="1" style="border-collapse: collapse; width: 100%"><tbody>${tr.repeat(rows)}</tbody></table><div><br></div>`;
}

/** AI-39 그림 넣기: 넣을 수 있는 형식 · 크기(Graph 첨부 POST 3MB 미만, 서버와 같다) */
export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp'];
export const IMAGE_MAX_BYTES = 3 * 1024 * 1024;
export function imageProblem(file: { type: string; size: number }): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return 'PNG · JPG · GIF · WebP 그림만 넣을 수 있습니다';
  if (file.size >= IMAGE_MAX_BYTES) return '그림은 3MB보다 작아야 합니다. 큰 그림은 파일로 첨부해 주세요';
  return null;
}
