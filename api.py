from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from main_logic import AgentContext, initialize_agent_context, process_question
from contextlib import asynccontextmanager


agent_context: AgentContext | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_context
    agent_context = initialize_agent_context()
    yield  


app = FastAPI(title="Financial Agent API", version="1.0.0", lifespan=lifespan)


def verify_api_key(
    authorization: str | None = Header(default=None),
) -> None:
    """
    Bearer 인증 강제.
    - 서버 설정(API_KEY)이 비어 있으면 동작X
    - 헤더 누락/형식 오류/불일치 시 401
    """
    if agent_context is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="에이전트 초기화에 실패했습니다. 서버 로그를 확인하세요.",
        )

    expected = (agent_context.settings.api_key or "").strip()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버 API_KEY가 설정되지 않았습니다. 환경변수/설정을 확인하세요.",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 필요합니다. (Authorization: Bearer <API_KEY>)",
        )

    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API 키입니다.",
        )


@app.get("/status")
async def status_check():
    return {"status": "ok"}


@app.get("/query")
async def query(
    question: str = Query(..., description="자연어 질문"),
    _: None = Depends(verify_api_key),
):
    result = process_question(agent_context, question)
    return {"answer": result}