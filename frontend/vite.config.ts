import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// 개발 서버 프록시
// - 화면은 같은 출처의 /api/... 로만 부른다(backend에 CORS 설정이 없다).
// - backend에 실제로 있는 라우트는 접두어 없는 GET /health 하나뿐이다(backend/app/main.py).
//   그래서 /api/health 만 /health 로 바꿔 넘기고, 나머지 /api/... 는 경로를 바꾸지 않고 그대로 넘긴다.
//   구조도 8절의 /api 경로([제안])를 backend가 어떤 접두어로 열지는 BE-3에서 정한다. 정해지면 아래 규칙을 맞춘다.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: {
      host: '127.0.0.1',
      strictPort: true,
      proxy: {
        '^/api/health$': { target, changeOrigin: true, rewrite: () => '/health' },
        '/api/': { target, changeOrigin: true },
      },
    },
    preview: { host: '127.0.0.1', strictPort: true },
  };
});
