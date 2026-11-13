// 리마인더 버튼 줄 + ⋯ 메뉴 (FE-16). 상세 · 🔔 팝업 · 패널 리마인더 탭이 같은 부품을 쓴다.
// - 버튼은 최대 3개(팝업은 2개), 오른쪽 정렬, 보조 → 주 순서. 빨강 채움은 쓰지 않는다(확정 동작이 아님, UX-D18):
//   주 버튼은 테두리, 보조는 글자 버튼(패널 제안 카드와 같은 모양)
// - [미루기]는 대시보드와 같은 시각 메뉴(lib/snooze). 업무가 여럿인 항목(기한 몰림 '하나 미루기')은 업무를 골라 내일 아침으로
// - ⋯: 내 일 아님 · 이 유형 알림 끄기 · 잘못 알아챘어요(AI 신호 유형만). 버튼에 이미 있는 동작은 메뉴에 다시 두지 않는다
import type { ReminderItem } from '../../api/contract.ts';
import type { TaskId } from '../../api/types.ts';
import { snoozeOptions } from '../../lib/snooze.ts';
import { Button, ChevronDown, Ellipsis, IconButton, Menu, cx } from '../../ui/index.ts';
import { drawableActions, MAX_BUTTONS, MENU_LABEL, menuKinds } from './reminderModel.ts';
import styles from './ReminderActions.module.css';
import type { ReminderRunner } from './useReminderRunner.ts';

interface Props {
  item: ReminderItem;
  runner: ReminderRunner;
  /** 서버 시계(나중에 메뉴 시각) */
  now: () => number;
  /** 이 유형 알림을 껐나(⋯ 메뉴 '켜기') */
  muted?: boolean;
  limit?: number;
  /** ⋯ 메뉴를 그릴지(팝업은 버튼만) */
  withMenu?: boolean;
  /** 명령 진행 중(초안 · 그날 업무 버튼을 잠근다) */
  busy?: boolean;
  /** 업무 이름(하나 미루기 메뉴) */
  taskText?: (id: TaskId) => string | null;
  className?: string;
}

export function ReminderActions({ item, runner, now, muted = false, limit = MAX_BUTTONS, withMenu = true, busy = false, taskText, className }: Props) {
  const drawn = drawableActions(item, runner.ctx, limit);
  const locked = runner.pending.has(item.key);
  const menu = withMenu ? menuKinds(item, muted, drawableActions(item, runner.ctx)) : [];
  if (drawn.length === 0 && menu.length === 0) return null;

  return (
    <div className={cx(styles.row, className)}>
      {drawn.map(({ action, plan }) => {
        const variant = action.primary ? 'secondary' : 'ghost';
        const disabled = locked || (plan.type === 'command' && busy);
        if (plan.type === 'snooze') {
          const items =
            plan.taskIds.length > 1
              ? plan.taskIds.map((id) => {
                  const tomorrow = snoozeOptions(now()).find((o) => o.key === 'tomorrow-0830')!;
                  return {
                    key: String(id),
                    label: taskText?.(id) ?? `업무 ${id}`,
                    detail: `내일 아침 ${tomorrow.detail}`,
                    disabled,
                    onSelect: () => void runner.run(item, plan, { untilMs: tomorrow.untilMs, taskId: id }),
                  };
                })
              : snoozeOptions(now()).map((o) => ({
                  key: o.key,
                  label: o.label,
                  detail: o.detail,
                  disabled,
                  onSelect: () => void runner.run(item, plan, { untilMs: o.untilMs }),
                }));
          return (
            <Menu
              key={action.id}
              align="end"
              trigger={
                <Button size="sm" variant={variant} aria-disabled={disabled || undefined}>
                  {action.label}
                  <ChevronDown size={16} aria-hidden="true" />
                </Button>
              }
              items={items}
            />
          );
        }
        return (
          <Button key={action.id} size="sm" variant={variant} aria-disabled={disabled || undefined} onClick={() => !disabled && void runner.run(item, plan)}>
            {action.label}
          </Button>
        );
      })}
      {menu.length > 0 && (
        <Menu
          align="end"
          trigger={<IconButton className={styles.more} label="이 리마인더 메뉴" icon={<Ellipsis size={16} aria-hidden="true" />} />}
          items={menu.map((kind, i) => ({
            key: kind,
            label: MENU_LABEL[kind],
            disabled: locked,
            separatorBefore: i > 0 && kind === 'wrong_signal',
            onSelect: () => void runner.runMenu(item, kind),
          }))}
        />
      )}
    </div>
  );
}
