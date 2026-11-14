/** 클래스 이름 합치기(거짓 값은 뺀다) */
export function cx(...names: Array<string | false | null | undefined>): string {
  return names.filter(Boolean).join(' ');
}
