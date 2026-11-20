// 서식 있는 메일 편집기(AI-32 · docs/20_frontend/outlook_benchmark.md 1.3 텍스트 서식 지정 · 1.2 삽입).
// 새 Outlook 텍스트 서식 지정 탭의 1차 항목을 한 줄 도구 모음으로 옮겼다:
// 굵게 · 기울임 · 밑줄 · 취소선 · 위 첨자 · 아래 첨자 · 글꼴 · 크기 · 형광펜 · 글꼴 색 · 글머리 기호 · 번호 · 내어쓰기 · 들여쓰기 · 인용 · 맞춤 ▾ · 줄 간격 ▾ · 서식 지우기(AI-38: 첨자 · 인용),
// 삽입 탭의 링크 · 서명 ▾(넣기 · 고르기 · 자동으로 넣기 끄기).
// contentEditable + document.execCommand로 만든다(새 의존성 없음). execCommand는 표준에서 '사용 중단'이지만 모든 브라우저가 아직 지원하고
// 대신할 표준 API가 없다(MDN). ponytail: 표 · 사진 · 서식 복사 · 스타일은 없다. 넣을 때 편집기 라이브러리(Lexical 등)로 갈지 다시 본다.
// 붙여넣은 HTML은 richText.sanitizeHtml로 거른다(우리 화면에서 스크립트가 돌지 않게). 서버도 보내기 전에 한 번 더 거른다.
import { type MouseEvent, type ReactNode, type Ref, useEffect, useImperativeHandle, useRef, useState } from 'react';
import {
  Baseline,
  Bold,
  Button,
  ChevronDown,
  Highlighter,
  IconButton,
  Italic,
  LinkIcon,
  List,
  ListIndentDecrease,
  ListIndentIncrease,
  ListOrdered,
  Menu,
  RemoveFormatting,
  Strikethrough,
  Subscript,
  Superscript,
  TextAlignStart,
  TextQuote,
  Underline,
  type MenuItemSpec,
} from '../../ui/index.ts';
import { safeHref, sanitizeHtml } from './richText.ts';
import styles from './Compose.module.css';

export interface RichEditorHandle {
  getText(): string;
  getHtml(): string;
  /** 글을 통째로 바꾼다(음성 입력 · 격식체 다시 쓰기). 서식은 사라진다 */
  setText(text: string): void;
  focus(): void;
  /** 링크 넣기 칸을 연다(파일 첨부 ▾ → 링크) */
  openLink(): void;
}

export interface SignatureOption {
  key: string;
  label: string;
  text: string;
}

interface Props {
  id: string;
  ref: Ref<RichEditorHandle | null>;
  initialText: string;
  placeholder: string;
  invalid: boolean;
  describedBy: string | undefined;
  onChange: (text: string) => void;
  signatures: SignatureOption[];
  autoSignature: boolean;
  onAutoSignatureChange: (on: boolean) => void;
  /** 도구 모음 끝에 붙는 버튼(중요도) */
  extra?: ReactNode;
  /** 입력칸 오른쪽 아래 버튼(격식체 · 음성) */
  tools?: ReactNode;
}

const FONTS = ['Aptos', '맑은 고딕', 'Arial', 'Calibri', 'Times New Roman', 'Courier New'];
// execCommand fontSize는 1~7 단계다. 단계마다 브라우저 기본 크기(pt)를 이름으로 보인다
const SIZES: [string, string][] = [
  ['1', '8'],
  ['2', '10'],
  ['3', '12'],
  ['4', '14'],
  ['5', '18'],
  ['6', '24'],
  ['7', '36'],
];
const ALIGNS: [string, string][] = [
  ['justifyLeft', '왼쪽 맞춤'],
  ['justifyCenter', '가운데 맞춤'],
  ['justifyRight', '오른쪽 맞춤'],
  ['justifyFull', '양쪽 맞춤'],
];
const LINE_HEIGHTS = ['1.0', '1.15', '1.5', '2.0', '2.5', '3.0'];

export function RichEditor({ id, ref, initialText, placeholder, invalid, describedBy, onChange, signatures, autoSignature, onAutoSignatureChange, extra, tools }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const saved = useRef<Range | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState('');

  useEffect(() => {
    if (box.current && initialText) box.current.innerText = initialText;
    // 처음 한 번만(그 뒤 글은 편집기가 들고 있다)
  }, []);

  // 도구 모음(선택 상자 · 색 고르기)을 누르면 편집기에서 포커스가 빠져 선택이 사라진다 → 마지막 선택을 기억해 되살린다
  useEffect(() => {
    const keep = () => {
      const sel = document.getSelection();
      if (sel && sel.rangeCount > 0 && box.current?.contains(sel.anchorNode)) saved.current = sel.getRangeAt(0).cloneRange();
    };
    document.addEventListener('selectionchange', keep);
    return () => document.removeEventListener('selectionchange', keep);
  }, []);

  const changed = () => onChange(box.current?.innerText ?? '');
  const restore = () => {
    const sel = document.getSelection();
    // 선택이 아직 편집기 안에 있으면(아이콘 버튼은 포커스를 뺏지 않는다) 그대로 쓴다. 기억한 선택은 selectionchange가 늦게 와 낡았을 수 있다
    if (sel && sel.rangeCount > 0 && box.current?.contains(sel.anchorNode)) return;
    box.current?.focus();
    if (saved.current && sel) {
      sel.removeAllRanges();
      sel.addRange(saved.current);
    }
  };
  const exec = (cmd: string, value?: string) => {
    restore();
    // 첨자는 <sup> · <sub> 태그로 남긴다. CSS(vertical-align)로 만들면 화면 · 서버 거르기가 지운다(AI-34 실제 보내기에서 확인)
    document.execCommand('styleWithCSS', false, cmd === 'superscript' || cmd === 'subscript' ? 'false' : 'true');
    document.execCommand(cmd, false, value);
    changed();
  };

  /** 줄 간격: 선택이 걸친 줄(블록)마다 line-height를 준다. 블록이 없으면 먼저 줄로 감싼다 */
  const lineHeight = (v: string) => {
    restore();
    const root = box.current;
    const sel = document.getSelection();
    if (!root || !sel || sel.rangeCount === 0) return;
    let blocks = Array.from(root.querySelectorAll<HTMLElement>('div, p, li')).filter((b) => sel.getRangeAt(0).intersectsNode(b));
    if (blocks.length === 0) {
      document.execCommand('formatBlock', false, 'div');
      blocks = Array.from(root.querySelectorAll<HTMLElement>('div, p, li')).filter((b) => sel.getRangeAt(0).intersectsNode(b));
    }
    for (const b of blocks) b.style.lineHeight = v;
    changed();
  };

  const insertLink = () => {
    const raw = linkUrl.trim();
    const url = /^[a-z][a-z0-9+.-]*:/i.test(raw) ? raw : `https://${raw}`;
    setLinkOpen(false);
    setLinkUrl('');
    if (!raw || !safeHref(url)) return;
    restore();
    const sel = document.getSelection();
    if (sel && !sel.isCollapsed) document.execCommand('createLink', false, url);
    else {
      const a = document.createElement('a');
      a.href = url;
      a.textContent = raw;
      document.execCommand('insertHTML', false, a.outerHTML);
    }
    changed();
  };

  const insertSignature = (text: string) => {
    restore();
    const root = box.current;
    if (!root) return;
    // 아웃룩처럼 커서 자리에 넣는다. 자동으로 넣기와 겹치지 않게 자동은 끈다
    document.execCommand('insertText', false, `\n\n${text.trim()}`);
    onAutoSignatureChange(false);
    changed();
  };

  useImperativeHandle(ref, () => ({
    getText: () => box.current?.innerText ?? '',
    getHtml: () => box.current?.innerHTML ?? '',
    setText: (t) => {
      if (box.current) box.current.innerText = t;
      changed();
    },
    focus: () => box.current?.focus(),
    openLink: () => setLinkOpen(true),
  }));

  const signatureItems: MenuItemSpec[] = [
    ...signatures.map((s) => ({ key: s.key, label: s.label, onSelect: () => insertSignature(s.text) })),
    {
      key: 'auto',
      label: autoSignature ? '보낼 때 자동으로 넣기 끄기' : '보낼 때 자동으로 넣기 켜기',
      onSelect: () => onAutoSignatureChange(!autoSignature),
      separatorBefore: signatures.length > 0,
      disabled: signatures.length === 0,
    },
  ];
  // 누르는 동안 편집기 포커스를 뺏지 않는다(선택이 그대로 남게)
  const keepFocus = (e: MouseEvent) => e.preventDefault();
  const tool = (label: string, icon: ReactNode, cmd: string) => (
    <IconButton label={label} icon={icon} onMouseDown={keepFocus} onClick={() => exec(cmd)} />
  );

  return (
    <div className={styles.editor}>
      <div className={styles.toolbar} role="toolbar" aria-label="텍스트 서식" aria-controls={id}>
        <select className={styles.toolSelect} aria-label="글꼴" defaultValue="" onChange={(e) => e.target.value && exec('fontName', e.target.value)}>
          <option value="" disabled>
            글꼴
          </option>
          {FONTS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <select className={styles.toolSelect} aria-label="글꼴 크기" defaultValue="" onChange={(e) => e.target.value && exec('fontSize', e.target.value)}>
          <option value="" disabled>
            크기
          </option>
          {SIZES.map(([v, pt]) => (
            <option key={v} value={v}>
              {pt}
            </option>
          ))}
        </select>
        {tool('굵게', <Bold size={20} aria-hidden="true" />, 'bold')}
        {tool('기울임꼴', <Italic size={20} aria-hidden="true" />, 'italic')}
        {tool('밑줄', <Underline size={20} aria-hidden="true" />, 'underline')}
        {tool('취소선', <Strikethrough size={20} aria-hidden="true" />, 'strikeThrough')}
        {tool('위 첨자', <Superscript size={20} aria-hidden="true" />, 'superscript')}
        {tool('아래 첨자', <Subscript size={20} aria-hidden="true" />, 'subscript')}
        <label className={styles.colorTool} title="텍스트 강조 색(형광펜)">
          <Highlighter size={20} aria-hidden="true" />
          <span className="sr-only">텍스트 강조 색</span>
          <input type="color" defaultValue="#ffff00" onChange={(e) => exec('hiliteColor', e.target.value)} />
        </label>
        <label className={styles.colorTool} title="글꼴 색">
          <Baseline size={20} aria-hidden="true" />
          <span className="sr-only">글꼴 색</span>
          <input type="color" defaultValue="#c00000" onChange={(e) => exec('foreColor', e.target.value)} />
        </label>
        {tool('글머리 기호', <List size={20} aria-hidden="true" />, 'insertUnorderedList')}
        {tool('번호 매기기', <ListOrdered size={20} aria-hidden="true" />, 'insertOrderedList')}
        {tool('내어쓰기', <ListIndentDecrease size={20} aria-hidden="true" />, 'outdent')}
        {tool('들여쓰기', <ListIndentIncrease size={20} aria-hidden="true" />, 'indent')}
        <IconButton label="인용" icon={<TextQuote size={20} aria-hidden="true" />} onMouseDown={keepFocus} onClick={() => exec('formatBlock', 'blockquote')} />
        <Menu
          trigger={<IconButton label="맞춤" icon={<TextAlignStart size={20} aria-hidden="true" />} onMouseDown={keepFocus} />}
          items={ALIGNS.map(([cmd, label]) => ({ key: cmd, label, onSelect: () => exec(cmd) }))}
        />
        <Menu
          trigger={
            <Button variant="ghost" size="sm" onMouseDown={keepFocus}>
              줄 간격 <ChevronDown size={16} aria-hidden="true" />
            </Button>
          }
          items={LINE_HEIGHTS.map((v) => ({ key: v, label: v, onSelect: () => lineHeight(v) }))}
        />
        {tool('서식 지우기', <RemoveFormatting size={20} aria-hidden="true" />, 'removeFormat')}
        <IconButton label="링크" icon={<LinkIcon size={20} aria-hidden="true" />} onMouseDown={keepFocus} onClick={() => setLinkOpen(true)} />
        <Menu
          trigger={
            <Button variant="ghost" size="sm" onMouseDown={keepFocus}>
              서명 <ChevronDown size={16} aria-hidden="true" />
            </Button>
          }
          items={signatureItems}
        />
        {extra}
      </div>
      {linkOpen && (
        <form
          className={styles.linkRow}
          onSubmit={(e) => {
            e.preventDefault();
            insertLink();
          }}
        >
          <input
            className={styles.input}
            type="url"
            aria-label="링크 주소"
            placeholder="https://"
            value={linkUrl}
            autoFocus
            onChange={(e) => setLinkUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setLinkOpen(false);
            }}
          />
          <Button size="sm" type="submit">
            넣기
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setLinkOpen(false)}>
            취소
          </Button>
        </form>
      )}
      <div className={styles.contentBox}>
        <div
          ref={box}
          id={id}
          className={styles.textarea}
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-multiline="true"
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          data-placeholder={placeholder}
          onInput={changed}
          onKeyDown={(e) => {
            // 인용의 빈 줄에서 Enter → 인용에서 나온다(아웃룩 · 워드와 같게, AI-42). 브라우저는 빈 인용 줄을 계속 만든다
            if (e.key !== 'Enter' || e.shiftKey || e.nativeEvent.isComposing) return;
            const node = document.getSelection()?.anchorNode;
            const el = node instanceof Element ? node : node?.parentElement;
            const quote = el?.closest('blockquote');
            if (!quote || !box.current?.contains(quote)) return;
            const line = el?.closest('div, p, li');
            if (((line && quote.contains(line) ? line : quote).textContent ?? '').trim() !== '') return;
            e.preventDefault();
            document.execCommand('formatBlock', false, 'div');
            changed();
          }}
          onPaste={(e) => {
            const html = e.clipboardData.getData('text/html');
            if (!html) return; // 일반 텍스트는 브라우저가 그대로 넣는다
            e.preventDefault();
            const sel = document.getSelection();
            if (!sel || sel.rangeCount === 0) return;
            const range = sel.getRangeAt(0);
            range.deleteContents();
            const frag = sanitizeHtml(html);
            const last = frag.lastChild;
            range.insertNode(frag);
            if (last) {
              range.setStartAfter(last);
              range.collapse(true);
              sel.removeAllRanges();
              sel.addRange(range);
            }
            changed();
          }}
        />
        {tools}
      </div>
    </div>
  );
}
