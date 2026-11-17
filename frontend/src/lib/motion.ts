// 움직임 줄이기(wireframe P5): 기기 설정('동작 줄이기')이나 CNE 설정(reduce_motion → <html data-reduce-motion>, AppLayout이 붙임) 중
// 하나라도 켜져 있으면 줄인다. CSS 쪽은 global.css가 같은 두 조건을 본다.
export const REDUCE_MOTION_ATTR = 'data-reduce-motion';

/** 기기 설정만. 설정 화면에서 '기기에서 이미 켜짐'을 보일 때 쓴다 */
export function osReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** 지금 움직임을 줄여야 하나(기기 설정 또는 CNE 설정) */
export function reducedMotion(): boolean {
  return (typeof document !== 'undefined' && document.documentElement.hasAttribute(REDUCE_MOTION_ATTR)) || osReducedMotion();
}
