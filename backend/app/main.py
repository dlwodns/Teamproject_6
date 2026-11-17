"""backend 진입점. 실행: `uvicorn app.main:app --port 8000` (backend/ 폴더에서)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import mails  # 메일 한 통 보기(#55 리뷰). 다른 PR들이 아래 import 줄 사이에 한 줄씩 더하므로, 겹치지 않게 맨 위에 둔다

from app.api import actions, health
from app.core import clock, request_id
from app.core.config import ensure_settings, get_settings
from app.core.db import init_db
from app.api import agent_command  # BE-11. 다른 PR이 위 import 줄을 고쳐도 겹치지 않게 따로 둔다
from app.api import agent, classify, dev_scenario  # PL-16 라우터. 위 import 줄을 다른 PR이 고쳐도 겹치지 않게 따로 둔다
from app.api import calendar  # BE-15 캘린더. 다른 PR과 import 줄이 겹치지 않게 따로 둔다
from app.jobs import worker
from app.api import dashboard  # BE-3. 다른 PR이 위 import 줄을 고쳐도 겹치지 않게 따로 둔다
from app.api import reminders  # BE-12 리마인더 · 알림 센터 · 브리핑. 다른 PR과 import 줄이 겹치지 않게 따로 둔다
from app.api import settings as settings_api  # 설정(하루 요약 · 회고 시각, 11-14). 다른 PR과 import 줄이 겹치지 않게 따로 둔다
from app.jobs import scheduler  # BE-12 리마인더 스케줄러


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_settings()  # 설정이 틀리면 뜨지 않는다(INF-4)
    clock.init_clock(get_settings().clock_start)  # 검사를 통과한 CLOCK_START로 offset을 한 번 정한다(worker마다 따로)
    init_db()  # 테이블이 없으면 만든다. 있는 테이블 · 데이터는 건드리지 않는다
    worker.start()  # CLASSIFY_WORKER=1일 때만(분류 작업자, PL-16)
    scheduler.start()  # REMINDER_SCHEDULER=1일 때만(리마인더 엔진 1분 틱, BE-12)
    yield
    scheduler.stop()
    worker.stop()


request_id.setup_logging()
app = FastAPI(title="ax-backend", version="0.1.0", lifespan=lifespan)
request_id.install(app)  # X-Request-ID · 접근 로그(INF-12)
from app.api import demo  # noqa: E402  BE-14. 다른 PR이 고치는 import 블록 · 라우터 끝 줄과 겹치지 않게 여기 둔다
demo.install(app)  # DEMO_TOOLS=true일 때만 /api/dev/clock(시간 이동). APP_MODE와 관계없다(BE-D23)
app.include_router(health.router)
app.include_router(mails.router)  # GET /api/mails/{id}(#55 리뷰). 다른 PR이 끝에 더하는 줄과 겹치지 않게 위에 둔다
from app.api import reply  # noqa: E402  BE-5 답장 보내기. 다른 PR의 import 블록 · 라우터 끝 줄과 겹치지 않게 여기 둔다
app.include_router(reply.router)  # POST /api/mails/{id}/reply
app.include_router(actions.router)
from app.api import awaiting  # noqa: E402  BE-13 응답 대기. 다른 PR의 import 블록 · 라우터 끝 줄과 겹치지 않게 여기 둔다
app.include_router(awaiting.router)  # GET /api/awaiting
from app.api import polish  # noqa: E402  답장 AI 다듬기. 다른 PR의 import 블록 · 라우터 끝 줄과 겹치지 않게 여기 둔다
app.include_router(polish.router)  # POST /api/mails/{id}/polish
app.include_router(agent_command.router)  # POST /api/agent/command(BE-11)
app.include_router(agent.router)  # 제안 카드 · 기록 · 에이전트가 아는 것(D50 · PL-16)
app.include_router(calendar.router)  # 캘린더 기한 · 다시 알림 · 회의 · 일정(BE-15 · D50)
app.include_router(classify.router)  # 분류 대기 수 · 개발용 분류 실행(PL-16)
app.include_router(dev_scenario.router)  # 운영에서는 404(시나리오 평가 전용)
app.include_router(dashboard.router)  # GET /api/dashboard 원자료(BE-3 · BE-D22)
app.include_router(reminders.router)  # 리마인더 · 알림 센터 · 브리핑 · 개발용 강제 실행(BE-12)
app.include_router(settings_api.router)  # GET · PATCH /api/settings(하루 요약 · 회고 시각, 11-14)
