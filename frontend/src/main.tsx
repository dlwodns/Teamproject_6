import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/outfit'; // 영문 표시 · 숫자 (SIL OFL 1.1, public/licenses/Outfit-OFL.txt)
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './styles/tokens.css';
import './styles/theme.css';
import './styles/global.css';
import { App } from './app/App.tsx';
import { applyTheme, readTheme } from './lib/theme.ts';
import { sessionReady } from './api/client.ts';

applyTheme(readTheme()); // 첫 화면부터 고른 테마로

// 실제 모드는 세션을 받은 뒤 띄운다(첫 요청이 401로 나지 않게, INF-11 11-25)
void sessionReady.finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
