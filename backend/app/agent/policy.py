"""확인이 필요한지 판정 (BE-11, D37, docs/30_backend/detail.md 3절). ai 출력에 확인 여부를 넣지 않고 백엔드 규칙만 본다.

| kind | 대상 | 확인 |
|---|---|---|
| query · display | — | 없음 |
| state_change | 확정 대상 1건 | 없음(실행 후 되돌리기) |
| state_change | 2건 이상 또는 후보 여러 개 | 확인 카드(미리보기 → 실행) |
| settings | — | 확인 카드 |
| send | — | 항상 미리보기 + 확인 |
"""
from app.agent.tools.registry import ActionDef


def needs_confirm(action: ActionDef, resolved_ids: list[int], ambiguous: bool) -> bool:
    if action.kind in ("query", "display"):
        return False
    if action.kind in ("settings", "send"):
        return True
    return len(resolved_ids) >= 2 or ambiguous  # state_change
