// 설정 > 메일 계정 (BE-7, 11-19): Outlook 로그인으로 계정을 연결하고, 지금 받기 · 연결 끊기를 한다.
// - [Outlook 계정 연결] → 서버가 준 Microsoft 로그인 주소로 이동 → 로그인 뒤 서버가 #/settings/accounts?outlook=connected|error로 돌려보낸다
// - 돌아온 결과는 알림으로 한 번 보이고 주소의 ?outlook=…을 지운다(새로고침해도 다시 뜨지 않게)
// - 서버가 더미 모드면(outlookEnabled 거짓 · 연결 시작 NotAvailableError) 버튼 대신 안내 문구
import { useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import type { MailAccount } from '../../api/contract.ts';
import { NotAvailableError } from '../../api/errors.ts';
import { accountsKey, queryKeys, useAccountsQuery, useConnectOutlook, useDisconnectAccount, useSyncAccount } from '../../api/queries.ts';
import { Button, StateRow, useToast } from '../../ui/index.ts';
import styles from './SettingsPage.module.css';

const REASON: Record<string, string> = {
  denied: '로그인에서 권한을 허용하지 않았습니다',
  expired: '연결 시간이 지났습니다. 다시 눌러 주세요',
  failed: 'Microsoft 로그인에 실패했습니다',
};

const kst = (ms: number) =>
  new Date(ms).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

/** 로그인에서 돌아온 결과(?outlook=…)를 알림으로 보이고 주소에서 지운다 */
function useLoginResult() {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const qc = useQueryClient();
  const result = params.get('outlook');
  const reason = params.get('reason');
  useEffect(() => {
    if (!result) return;
    if (result === 'connected') {
      toast.show({ id: 'outlook-login', kind: 'info', title: 'Outlook 계정을 연결했습니다' });
      void qc.invalidateQueries({ queryKey: accountsKey });
      void qc.invalidateQueries({ queryKey: queryKeys.dashboard });
    } else {
      toast.show({ id: 'outlook-login', kind: 'error', title: 'Outlook을 연결하지 못했습니다', description: REASON[reason ?? ''] ?? REASON.failed });
    }
    setParams({}, { replace: true });
  }, [result, reason, toast, qc, setParams]);
}

function AccountRow({ a }: { a: MailAccount }) {
  const sync = useSyncAccount();
  const disconnect = useDisconnectAccount();
  const connect = useConnectOutlook();
  const toast = useToast();
  const outlook = a.provider === 'outlook_graph';
  const status = !outlook ? '시연 계정' : a.connected ? '연결됨' : '연결 끊김';
  const synced = a.lastSyncedMs !== null ? ` · 마지막으로 받음 ${kst(a.lastSyncedMs)}` : '';
  const busy = sync.isPending || disconnect.isPending || connect.isPending;
  return (
    <div className={styles.infoRow}>
      <dt>{outlook ? 'Outlook' : '시연'}</dt>
      <dd>
        <span>{a.email}</span>
        {a.aliases.length > 0 && <p className={styles.hint}>받는 주소로도 봄: {a.aliases.join(' · ')}</p>}
        <p className={styles.hint}>
          {status}
          {synced}
        </p>
        {outlook && (
          <span className={styles.inline}>
            {a.connected ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() =>
                    sync.mutate(a.id, {
                      onSuccess: (r) => toast.show({ id: 'outlook-sync', kind: 'info', title: r.added ? `새 메일 ${r.added}통을 받았습니다` : '새 메일이 없습니다' }),
                      onError: () => toast.show({ id: 'outlook-sync', kind: 'error', title: '메일을 받지 못했습니다', description: '연결이 끊겼으면 다시 연결해 주세요' }),
                    })
                  }
                >
                  {sync.isPending ? '받는 중…' : '지금 받기'}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() =>
                    disconnect.mutate(a.id, { onError: () => toast.show({ id: 'outlook-disconnect', kind: 'error', title: '연결을 끊지 못했습니다' }) })
                  }
                >
                  연결 끊기
                </Button>
              </>
            ) : (
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  connect.mutate(undefined, {
                    onSuccess: (url) => window.location.assign(url),
                    onError: () => toast.show({ id: 'outlook-login', kind: 'error', title: 'Outlook 연결을 시작하지 못했습니다' }),
                  })
                }
              >
                다시 연결
              </Button>
            )}
          </span>
        )}
      </dd>
    </div>
  );
}

export function MailAccounts() {
  useLoginResult();
  const accounts = useAccountsQuery();
  const connect = useConnectOutlook();
  const toast = useToast();
  if (accounts.isNotAvailable) return <p className={styles.hint}>이 서버에는 계정 연결 기능이 없습니다.</p>;
  if (!accounts.data) return <StateRow state={accounts.isError ? 'error' : 'loading'} onRetry={() => void accounts.refetch()} />;
  const off = !accounts.data.outlookEnabled || connect.error instanceof NotAvailableError;
  return (
    <div className={styles.form}>
      {accounts.data.items.length > 0 && (
        <dl className={styles.info}>
          {accounts.data.items.map((a) => (
            <AccountRow key={a.id} a={a} />
          ))}
        </dl>
      )}
      {off ? (
        <p className={styles.hint}>서버가 시연 데이터 모드라 Outlook을 연결할 수 없습니다(MAIL_SOURCE=outlook_graph로 켜기).</p>
      ) : (
        <span className={styles.inline}>
          <Button
            disabled={connect.isPending}
            onClick={() =>
              connect.mutate(undefined, {
                onSuccess: (url) => window.location.assign(url),
                onError: (e) => {
                  if (!(e instanceof NotAvailableError)) toast.show({ id: 'outlook-login', kind: 'error', title: 'Outlook 연결을 시작하지 못했습니다' });
                },
              })
            }
          >
            {connect.isPending ? 'Microsoft로 이동 중…' : 'Outlook 계정 연결'}
          </Button>
        </span>
      )}
      <p className={styles.hint}>
        Microsoft 로그인 화면에서 메일 · 일정 권한을 허용하면 최근 14일 메일을 받아 오고, 그 뒤로 1분마다 새 메일을 받습니다. 연결을 끊어도 이미 받은 메일과 업무는 남습니다.
      </p>
    </div>
  );
}
