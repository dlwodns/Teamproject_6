// 아이콘 (FE-D16): lucide-react(ISC)에서 쓰는 것만 다시 내보낸다. 크기는 16 · 20px, 색은 currentColor.
// 장식 아이콘은 aria-hidden으로 쓰고, 뜻은 옆 글자나 버튼 이름이 말한다.
import type { SVGProps } from 'react';

export {
  AlarmClock,
  ArrowUp,
  Bell,
  Building,
  Check,
  CircleCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Ellipsis,
  Inbox,
  Info,
  Mic,
  PanelLeft,
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
