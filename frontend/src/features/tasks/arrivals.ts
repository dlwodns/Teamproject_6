// 새로 들어온 업무 줄 표시(AI-42): 대시보드를 처음 그린 뒤 새로 나타난 업무만 '들어오는' 움직임을 준다.
// 처음 화면의 업무는 움직이지 않는다(ready 전). 같은 업무가 여러 칸(긴급 + 유형)에 있으면 같은 그리기에서 함께 움직인다.
const seen = new Set<string>();
let ready = false;

/** 이 업무가 처음 그린 뒤 새로 들어왔나(그리는 순간 한 번 판단) */
export const isArrival = (id: string): boolean => ready && !seen.has(id);
/** 그린 뒤 기억한다 */
export const markSeen = (id: string): void => void seen.add(id);
/** 첫 화면을 다 그렸다 — 이후 나타나는 업무는 새로 들어온 것 */
export const arrivalsReady = (): void => {
  ready = true;
};
