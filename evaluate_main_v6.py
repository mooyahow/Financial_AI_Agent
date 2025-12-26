# evaluate_main.py

import json
import csv
import time
from pathlib import Path
from langchain_naver import ChatClovaX
from config import setup_api_key, API_KEY
from data_loader import load_data
from agent import create_financial_agent
from tools import fn_analyze_company_stability, adjust_date_to_business_day_kr


def load_json_auto_encoding(json_path: str):
    """자동 인코딩 감지하여 JSON 로드"""
    for enc in ["utf-8", "utf-8-sig", "cp949", "euc-kr"]:
        try:
            with open(json_path, "r", encoding=enc) as f:
                print(f"✅ JSON 로딩 성공: 인코딩 = {enc}")
                return json.load(f)
        except UnicodeDecodeError:
            continue
    raise ValueError("❌ JSON 인코딩을 인식할 수 없습니다. 파일을 UTF-8로 저장해주세요.")


def evaluate(json_path: str, output_csv_path: str):
    setup_api_key()

    # LLM 초기화
    llm = ChatClovaX(
        model="HCX-005",
        api_key=API_KEY,
        base_url="https://clovastudio.stream.ntruss.com/v1/openai"
    )

    # 데이터 로딩
    df_stock, df_info = load_data()
    if df_stock is None:
        print("📛 주식 데이터 로드 실패")
        return

    # 에이전트 초기화
    agent_executor = create_financial_agent(llm=llm, df_stock=df_stock, df_info=df_info)
    agent = agent_executor.agent

    # JSON 파일 로딩
    data = load_json_auto_encoding(json_path)
    results = []

    for item in data:
        message = item["input_data"]["message"]
        expected_output = item.get("expected_output", "").strip()
        print("\n🟢 질문:", message)

        try:
            start_time = time.time()
            q_processed = adjust_date_to_business_day_kr(message)

            # 계획 생성
            agent_plan = agent.plan(intermediate_steps=[], input=q_processed)

            # 특정 도구 직접 호출
            if isinstance(agent_plan, list) and agent_plan and agent_plan[0].tool == "analyze_company_stability":
                tool_input = agent_plan[0].tool_input
                final_report = fn_analyze_company_stability(
                    llm=llm,
                    df_info=df_info,
                    stock_name=tool_input["stock_name"]
                )
                final_output = f"""{final_report.get("llm_analysis", "")}  
--- 분석 지표 ---  
1. 기업 재무 지표: {final_report.get("metrics_str", "")}  
2. 주가 및 거래량 추세 분석: {final_report.get("historical_str", "")}  
3. 재무제표 핵심 항목 추이: {final_report.get("financial_trend_str", "")}  
---"""
            else:
                response = agent_executor.invoke({"input": q_processed})
                final_output = response.get("output", "").strip()

            elapsed_time = round(time.time() - start_time, 2)

            # 평가 기준 (단순 포함 여부)
            if expected_output and expected_output in final_output:
                eval_result = "✅ 정답"
            elif expected_output == "":
                eval_result = "⚪ 기준 없음"
            else:
                eval_result = "❌ 오답"

            results.append({
                "message": message,
                "expected_output": expected_output,
                "final_output": final_output,
                "eval": eval_result,
                "elapsed_time": elapsed_time
            })

        except Exception as e:
            elapsed_time = round(time.time() - start_time, 2)
            results.append({
                "message": message,
                "expected_output": expected_output,
                "final_output": f"에러 발생: {str(e)}",
                "eval": "❌ 에러",
                "elapsed_time": elapsed_time
            })

    # CSV 저장
    with open(output_csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["message", "expected_output", "final_output", "eval", "elapsed_time"]
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\n✅ 평가 결과 저장 완료 → {output_csv_path}")


# 실행
if __name__ == "__main__":
    evaluate(
        json_path=r"C:\Users\USER\Desktop\mirae\simple_queries.json",
        output_csv_path=r"C:\Users\USER\Desktop\mirae\evaluation_result_simple.csv"
    )

    evaluate(
        json_path=r"C:\Users\USER\Desktop\mirae\conditional_queries.json",
        output_csv_path=r"C:\Users\USER\Desktop\mirae\evaluation_result_conditional.csv"
    )

    evaluate(
        json_path=r"C:\Users\USER\Desktop\mirae\signal_queries.json",
        output_csv_path=r"C:\Users\USER\Desktop\mirae\evaluation_result_signal.csv"
    )
