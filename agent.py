import pytz
from datetime import datetime

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.language_models import BaseLanguageModel

from config import AGENT_PROMPT_TEMPLATE
from tools import get_tools


def create_financial_agent(llm: BaseLanguageMode, df_stock, df_info) -> AgentExecutor:
    """
    llm과 금융 분석 도구들을 사용하여 'Tool-Calling' 에이전트와 실행기를 생성합니다

    Args:
        llm: 사용할 언어 모델 
        df_stock (pd.DataFrame): 종목별 주가 관련 시계열 데이터 프레임

    Returns:
        AgentExecutor: 즉시 실행 가능한 에이전트 실행기
    """
    # 1. 도구 목록 생성
    tools = get_tools(llm, df_stock, df_info)

    # 2. 현재 날짜(Asia/Seoul) 삽입
    seoul_tz = pytz.timezone('Asia/Seoul')
    current_date = datetime.now(seoul_tz).strftime('%Y-%m-%d')

    # 3. 스키마 정보 생성
    schema_info = ", ".join(df_stock.columns.tolist())
    # 3. 시스템 프롬프트에 날짜 주입
    prompt_with_date = AGENT_PROMPT_TEMPLATE.format(current_date=current_date, schema_info=schema_info)

    # 4. ChatPromptTemplate 구성
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_with_date),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # 5. Tool-Calling 에이전트 생성
    agent = create_tool_calling_agent(llm, tools, prompt)

    # 6. AgentExecutor 생성
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=5,
    )

    return agent_executor

