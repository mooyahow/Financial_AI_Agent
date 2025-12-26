from main_logic import initialize_agent_context, process_question

def main():
    """
    CLI에서 샘플 질문을 실행하는 간단한 데모 엔트리포인트
    """
    context = initialize_agent_context()
    if context is None:
        print("에이전트 초기화에 실패했습니다. 환경 변수를 확인하세요.")
        return

    questions = [
        "2024-10-14에 거래량이 전날대비 200% 이상 증가한 종목을 모두 보여줘",
    ]

    for q in questions:
        print("\n" + "=" * 60)
        print(f"질문: {q}")
        print("=" * 60)
        try:
  
            result = process_question(context, q)
            print(result)
        except Exception as e:
            print(f"에러 발생: {e}")


if __name__ == "__main__":
    main()
