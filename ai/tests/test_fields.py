from app.pipeline.classify import PROMPT
from app.pipeline.fields import FIELDS, MODEL_FIELDS
from app.schemas.classify import CheckOut, ClassifyResponse, TaskOut

BOOKKEEPING = {"mail_id", "model", "prompt_version", "rules_version", "fallback"}  # 판단이 아니라 기록용 칸
MODEL_ONLY = {"mail_type"}  # 모델이 내지만 응답에는 action_types로 나가는 칸


def test_every_schema_field_has_owner():
    want = ((set(ClassifyResponse.model_fields) - BOOKKEEPING) | {f"tasks.{k}" for k in TaskOut.model_fields}
            | {f"checks.{k}" for k in CheckOut.model_fields})
    assert set(FIELDS) - MODEL_ONLY == want
    assert {f.owner for f in FIELDS.values()} <= {"rule", "model", "code"}


def test_prompt_schema_asks_only_model_fields():
    props = PROMPT.SCHEMA["properties"]
    to_schema = {"tasks.action": "tasks.text", "tasks.to": "tasks.deliver_to", "follow_up": "is_follow_up"}  # 모델 출력 이름 → 응답 이름
    asked = {to_schema.get(k, k) for k in props} | {to_schema.get(f"tasks.{k}", f"tasks.{k}") for k in props["tasks"]["items"]["properties"]}
    assert asked == set(MODEL_FIELDS)


def test_type_lists_match_schema():
    assert PROMPT.TASK_TYPES == list(TaskOut.model_fields["type"].annotation.__args__)
