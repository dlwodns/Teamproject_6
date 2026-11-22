// 아이콘 (FE-D16): lucide-react(ISC)에서 쓰는 것만 다시 내보낸다. 크기는 16 · 20px, 색은 currentColor.
// 장식 아이콘은 aria-hidden으로 쓰고, 뜻은 옆 글자나 버튼 이름이 말한다.
import type { SVGProps } from 'react';

export {
  AlarmClock,
  ArrowDown,
  Baseline,
  Bold,
  CircleAlert,
  Highlighter,
  Italic,
  Languages,
  Link as LinkIcon,
  List,
  ListIndentDecrease,
  ListIndentIncrease,
  ListOrdered,
  RemoveFormatting,
  Strikethrough,
  Subscript,
  Superscript,
  TextQuote,
  TextAlignStart,
  Underline,
  ArrowUp,
  Bell,
  Building,
  Check,
  CircleCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Ellipsis,
  Inbox,
  Info,
  Keyboard,
  Mail as MailIcon,
  MailOpen,
  Maximize2 as Maximize,
  Mic,
  Minus,
  PenLine,
  PanelLeft,
  SquarePen,
  Pin,
  PinOff,
  Reply,
  RotateCcw,
  Sparkles,
  Star,
  X,
} from 'lucide-react';
export type { LucideIcon, LucideProps } from 'lucide-react';

interface RankIconProps extends Omit<SVGProps<SVGSVGElement>, 'ref'> {
  size?: 16 | 20 | 24;
}

/**
 * 상급자 계급장(어깨 계급장 ▲ 모양, UX-D13). lucide에 없어 Tabler Icons의 `military-rank`(outline) 그림을 복사했다.
 * Tabler Icons © Paweł Kuna, MIT License — https://github.com/tabler/tabler-icons/blob/main/LICENSE
 */
export function RankIcon({ size = 16, ...props }: RankIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M18 7v12a2 2 0 0 1 -2 2h-8a2 2 0 0 1 -2 -2v-12l6 -4z" />
      <path d="M10 13l2 -1l2 1" />
      <path d="M10 17l2 -1l2 1" />
      <path d="M10 9l2 -1l2 1" />
    </svg>
  );
}

const svgBase = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
});

/** AI-45 [요약]: 글머리 목록 상자 + 오른쪽 위 반짝임(사용자가 준 모양, 11-22). 우리가 그렸다 */
export function SummaryIcon({ size = 16, ...props }: RankIconProps) {
  return (
    <svg {...svgBase(size)} {...props}>
      <path d="M14 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-8" />
      <path d="M7 9h.01M7 13h.01M7 17h.01M11 9h2M11 13h6M11 17h6" />
      <path d="M19 1.8l.8 2.4 2.4.8-2.4.8-.8 2.4-.8-2.4-2.4-.8 2.4-.8z" fill="currentColor" strokeWidth={1} />
    </svg>
  );
}

/** AI-45 [번역]: 겹친 두 상자 '가' · 'A'(구글 번역의 두 언어 상자 모양을 참고해 우리가 그렸다, 11-22) */
export function TranslateIcon({ size = 16, ...props }: RankIconProps) {
  return (
    <svg {...svgBase(size)} {...props}>
      <path d="M14 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3" />
      <path d="M5.5 6.5h2.8c0 2-1 3.4-2.8 4.3M10.8 5.2v6.6M10.8 8.4h1.4" strokeWidth={1.6} />
      <rect x="10" y="10" width="11" height="11" rx="2" />
      <path d="M13 18.5l2.5-6 2.5 6M13.9 16.4h3.2" strokeWidth={1.6} />
    </svg>
  );
}
