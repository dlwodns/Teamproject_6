"""에이전트 시나리오 평가 실행기 (PL-16 5.5절, tau2-bench 방식을 줄인 것).

한 시나리오 = 처음 상태(fixture) + 순서대로 부르는 요청(steps) + 기대 최종 상태(final).
채점은 두 가지만 본다: ① 최종 상태가 모두 맞는가 ② 금지 행동이 0건인가.

HTTP만 쓴다. 그래서 테스트(TestClient)와 실제 서버(시연 · 배포)에 같은 시나리오를 그대로 돌린다.
백엔드가 갖춰야 하는 개발용 경로 세 개: POST /api/dev/scenario/load · POST /api/dev/scenario/clock ·
GET /api/dev/scenario/state (backend/app/api/dev_scenario.py).

이 파일은 외부 패키지를 쓰지 않는다. 요청을 보내는 함수(call)는 부르는 쪽이 넘긴다
(backend 테스트는 TestClient, 명령줄은 run_scenarios.py의 httpx).
"""
import copy
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CASES = Path(__file__).resolve().parent / "cases"
Call = Callable[[str, str, dict | None, dict | None], tuple[int, object]]  # (method, path, json, headers) → (status, body)
VAR = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
STEP_KEYS = {"do", "body", "headers", "expect", "save", "clock"}
EXPECT_KEYS = {"status", "match", "len", "contains", "not_contains"}
FINAL_KEYS = {"tasks", "log_count", "live_count", "vias", "contacts", "unused_previews", "hide_count",
              "preview_count", "forbidden_actions"}
MISSING = object()


@dataclass
class Result:
    id: str
    title: str
    passed: bool = True
    forbidden: int = 0
    failures: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.passed = False
        self.failures.append(msg)


def load_cases(only: list[str] | None = None) -> list[dict]:
    base = json.loads((CASES / "_base.json").read_text(encoding="utf-8"))
    out = []
    for p in sorted(CASES.glob("SC-*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        if only and case["id"] not in only:
            continue
        fx = case.get("fixture", {})
        if fx.pop("base", False):
            merged = copy.deepcopy(base)
            for k, v in fx.items():
                merged[k] = (merged.get(k, []) + v) if isinstance(v, list) else v
            case["fixture"] = merged
        out.append(case)
    return out


# ---------- 값 꺼내기 · 바꿔 넣기 ----------

def pick(body, path: str):
    """'a.0.b' · 'items[*].state' 형식. [*]는 목록의 각 항목에서 나머지 경로를 꺼내 목록으로 돌려준다."""
    cur = body
    parts = path.replace("[*]", ".*").split(".") if path else []
    for i, part in enumerate(parts):
        if part == "*":
            rest = ".".join(parts[i + 1:])
            return [pick(x, rest) for x in cur]
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def subst(value, env: dict):
    if isinstance(value, str):
        whole = VAR.fullmatch(value)
        if whole:
            return env[whole.group(1)]
        return VAR.sub(lambda m: str(env[m.group(1)]), value)
    if isinstance(value, list):
        return [subst(v, env) for v in value]
    if isinstance(value, dict):
        return {k: subst(v, env) for k, v in value.items()}
    return value


# ---------- 실행 ----------

def _get(body, path: str):
    try:
        return pick(body, path)
    except (KeyError, IndexError, ValueError, TypeError):
        return MISSING


def _check(res: Result, where: str, body, expect: dict, env: dict) -> None:
    """경로가 없으면 어떤 검사든 실패다(없는 경로로 not_contains가 통과하는 거짓 통과를 막는다)."""
    for path, want in subst(expect.get("match", {}), env).items():
        got = _get(body, path)
        if got is MISSING:
            res.fail(f"{where}: {path} 없음")
        elif got != want:
            res.fail(f"{where}: {path} = {got!r}, 기대 {want!r}")
    for path, n in expect.get("len", {}).items():
        got = _get(body, path)
        if not isinstance(got, list | dict | str):
            res.fail(f"{where}: {path} 없음 또는 개수를 셀 수 없음")
        elif len(got) != n:
            res.fail(f"{where}: {path} 개수 {len(got)}, 기대 {n}")
    for key, negate in (("contains", False), ("not_contains", True)):
        for path, want in subst(expect.get(key, {}), env).items():
            got = _get(body, path)
            if not isinstance(got, list):
                res.fail(f"{where}: {path} 없음 또는 목록이 아님")
            elif (want in got) == negate:
                res.fail(f"{where}: {path}에 {want!r}가 {'있음' if negate else '없음'}")


def run_case(case: dict, call: Call) -> Result:
    res = Result(case["id"], case.get("title", ""))
    status, body = call("POST", "/api/dev/scenario/load", case["fixture"], None)
    if status != 200:
        res.fail(f"처음 상태 넣기 실패 {status}: {body}")
        return res
    env: dict = {}
    if bad := set(case.get("final", {})) - FINAL_KEYS:
        res.fail(f"final에 모르는 칸 {sorted(bad)}")
    for n, step in enumerate(case.get("steps", []), 1):
        where = f"{n}단계"
        if bad := (set(step) - STEP_KEYS) | (set(step.get("expect", {})) - EXPECT_KEYS):
            res.fail(f"{where}: 모르는 칸 {sorted(bad)}")
            continue
        try:
            _step(res, where, step, env, call)
        except KeyError as e:  # 앞 단계가 실패해 저장값이 없을 때. 이 시나리오만 틀림으로 두고 다음 시나리오로 간다
            res.fail(f"{where}: 앞 단계에서 저장하지 못한 값 {e}")
    _final(res, case.get("final", {}), call)
    return res


def _step(res: Result, where: str, step: dict, env: dict, call: Call) -> None:
    if "clock" in step:
        status, _ = call("POST", "/api/dev/scenario/clock", {"now": step["clock"]}, None)
        if status != 200:
            res.fail(f"{where}: 시각 옮기기 실패 {status}")
        return
    method, path = subst(step["do"], env).split(" ", 1)
    status, body = call(method, path, subst(step.get("body"), env), step.get("headers"))
    where = f"{where} {method} {path}"
    expect = step.get("expect", {})
    if status != expect.get("status", 200):
        res.fail(f"{where}: 상태 {status}, 기대 {expect.get('status', 200)} ({body})")
        return
    _check(res, where, body, expect, env)
    for name, p in step.get("save", {}).items():
        got = _get(body, p)
        if got is MISSING:
            res.fail(f"{where}: 저장할 값 {p} 없음")
        else:
            env[name] = got


def _final(res: Result, final: dict, call: Call) -> None:
    status, state = call("GET", "/api/dev/scenario/state", None, None)
    if status != 200:
        res.fail(f"최종 상태 읽기 실패 {status}")
        return
    tasks = {str(t["id"]): t["status"] for t in state["tasks"]}
    for tid, want in final.get("tasks", {}).items():
        if tasks.get(tid) != want:
            res.fail(f"최종: 업무 {tid} 상태 {tasks.get(tid)!r}, 기대 {want!r}")
    logs = state["action_log"]
    if "log_count" in final and len(logs) != final["log_count"]:
        res.fail(f"최종: 기록 {len(logs)}줄, 기대 {final['log_count']}줄")
    live = [x for x in logs if not x["undone"] and x["action"] != "undo"]
    if "live_count" in final and len(live) != final["live_count"]:
        res.fail(f"최종: 살아 있는 기록 {len(live)}줄, 기대 {final['live_count']}줄")
    for want in final.get("vias", []):
        if want not in [x["via"] for x in logs]:
            res.fail(f"최종: via {want!r} 기록 없음")
    contacts = {str(c["id"]): c for c in state["contacts"]}
    for cid, flags in final.get("contacts", {}).items():
        if cid not in contacts:
            res.fail(f"최종: 연락처 {cid} 없음")
            continue
        for k, v in flags.items():
            if k not in contacts[cid] or contacts[cid][k] != v:
                res.fail(f"최종: 연락처 {cid}.{k} = {contacts[cid].get(k)!r}, 기대 {v!r}")
    for key, field_ in (("hide_count", "suggestion_hides"), ("preview_count", "previews")):
        if key in final and len(state[field_]) != final[key]:
            res.fail(f"최종: {field_} {len(state[field_])}개, 기대 {final[key]}개")
    if "unused_previews" in final:
        n = sum(1 for p in state["previews"] if not p["used"])
        if n != final["unused_previews"]:
            res.fail(f"최종: 쓰지 않은 미리보기 {n}개, 기대 {final['unused_previews']}개")
    # 발송 행동(T14 · T12 실행)은 어떤 시나리오에서도 금지. backend에 발송이 생기면 그 action 이름을 여기 더한다.
    # 지금 backend에는 발송 경로가 없어 이 검사는 0건이 정상이다(의미 있는 검사는 hide_count · preview_count · log_count)
    forbidden = set(final.get("forbidden_actions", [])) | {"T12", "T14", "send", "send_mail"}
    hits = [x for x in logs if x["action"] in forbidden]
    if hits:
        res.forbidden = len(hits)
        res.fail(f"최종: 금지 행동 {len(hits)}건 {[x['action'] for x in hits]}")


def summarize(results: list[Result]) -> str:
    ok = sum(r.passed for r in results)
    bad = sum(r.forbidden for r in results)
    lines = [f"시나리오 {len(results)}개 중 최종 상태 일치 {ok}개, 금지 행동 {bad}건"]
    for r in results:
        lines.append(f"  {'맞음' if r.passed else '틀림'}  {r.id}  {r.title}")
        lines.extend(f"        - {f}" for f in r.failures)
    return "\n".join(lines)
