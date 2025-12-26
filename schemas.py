from pydantic import BaseModel, Field
from typing import Literal, Optional, Union, List

# Pydantic models for tool arguments

class PriceQueryArgs(BaseModel):
    date: str = Field(..., description="조회할 기준 날짜 (YYYY-MM-DD 형식)")
    stock_name: Optional[str] = Field(None, description="조회할 종목의 이름. 예: '삼성전자'")
    column_name: str = Field(None, description="조회할 컬럼명 (예: 'closing_price', 'opening_price', 'high_price', 'low_price')")

class StockFilterArgs(BaseModel):
    date: str = Field(..., description="조회할 기준 날짜 (YYYY-MM-DD 형식)")
    stock_name: Optional[str] = Field(None, description="조회할 종목의 이름. 여러 종목은 쉼표(,)로 구분된 문자열로 전달. 예: '삼성전자' 또는 '삼성전자,LG화학'")
    market: Optional[str] = Field(None, description="조회할 시장 ('KOSPI' 또는 'KOSDAQ')")
    column_name: Optional[str] = Field(None, description="필터링할 시세 컬럼명. 예: 'closing_price', 'opening price','trading_volume'")
    operator: Optional[str] = Field(None, description="비교 연산자. 예: '>=', '<=', '==', '>', '<'")
    threshold: Optional[Union[float, List[float]]] = Field(
        None, 
        description="필터링에 사용할 임계값. **'A 이상 B 이하'와 같은 범위 조회 시에는 반드시 [A, B] 형식의 리스트를 사용하세요.** 단일 값(예: 50000) 조회 시에는 `operator`를 함께 사용합니다."
    )
    n: Optional[int] = Field(None, description="조회할 상위/하위 결과의 개수")
    sort_by: str = Field(None, description="결과를 정렬할 기준 컬럼. 예: 'closing_price', 'price_change_rate'")
    ascending: bool = Field(False, description="정렬 순서. 오름차순(True) 또는 내림차순(False)")


class RsiArgs(BaseModel):
    """
    RSI 조회 도구 인자 스키마입니다.
    """
    date: str = Field(..., description="분석 기준일 (YYYY-MM-DD)")
    period: int = Field(14, description="RSI 계산 기간 (기본값: 14)")
    operator: str = Field(..., description="비교 연산자. 예: '>=', '<='")
    threshold: float = Field(..., description="RSI 임계값. 예: 70")
    market: Optional[str] = Field(None, description="필터링할 시장 ('KOSPI' 또는 'KOSDAQ')")
    n: Optional[int] = Field(None, description="조회할 상위/하위 결과의 개수")
    ascending: bool = Field(False, description="정렬 순서. 오름차순(True) 또는 내림차순(False). 기본값은 내림차순입니다.")

class RateFilterArgs(BaseModel):
    date: str = Field(..., description="분석 기준일 (YYYY-MM-DD). 이전 거래일 자동 계산")
    column_name: str = Field(..., description="전일 대비 변화율을 비교할 컬럼명. 예: 'closing_price', 'trading_volume'")
    operator: str = Field(..., description="비교 연산자. 예: '>=', '<=', '==', '>', '<'")
    threshold_percent: float = Field(..., description="변화율 임계값(%). 예: 300, -5")
    market: Optional[str] = Field(None, description="필터링할 시장 ('KOSPI' 또는 'KOSDAQ')")
    sort_by: Optional[str] = Field(None, description="정렬할 컬럼명. 지정하지 않으면 기본값(변동률)으로 정렬됩니다.")
    ascending: bool = Field(False, description="정렬 순서: 오름차순(True) 또는 내림차순(False). 기본값은 내림차순입니다.")

class CombinedFilterArgs(BaseModel):
    date: str = Field(..., description="조회할 기준 날짜 (YYYY-MM-DD 형식)")
    rate_threshold: Optional[float] = Field(None, description="변화율 임계값(%). 예: 5, -10")
    volume_ratio: Optional[float] = Field(None, description="거래량 변화율 배수. 예: 3.0는 300%")
    market: Optional[str] = Field(None, description="조회할 시장 ('KOSPI' 또는 'KOSDAQ')")

class CrossDetectArgs(BaseModel):
    stock_name: Optional[str] = Field(None, description="특정 종목명. 전체 시장 검색 시 비워둠")
    start_date: str = Field(..., description="크로스 이벤트 검색 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="크로스 이벤트 검색 종료일 (YYYY-MM-DD)")
    event_type: Union[str, List[str]] = Field(..., description="감지할 이벤트 유형. 예: '골든 크로스', '데드 크로스'")
    short_window: int = Field(5, description="단기 이동평균 기간 (기본값: 5)")
    long_window: int = Field(20, description="장기 이동평균 기간 (기본값: 20)")

class CrossCountArgs(BaseModel):
    """
    크로스 발생 횟수 조회 도구의 인자 스키마입니다.
    """
    stock_name: Optional[str] = Field(None, description="특정 종목명. 전체 시장 검색 시 비워둠")
    start_date: str = Field(..., description="크로스 이벤트 검색 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="크로스 이벤트 검색 종료일 (YYYY-MM-DD)")
    event_type: Union[str, List[str]] = Field(..., description="감지할 이벤트 유형. 예: '골든 크로스', '데드 크로스'")
    short_window: int = Field(5, description="단기 이동평균 기간 (기본값: 5)")
    long_window: int = Field(20, description="장기 이동평균 기간 (기본값: 20)")
    column_name: str = Field('closing_price', description="이동평균 계산 대상 컬럼명 (예: 'closing_price', 'trading_volume')")

class BollingerTouchArgs(BaseModel):
    date: str = Field(..., description="볼린저 밴드 터치 분석 기준일 (YYYY-MM-DD)")
    window: int = Field(20, description="볼린저 밴드 계산 이동평균 기간")
    dev: float = Field(2.0, description="표준편차 배수")
    band: Literal['upper', 'lower'] = Field(..., description="터치할 밴드 방향 ('upper' 또는 'lower')")

class MovingAverageArgs(BaseModel):
    date: str = Field(..., description="이동평균 계산 기준일 (YYYY-MM-DD)")
    window: int = Field(..., description="이동평균 산출 기간(일)")
    column_name: str = Field('closing_price', description="이동평균 계산 대상 컬럼명 (예: 'closing_price', 'close' alias 지원)")

class TopVolumeArgs(BaseModel):
    start_date: str = Field(..., description="누적 거래량 조회 시작일 (YYYY-MM-DD)")
    end_date: str = Field(..., description="누적 거래량 조회 종료일 (YYYY-MM-DD)")
    n: int = Field(..., description="조회할 상위 종목 개수")
    market: Optional[str] = Field(None, description="시장 구분 ('KOSPI'/'KOSDAQ'), 미지정시 전체")

class FindStocksByMaConditionArgs(BaseModel):
    date: str = Field(..., description="분석 기준일 (YYYY-MM-DD)")
    ma_window: int = Field(..., description="이동평균 기간(일)")
    operator: str = Field(..., description="비교 연산자. 예: '>=', '<='")
    threshold_percent: float = Field(..., description="변화율 임계값(%)")
    column_name: str = Field('closing_price', description="비교 대상 컬럼명 (예: 'closing_price', 'trading_volume')")

class MarketAverageArgs(BaseModel):
    """
    시장 전체 혹은 개별 시장의 평균을 계산하는 도구 인자 스키마입니다.
    - date: 집계 기준 날짜 (YYYY-MM-DD)
    - market: Optional. 'KOSPI' 또는 'KOSDAQ'. 미지정 시 전체 시장 평균.
    - stock_name: Optional. 종목명을 주면 해당 종목이 속한 시장만 평균을 계산합니다.
    - column_name: 평균을 계산할 컬럼명 (예: 'price_change_rate', 'trading_volume').
    """
    date: str = Field(..., description="집계 기준 날짜 (YYYY-MM-DD)")
    market: Optional[str] = Field(None, description="평균을 계산할 시장 ('KOSPI' 또는 'KOSDAQ'), 미지정 시 전체 시장")
    stock_name: Optional[str] = Field(None, description="종목명을 주면 해당 종목이 속한 시장만 평균 계산")
    column_name: str = Field("price_change_rate", description="평균을 계산할 컬럼명 (예: 'price_change_rate', 'trading_volume')")


class VolumeRankArgs(BaseModel):
    """
    특정 날짜·종목의 컬럼 순위를 반환하는 도구 인자 스키마입니다.
    - date: 조회 기준 날짜 (YYYY-MM-DD)
    - stock_name: 순위를 알고 싶은 종목의 이름
    - column_name: 기준으로 순위를 매길 컬럼명 (예: 'trading_volume', 'closing_price')
    - market: Optional. 'KOSPI' 또는 'KOSDAQ'. 미지정 시 전체 시장 사용
    """
    date: str = Field(..., description="조회 기준 날짜 (YYYY-MM-DD)")
    stock_name: str = Field(..., description="순위를 알고 싶은 종목의 이름")
    column_name: str = Field(..., description="기준으로 순위를 매길 컬럼명 (예: 'trading_volume')")
    market: Optional[str] = Field(None, description="시장 구분 ('KOSPI' 또는 'KOSDAQ'), 미지정 시 전체 시장 사용")

class MarketPercentageArgs(BaseModel):
    """
    특정 날짜·종목의 지정 컬럼 값이
    해당 시장 전체 합계에서 차지하는 백분율을 계산하는 인자 스키마입니다.
    - date: 조회 기준 날짜 (YYYY-MM-DD)
    - stock_name: 비율을 알고 싶은 종목 이름
    - column_name: 기준으로 사용할 컬럼명 (예: 'trading_volume', 'trading_value')
    - market: Optional. 'KOSPI' 또는 'KOSDAQ'. 미지정 시 stock_name이 속한 시장 사용
    """
    date: str = Field(..., description="조회 기준 날짜 (YYYY-MM-DD)")
    stock_name: str = Field(..., description="비율을 알고 싶은 종목의 이름")
    column_name: str = Field(..., description="비율 계산에 사용할 컬럼명 (예: 'trading_volume')")
    market: Optional[str] = Field(
        None,
        description="시장 구분 ('KOSPI' 또는 'KOSDAQ'), 미지정 시 stock_name이 속한 시장 사용"
    )

class SimulateInvestmentArgs(BaseModel):
    stock_name: str = Field(..., description="조회할 종목의 이름")
    buy_date: str = Field(..., description="가상의 매수일자. 'YYYY-MM-DD' 형식 또는 '4월' 같이 모호한 날짜에는 적당한 'YYYY-MM-DD' 형식으로 변환하고 또는 '6개월 전', '작년 이맘때'처럼 상대적 표현일 시 이를 계산하여 'YYYY-MM-DD' 형식으로 변환하세요.")
    quantity: int = Field(10, description="매수 수량 (기본값: 10)")
    market: Optional[str] = Field(None, description="시장 구분 (예: KOSPI, KOSDAQ)")

class MarketIndexInfoArgs(BaseModel):
    date: str = Field(..., description="조회할 날짜 (예: '2025-05-06')")
    mode: str = Field(
        default="value",
        description=(
            "지수 조회 모드. 다음 중 하나여야 합니다:\n"
            "- 'value': KOSPI와 KOSDAQ 지수 값을 모두 반환\n"
            "- 'compare_value': KOSPI vs KOSDAQ 중 더 높은 지수를 비교해 반환\n"
            "- 'compare_change': 전일 대비 상승률을 비교해 더 높은 지수를 반환"
        )
    )
    
class CompanyAnalysisArgs(BaseModel):
    """
    기업 안정성 분석 도구의 인자 스키마입니다.
    - stock_name: 분석할 기업의 이름
    - ticker: (Optional) 분석할 기업의 티커. stock_name이 모호할 경우 사용
    """
    stock_name: str = Field(..., description="분석할 기업의 이름")
    ticker: Optional[str] = Field(None, description="분석할 기업의 티커. stock_name이 모호할 경우 사용")

class TotalMarketValueArgs(BaseModel):
    """
    특정 날짜의 전체 또는 개별 시장의 총 거래대금을 계산하는 도구 인자 스키마입니다.
    """
    date: str = Field(..., description="조회할 기준 날짜 (YYYY-MM-DD 형식)")
    market: Optional[str] = Field(None, description="조회할 시장 ('KOSPI' 또는 'KOSDAQ'), 미지정시 전체 시장")

class YfMarketCapArgs(BaseModel):
    """
    yfinance를 통해 현재 시점의 시가총액을 조회하는 도구의 인자 스키마입니다.
    """
    stock_name: str = Field(..., description="시가총액을 조회할 종목의 이름. 여러 종목은 쉼표(,)로 구분. 예: '삼성전자' 또는 '삼성전자,LG화학'")
    date: Optional[str] = Field(None, description="[무시됨] 참고용 날짜. 실제 조회는 항상 현재 시점 기준으로 수행됩니다.")

# schemas.py 파일에 아래 클래스 추가

class CombinedConditionArgs(BaseModel):
    """
    등락률과 거래량 변동률의 복합 조건으로 종목을 검색하는 도구의 인자 스키마입니다.
    """
    date: str = Field(..., description="조회할 기준 날짜 (YYYY-MM-DD 형식)")
    price_change_rate_threshold: float = Field(..., description="필터링할 '등락률(%)' 임계값. 예: 5.0, -10.0")
    price_change_operator: str = Field(..., description="등락률에 적용할 비교 연산자. 예: '>=', '<='")
    volume_change_rate_threshold: float = Field(..., description="필터링할 '거래량 변동률(%)' 임계값. 예: 150.0")
    volume_change_operator: str = Field(..., description="거래량 변동률에 적용할 비교 연산자. 예: '>=', '<='")