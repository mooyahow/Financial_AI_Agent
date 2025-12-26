"""
로컬에서 API 서버 없이 바로 질문을 실행하기 위한 엔트리포인트

사용 예시:
    python python_exe.py --question "2024-10-14에 거래량이 전날대비 200% 이상 증가한 종목을 모두 보여줘"
또는 실행 후 프롬프트에 질문을 입력하세요.
"""

import argparse

from main_logic import initialize_agent_context, process_question


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="로컬 LLM 금융 에이전트 실행기")
    parser.add_argument(
        "--question",
        "-q",
        type=str,
        help="바로 실행할 질문. 생략하면 인터랙티브 모드가 시작됩니다.",
    )
    return parser.parse_args()


def run_interactive(context):
    print("종료하려면 빈 줄을 입력하세요.")
    while True:
        question = input("\n질문> ").strip()
        if not question:
            print("종료합니다.")
            break
        result = process_question(context, question)
        print(result)


def main():
    args = parse_args()
    context = initialize_agent_context()
    if context is None:
        print("에이전트 초기화에 실패했습니다. 환경 변수를 확인하세요.")
        return

    if args.question:
        print(process_question(context, args.question))
    else:
        run_interactive(context)


if __name__ == "__main__":
    main()