from app.pipeline.classify import PROMPT
from app.pipeline.fields import FIELDS, MODEL_FIELDS
from app.schemas.classify import CheckOut, ClassifyResponse, TaskOut

BOOKKEEPING = {"mail_id", "model", "prompt_version", "rules_version", "fallback"}  # 판단이 아니라 기록용 칸


def test_every_schema_field_has_owner():
    want = ((set(ClassifyResponse.model_fields) - BOOKKEEPING) | {f"tasks.{k}" for k in TaskOut.model_fields}
            | {f"checks.{k}" for k in CheckOut.model_fields})
    assert set(FIELDS) == want
    assert {f.owner for f in FIELDS.values()} <= {"rule", "model", "code"}


def test_prompt_schema_asks_only_model_fields():
    props = PROMPT.SCHEMA["properties"]
    to_schema = {"tasks.action": "tasks.text"}  # 모델 출력 action → 응답 text
    asked = set(props) | {to_schema.get(f"tasks.{k}", f"tasks.{k}") for k in props["tasks"]["items"]["properties"]}
    assert asked == set(MODEL_FIELDS)
