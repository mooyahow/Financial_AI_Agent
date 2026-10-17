# Financial AI Agent

고성능 주가 데이터(DuckDB + Parquet)와 LangChain ToolCallingAgent를 결합한 금융 분석 에이전트입니다.  
FastAPI 기반 HTTP API와 로컬 CLI(`python_exe.py`) 두 가지 방식으로 질문에 답변합니다.
(대회 규정으로 원본 코드 비공개, 동일 아키텍처를 재현한 예제)

## 주요 기능
- **LangChain ToolCallingAgent + AgentExecutor**: 질문 → 계획 → 도구 실행 → 응답 흐름 유지
- **20개+ 금융 분석 도구**: RSI, 볼린저 밴드, 거래량 급증, 등락률/변동률, 이동평균 비교 등 (`tools.py`)
- **DuckDB + Parquet**: 대용량 주가 데이터 고속 조회
- **yfinance 연동**: 실시간 시가총액 및 최신 시세 보완
- **Redis 캐시(옵션)**: 질문-응답 캐시로 동일 질의 가속
- **FastAPI 엔드포인트**: `GET /query`, `GET /status`
- **로컬 CLI 실행**: API 없이 `python_exe.py`로 질의 응답
- **크론 기반 업데이트 스크립트 지원**: DuckDB 최신화 + Parquet export (예: `update_stocks_db_m.py`, `export_to_parquet.py`)


## 폴더/파일 구조
| 파일 | 설명 |
| --- | --- |
| `main_logic.py` | 질의 → 계획 → 실행 → 응답의 공용 로직 |
| `agent.py` | LangChain ToolCallingAgent + AgentExecutor 생성 |
| `tools.py` | 20여 개 금융 분석 도구, 공휴일/영업일 보정 포함 |
| `schemas.py` | LangChain tool 인자 검증용 `pydantic` 모델 |
| `data_loader.py` | DuckDB에서 시세 데이터 로드 및 전처리 |
| `api.py` | FastAPI HTTP 서버 (`/query`, `/status`) |
| `python_exe.py` | 로컬 CLI 실행 스크립트 (API 없이 동작) |
| `config.py` | 환경 변수 기반 설정 로더 및 프롬프트 템플릿 |
| `requirements.txt` | 의존성 목록 |
| `Dockerfile`, `docker-compose.yml` | 컨테이너 빌드·실행 설정 |
| `.env.example` | 필요한 환경 변수 예시 |

## 사전 준비
1. Python 3.10+
2. DuckDB 파일 준비 (`DB_PATH` 환경 변수로 경로 지정)
3. OpenAI 호환 LLM 엔드포인트 정보 (Base URL, API Key, 모델명)
4. 선택: Redis 서버 (`REDIS_URL`)

## 환경 변수 (.env 예시)
`.env.example`을 참고해 `.env`를 작성하세요.

```
API_KEY=your_api_key            # HTTP API 인증용 (비워두면 인증 없이 동작)
LLM_API_KEY=your_llm_api_key    # LLM 키
LLM_MODEL=general-llm           # 사용 모델명
LLM_BASE_URL=http://localhost:1234/v1  #  Base URL
DB_PATH=data/all_stocks.duckdb  # DuckDB 파일 경로
REDIS_URL=redis://localhost:1234/0
API_KEY_HEADER=Authorization
```

## 설치
```bash
pip install -r requirements.txt
```

## 로컬 CLI 실행 (API 없이)
```bash
python python_exe.py --question "2024-10-14에 거래량이 전날대비 200% 이상 증가한 종목"
# 또는 실행 후 프롬프트에서 질문 입력
python python_exe.py
# 한글 실행 파일(alias)
python run_.py
```

## FastAPI 서버 실행
```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

### 엔드포인트
| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/status` | 서버 상태 확인 |
| GET | `/query` | 질문 처리 |
**Base URL**: `http://localhost:8000`  
**인증**: `Authorization: Bearer {YOUR_API_KEY}` (환경 변수 `API_KEY`와 일치해야 함)

### 요청 파라미터
| 이름 | 위치 | 필수 | 설명 |
| --- | --- | --- | --- |
| `question` | query | ✅ | 자연어 질문 내용 |

### curl 예시

```bash
curl -G "http://localhost:8000/query" \
  -H "Authorization: Bearer {YOUR_API_KEY}" \
  --data-urlencode "question=2024년 11월 22일에 KOSDAQ 시장에서 등락률이 +5% 이상인 종목은?"
```


## Docker로 실행
```bash
cp .env.example .env            # 값 채우기
mkdir -p data                   # DuckDB 파일을 data/ 아래에 둠
docker compose up --build -d
curl http://localhost:8000/status
```
- 데이터(DuckDB/Parquet)는 이미지에 넣지 않고 `./data`를 읽기 전용 볼륨으로 마운트
- `.env`는 `env_file`로 주입, `.dockerignore`로 이미지에서 제외
- `/status` 기반 HEALTHCHECK 포함

## 데이터 파이프라인 및 업데이트
- **DuckDB → Parquet**: Parquet로 export하여 병렬 읽기 최적화 (예: `export_to_parquet.py`)
- **일별 업데이트**: 크론탭 등으로 `update_stocks_db_m.py` 실행 후 Parquet 덮어쓰기
- **조회 최적화**: `data_loader.py`가 DuckDB를 읽어 Pandas DataFrame으로 전처리


## 대회 이후 보완한 부분
대회 기간에는 평가셋 점수와 크레딧 한도 안에서 동작시키는 데 집중했기 때문에, 서버에 코드를 올리고 `uvicorn`을 직접 띄우는 수준이었습니다. 대회가 끝난 뒤 당시 부족했다고 느낀 부분을 아래와 같이 보완했습니다.

- **컨테이너화**: `Dockerfile`·`docker-compose.yml` 추가. 데이터와 비밀값을 이미지에서 분리하고 헬스체크를 넣어 같은 환경에서 재현·배포 가능하도록 정리
- **벤더 비종속 구성**: 대회에서는 특정 클라우드 LLM에 고정돼 있던 호출부를 OpenAI 호환 엔드포인트 설정(`LLM_BASE_URL`, `LLM_MODEL`)으로 일반화
- **인증 정리**: HTTP API에 Bearer 토큰 인증을 넣고 미설정 시 명시적으로 503을 반환하도록 수정
- **로컬 CLI**: 서버 없이 동일한 질의 흐름을 실행할 수 있는 `python_exe.py` 추가 (실패 분석 반복에 유용)

아직 남아 있는 한계: 싱글턴 구조라 대화 맥락을 유지하지 못하고, LLM 선정은 샘플 질의 기반의 정성 비교에 그쳤습니다. 실서비스로 가려면 멀티턴 설계와 모델별 정량 평가 체계가 필요합니다.

## 설계 노트
- **LLM 교체 용이성**: `config.py`와 환경 변수로 LLM 엔드포인트/모델을 설정하며, 특정 벤더명/키 포맷을 노출하지 않습니다.
- **인증 일반화**: HTTP 인증은 Bearer 토큰(`API_KEY`)으로 단순화되어 있으며, 필요 시 미설정으로 공개 테스트 가능.
- **캐시 옵션**: `REDIS_URL`이 설정된 경우 Redis 기반 캐시 모듈을 연동하도록 확장할 수 있습니다.
- **오프라인 친화성**: API 서버 없이도 `python_exe.py`로 동일한 질의 흐름을 실행할 수 있습니다.

## 주의 사항
 실제 IP, 도메인, 회사 고유 명칭, 특정 키 포맷은 코드/문서 어디에도 포함하지 않습니다.
- `.env`, DuckDB 파일, Parquet 파일은 `.gitignore`에 포함되어 있어 공개 저장소에 노출되지 않습니다.


