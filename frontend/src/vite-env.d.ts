/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_MODE?: string;
  readonly VITE_API_BASE?: string;
  /** 음성인식 방식(D29): browser(기본) · server(서버 Whisper, 아직 없음 → 🎤 숨김) */
  readonly VITE_STT_MODE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
