// 브라우저 세션(backend app/api/session.py, AUTH_MODE=session). 비밀번호 없이 브라우저마다 사용자 하나.
// 세션 값은 httpOnly 쿠키라 화면 코드가 읽거나 저장하지 않는다. 같은 출처(/api)라 fetch가 쿠키를 함께 보낸다.
// 실패해도 화면은 띄운다 — 그 뒤 요청이 401로 실패해 화면마다 오류 상태를 보인다(모의 데이터로 바꾸지 않는다).
export async function startSession(baseUrl: string, fetchFn: typeof fetch = fetch): Promise<void> {
  try {
    await fetchFn(`${baseUrl}/session`, { method: 'POST', credentials: 'same-origin', headers: { Accept: 'application/json' } });
  } catch {
    // 연결 실패: 화면의 요청들이 NetworkError로 알린다
  }
}
