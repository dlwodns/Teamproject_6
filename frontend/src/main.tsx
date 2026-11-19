import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/outfit'; // 영문 표시 · 숫자 (SIL OFL 1.1, public/licenses/Outfit-OFL.txt)
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './styles/tokens.css';
import './styles/theme.css';
import './styles/global.css';
import { App } from './app/App.tsx';
import { applyTheme, readTheme } from './lib/theme.ts';

applyTheme(readTheme()); // 첫 화면부터 고른 테마로

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
