from dataclasses import dataclass

import pandas as pd
from langchain.agents import AgentExecutor
from langchain_core.agents import AgentFinish
from langchain_core.language_models import BaseLanguageModel
from langchain_openai import ChatOpenAI

# OpenAI
#from langchain_openai import ChatOpenAI
# Naver
#from langchain_naver import ChatClovaX
# Anthropic
#from langchain_anthropic import ChatAnthropic
# Google
#from langchain_google_genai import ChatGoogleGenerativeAI




from agent import create_financial_agent
from config import Settings, load_settings
from data_loader import load_data
from tools import adjust_date_to_business_day_kr, adjust_invoked_date, fn_analyze_company_stability


@dataclass
class AgentContext:
    settings: Settings
    llm: BaseLanguageModel
    df_stock: pd.DataFrame
    df_info: pd.DataFrame
    agent_executor: AgentExecutor


def build_llm(settings: Settings) -> BaseLanguageModel:
    """
    #LLM 엔드포인트 선택하여 LangChain LLM 인스턴스 생성
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_tokens=4096,
    )


def initialize_agent_context() -> Optional[AgentContext]:
    """
    설정을 로드하고, 데이터 및 에이전트 준비
    데이터나 환경 설정이 없는 경우 None을 반환
    """
    settings = load_settings()
    df_stock, df_info = load_data(settings.db_path)
    if df_stock is None or df_info is None:
        return None

    llm = build_llm(settings)
    agent_executor = create_financial_agent(llm=llm, df_stock=df_stock, df_info=df_info)

    return AgentContext(
        settings=settings,
        llm=llm,
        df_stock=df_stock,
        df_info=df_info,
        agent_executor=agent_executor,
    )


def _render_company_report(result: dict) -> str:
    llm_analysis = result.get("llm_analysis", "")
    metrics = result.get("metrics_str", "")
    historical = result.get("historical_str", "")
    trends = result.get("financial_trend_str", "")

    return f"""{llm_analysis}

---
분석 지표
### 1. 기업 재무 지표:
{metrics}

### 2. 주가 및 거래량 추세 분석:
{historical}

### 3. 재무제표 핵심 항목 추이:
{trends}
---
"""


def process_question(context: AgentContext, question: str) -> str:
    """
    질의 → 계획 → 실행 → 응답 흐름을 수행하고 문자열 결과를 반환
    """
    if context is None:
        return "에이전트 컨텍스트를 초기화하지 못했습니다. 환경 변수를 확인하세요."

    # 전처리: 공휴일/주말 응답
    q_processed = adjust_date_to_business_day_kr(question)
    if q_processed.startswith("'"):
        return q_processed

    agent = context.agent_executor.agent
    agent_plan = agent.plan(intermediate_steps=[], input=q_processed)

    # analyze_company_stability는 직접 실행하여 2차 요약을 방지
    if isinstance(agent_plan, list) and agent_plan and agent_plan[0].tool == 'analyze_company_stability':
        tool_input = agent_plan[0].tool_input
        final_report = fn_analyze_company_stability(
            llm=context.llm,
            df_info=context.df_info,
            stock_name=tool_input['stock_name'],
        )
        return _render_company_report(final_report)

    response = context.agent_executor.invoke({"input": q_processed})

    # LLM invoking 후 단일 date 인자 영업일 보정
    args = None
    if hasattr(response, 'args'):
        args = response.args
    elif isinstance(response, dict) and 'args' in response:
        args = response['args']

    if args and 'date' in args and 'start_date' not in args and 'end_date' not in args:
        args['date'] = adjust_invoked_date(args['date'])

    if isinstance(response, AgentFinish):
        return response.return_values.get("output", "결과를 출력할 수 없습니다.")

    if isinstance(response, dict):
        return response.get("output", "결과를 출력할 수 없습니다.")

    return str(response)