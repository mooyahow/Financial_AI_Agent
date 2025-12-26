# tools.py (Phase 1-3 최종 버전)
import pandas as pd
import pandas_ta as ta
from dateutil.parser import parse as parse_date
from typing import Optional, List, Union, Literal
import time
import logging
from functools import wraps, partial
import re
import json
import yfinance as yf
from datetime import datetime, timedelta
import holidays
import pytz


from langchain.tools import Tool, StructuredTool
from pydantic import BaseModel, Field
from schemas import (
    PriceQueryArgs,
    StockFilterArgs,
    RateFilterArgs,
    BollingerTouchArgs,
    MovingAverageArgs,
    TopVolumeArgs,
    CrossDetectArgs,
    FindStocksByMaConditionArgs,
    MarketAverageArgs,
    VolumeRankArgs,
    MarketPercentageArgs,
    SimulateInvestmentArgs,
    MarketIndexInfoArgs,
    CompanyAnalysisArgs,
    RsiArgs,
    CrossCountArgs,
    TotalMarketValueArgs,
    YfMarketCapArgs,
    CombinedConditionArgs,
)


# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 1. 오류 처리 데코레이터 정의

def tool_error_handler(max_retries: int = 2, delay: int = 1):
    """
    도구 실행 중 발생하는 예외를 처리하고, 지정된 횟수만큼 재시도하는 데코레이터.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logging.warning(
                        f"도구 '{func.__name__}' 실행 중 오류 발생 (시도 {attempt + 1}/{max_retries}). "
                        f"에러: {e}. {delay}초 후 재시도합니다."
                    )
                    time.sleep(delay)
            # 최종 실패 시, 에이전트가 이해할 수 있는 문자열로 에러를 반환
            error_message = f"Error: Tool '{func.__name__}' failed after {max_retries} attempts. Last error: {last_exception}"
            logging.error(error_message)
            return error_message
        return wrapper
    return decorator


# 2. 도구 함수 정의

def adjust_date_to_business_day_kr(input_text: str) -> str:
    """
    input_text에서 단일 YYYY-MM-DD 패턴의 날짜를 찾아
    비영업일(주말/법정공휴일/근로자의 날)이면 휴일명을 하드코딩 응답으로 반환하고,
    영업일이면 원본 텍스트를 그대로 반환합니다.
    범위 날짜(2개 이상)나 날짜가 없으면 변경하지 않습니다.
    """
    pattern = r"\d{4}-\d{2}-\d{2}"
    dates = re.findall(pattern, input_text)

    # 단일 날짜인 경우
    if len(dates) == 1:
        date_str = dates[0]
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return input_text

        # 해당 연도 공휴일 조회
        kr_holidays = holidays.KR(years=[date.year])

        # 별도 처리할 근로자의 날
        def is_labor_day(d):
            return d.month == 5 and d.day == 1

        # 비영업일 정의
        def is_non_business(d):
            return d.weekday() >= 5 or d in kr_holidays or is_labor_day(d)

        # 비영업일이면 휴일명 하드코딩 응답
        if is_non_business(date):
            holiday_name = kr_holidays.get(date) or ("근로자의 날" if is_labor_day(date) else "공휴일")
            return f"'{date_str}'은(는) {holiday_name}입니다."

        # 영업일이면 LLM 호출용 원본 반환
        return input_text

    # 범위 날짜(2개 이상) 또는 날짜 없음
    return input_text

def adjust_invoked_date(date_str: str) -> str:
    """
    LLM invoking 후 단일 날짜 인자에 대해 비영업일이면 직전 영업일로 보정하여 반환합니다.
    """
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date_str

    kr_holidays = holidays.KR(years=[date.year])

    def is_labor_day(d):
        return d.month == 5 and d.day == 1

    def is_non_business(d):
        return d.weekday() >= 5 or d in kr_holidays or is_labor_day(d)

    # 직전 영업일까지 이동
    while is_non_business(date):
        date -= timedelta(days=1)

    return date.strftime("%Y-%m-%d")

@tool_error_handler(max_retries=2, delay=1)
def fn_query_market_index_info(date: str, mode: str = "value") -> str:
    import yfinance as yf
    import pandas as pd
    from datetime import timedelta
    import holidays

    # ✅ 한국 공휴일 정의 + 근로자의 날 포함
    kr_holidays = holidays.KR(years=[2024, 2025])
    is_holiday = lambda d: d.weekday() >= 5 or d in kr_holidays or (d.month == 5 and d.day == 1)

    # ✅ 영업일 보정
    def get_last_business_day(d: str) -> str:
        d = pd.to_datetime(d).date()
        while is_holiday(d):
            d -= timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    # ✅ 전일 영업일
    def get_previous_trading_day(d: str) -> str:
        d = pd.to_datetime(d).date() - timedelta(days=1)
        while is_holiday(d):
            d -= timedelta(days=1)
        return d.strftime("%Y-%m-%d")

    # ✅ 종가 조회
    def get_close(ticker: str, target_date: str) -> float:
        df = yf.download(ticker, start=target_date, end=pd.to_datetime(target_date) + timedelta(days=1), progress=False)
        if df.empty:
            return None
        try:
            price = df["Close"].iloc[0]
            return round(float(price), 2)
        except Exception:
            return None

    # ✅ 상승률 계산
    def get_change(ticker: str, target_date: str) -> float:
        today = get_last_business_day(target_date)
        prev = get_previous_trading_day(today)
        df = yf.download(ticker, start=prev, end=pd.to_datetime(today) + timedelta(days=1), progress=False).sort_index()
        try:
            today_price = df.loc[df.index.strftime('%Y-%m-%d') == today, "Close"].values[0]
            prev_price = df.loc[df.index.strftime('%Y-%m-%d') == prev, "Close"].values[0]
            return round(float((today_price - prev_price) / prev_price * 100), 2)
        except Exception:
            return None

    # ✅ 본 로직 실행
    indices = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11"}
    today = get_last_business_day(date)

    if mode == "value":
        v1 = get_close(indices["KOSPI"], today)
        v2 = get_close(indices["KOSDAQ"], today)
        if v1 is None or v2 is None:
            return f"{today} 기준 지수를 조회할 수 없습니다."
        return f"{today} KOSPI 지수: {v1}, KOSDAQ 지수: {v2}"

    elif mode == "compare_value":
        v1 = get_close(indices["KOSPI"], today)
        v2 = get_close(indices["KOSDAQ"], today)
        if v1 is None or v2 is None:
            return f"{today} 기준 지수 비교에 실패했습니다."
        if v1 > v2:
            return f"{today}에는 KOSPI 지수가 더 높습니다. ({v1} > {v2})"
        elif v1 < v2:
            return f"{today}에는 KOSDAQ 지수가 더 높습니다. ({v2} > {v1})"
        else:
            return f"{today}에는 KOSPI와 KOSDAQ 지수가 동일합니다. ({v1})"

    elif mode == "compare_change":
        g1 = get_change(indices["KOSPI"], today)
        g2 = get_change(indices["KOSDAQ"], today)
        if g1 is None or g2 is None:
            return f"{today} 기준 상승률 비교에 실패했습니다."
        if g1 > g2:
            return f"{today} 기준 상승률은 KOSPI가 더 높습니다. ({g1}% > {g2}%)"
        elif g1 < g2:
            return f"{today} 기준 상승률은 KOSDAQ이 더 높습니다. ({g2}% > {g1}%)"
        else:
            return f"{today} 기준 KOSPI와 KOSDAQ의 상승률이 동일합니다. ({g1}%)"

    return "지원되지 않는 mode입니다. 'value', 'compare_value', 'compare_change' 중 하나여야 합니다."

@tool_error_handler(max_retries=3, delay=2)
def apply_common_filters(df, column=None, operator=None, threshold=None, market=None):
    if market and 'market' in df.columns:
        df = df[df['market'].str.upper() == market.upper()]
    if column and threshold is not None:
        if column not in df.columns: return df
        target_series = pd.to_numeric(df[column], errors='coerce')
        if isinstance(threshold, list) and len(threshold) == 2:
            min_val, max_val = sorted(threshold)
            df = df[(target_series >= min_val) & (target_series <= max_val)]
        elif operator:
            if operator in ['>=', '이상', 'gte']: df = df[target_series >= threshold]
            elif operator in ['>', '초과', 'gt']: df = df[target_series > threshold]
            elif operator in ['<=', '이하', 'lte']: df = df[target_series <= threshold]
            elif operator in ['<', '미만', 'lt']: df = df[target_series < threshold]
            elif operator in ['==', '=', 'eq']: df = df[target_series == threshold]
    return df
#최종 출력 수정
@tool_error_handler()
def fn_get_stock_details_and_filter(DF_STOCK, date, ticker=None, stock_name=None, market=None, column_name=None, operator=None, threshold=None, n=None, sort_by=None, ascending=False, df=None):
    data = df if df is not None else DF_STOCK
    base_data = data[data['date'] == date].copy()
    if ticker: base_data = base_data[base_data['ticker'] == ticker]
    filtered_df = apply_common_filters(base_data, column_name, operator, threshold, market)
    if stock_name:  base_data = base_data[base_data['stock_name'] == stock_name]
    filtered_df = apply_common_filters(base_data, column_name, operator, threshold, market)
    if filtered_df.empty: return "요청하신 조건에 맞는 주식 데이터를 찾을 수 없습니다."
    sort_key = sort_by or column_name
    if sort_key and sort_key in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by=sort_key, ascending=ascending)
    if n is not None: filtered_df = filtered_df.head(n)
    return_cols = ['date', 'ticker', 'stock_name', column_name]
    for col in [column_name, sort_by]:
        if col and col not in return_cols: return_cols.append(col)
    final_cols = [col for col in return_cols if col in filtered_df.columns]
    final_df = filtered_df[final_cols].reset_index(drop=True)
    
    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    
    df_string = df_to_show.to_string()
    final_output_string = f"{df_string}\n\n[Total {total_rows} rows]"
    
    return final_output_string

@tool_error_handler()
def fn_find_stocks_by_daily_change(DF_STOCK, date: str, column_name: str, operator: str, threshold_percent: float, market: str = None, sort_by: str = None, ascending=False, df: pd.DataFrame = None):
    """
    특정 컬럼의 전일 대비 변화율을 계산하고, 주어진 조건에 맞는 종목을 정렬하여 반환합니다.
    """
    # 'price_change_rate'는 이미 계산된 값이므로 다른 도구를 사용하는 것이 더 적합합니다.
    # 여기서는 일관된 처리를 위해 로직을 유지하고 출력 컬럼을 맞춰줍니다.
    if column_name == 'price_change_rate':
        df1 = DF_STOCK[DF_STOCK['date'] == date]
        if market:
            df1 = df1[df1['market'].str.upper() == market.upper()]
        
        filtered_df = apply_common_filters(df1, 'price_change_rate', operator, threshold_percent)

        if filtered_df.empty:
            return "조건을 만족하는 종목을 찾을 수 없습니다."

        sort_key = sort_by or 'price_change_rate'
        sorted_df = filtered_df.sort_values(by=sort_key, ascending=ascending)
        
        # 요청된 출력 컬럼 선택 (신규 추가 열은 없으므로 price_change_rate만 포함)
        cols_to_return = ['stock_name', 'market', 'date', 'price_change_rate']
        final_df = sorted_df[cols_to_return].reset_index(drop=True)

        total_rows = len(final_df)
        df_to_show = final_df.head(20)
        df_string = df_to_show.to_string()
        return f"{df_string}\n\n[Total {total_rows} rows]"

    # --- 메인 로직 ---
    today_df = DF_STOCK[DF_STOCK['date'] == date].copy()
    if df is not None:
        today_df = today_df[today_df['stock_name'].isin(df['stock_name'].unique())]
    
    if market: today_df = today_df[today_df['market'] == market]
    if today_df.empty: return "조건에 해당하는 당일 데이터가 없습니다."
    
    prev_bday = DF_STOCK[DF_STOCK['date'] < date]['date'].max()
    if pd.isna(prev_bday): return "전일 데이터가 없어 비교가 불가능합니다."
    
    yesterday_df = DF_STOCK[DF_STOCK['date'] == prev_bday].copy()
    yesterday_col_name = f'yesterday_{column_name}'
    yesterday_comp_df = yesterday_df[['stock_name', column_name]].rename(columns={column_name: yesterday_col_name})
    
    merged_df = pd.merge(today_df, yesterday_comp_df, on='stock_name')
    merged_df = merged_df[merged_df[yesterday_col_name] != 0].copy()
    
    if merged_df.empty: return "전일 대비 변화율을 계산할 대상 종목이 없습니다."
        
    change_col_name = f'{column_name}_change_percent'
    merged_df[change_col_name] = ((merged_df[column_name] - merged_df[yesterday_col_name]) / merged_df[yesterday_col_name]) * 100
    
    result_df = apply_common_filters(merged_df, column=change_col_name, operator=operator, threshold=threshold_percent, market=None)
    
    if result_df.empty:
        return "조건을 만족하는 종목을 찾을 수 없습니다."

    # 정렬 우선순위 적용
    sort_keys = [change_col_name]
    if sort_by and sort_by in result_df.columns and sort_by not in sort_keys:
        sort_keys.append(sort_by)
    if 'price_change_rate' in result_df.columns and 'price_change_rate' not in sort_keys:
        sort_keys.append('price_change_rate')
    
    sorted_df = result_df.sort_values(by=sort_keys, ascending=ascending)

    # 최종 출력 컬럼 및 형식
    cols_to_return = ['stock_name', 'market', 'date', 'price_change_rate', change_col_name]
    final_cols = [c for c in cols_to_return if c in sorted_df.columns]
    
    final_df = sorted_df[final_cols].reset_index(drop=True)
    
    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    
    df_string = df_to_show.to_string()
    final_output_string = f"{df_string}\n\n[Total {total_rows} rows]"
    
    return final_output_string



#수정
@tool_error_handler()
def fn_get_rsi(DF_STOCK, date, stock_name=None, market=None, period=14, operator=None, threshold=None, n=None, ascending: bool = False, df=None):
    """
    특정 날짜를 기준으로 RSI(상대강도지수)를 계산하고, 주어진 조건에 맞는 종목을 정렬하여 반환합니다.
    - 표준 계산을 위해 `pandas-ta` 라이브러리를 사용합니다.
    - `operator`가 '<' 또는 '<='일 경우, 사용자 편의를 위해 자동으로 오름차순 정렬합니다.
    - 반환 전 인덱스를 리셋하여 깔끔하게 정리합니다.
    """
    data = df if df is not None else DF_STOCK
    end_date = parse_date(date)
    start_date = end_date - pd.offsets.BDay(period + 40)
    
    base_data = data[(data['date'] >= start_date.strftime('%Y-%m-%d')) & (data['date'] <= end_date.strftime('%Y-%m-%d'))].copy()
    
    if stock_name:
        base_data = base_data[base_data['stock_name'] == stock_name]
    
    def calculate_rsi(group):
        group[f'RSI_{period}'] = ta.rsi(group['adjusted_close'], length=period)
        return group
    
    rsi_df = base_data.groupby('stock_name', group_keys=False).apply(calculate_rsi)
    
    rsi_df.dropna(subset=[f'RSI_{period}'], inplace=True)
    result_df = rsi_df[rsi_df['date'] == date].copy()
    
    rsi_col_name = f'RSI_{period}'
    
    filtered_df = apply_common_filters(result_df, rsi_col_name, operator, threshold, market)

    if not filtered_df.empty:
        sort_order_ascending = True if operator in ['<', '<='] else ascending
        
        sorted_df = filtered_df.sort_values(by=rsi_col_name, ascending=sort_order_ascending)

        if n is not None:
            final_df = sorted_df.head(n)
        else:
            final_df = sorted_df
    else:
        final_df = filtered_df
    
    if final_df.empty:
        return "조건에 맞는 종목을 찾을 수 없습니다."

    final_df = final_df.reset_index(drop=True)

    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    df_string = df_to_show[['stock_name', 'market', 'date', rsi_col_name]].to_string()
    final_output_string = f"{df_string}\n\n[Total {total_rows} rows]"

    return final_output_string

@tool_error_handler()
def fn_find_bollinger_touch(DF_STOCK, date: str, window: int = 20, dev: int = 2, band: str = "lower", df=None):
    data = df if df is not None else DF_STOCK
    end_date = parse_date(date)
    start_date = end_date - pd.offsets.BDay(window + 40)
    data = data[(data['date'] >= start_date.strftime('%Y-%m-%d')) & (data['date'] <= end_date.strftime('%Y-%m-%d'))].copy()
    
    def calculate_bb(group):
        series = group['adjusted_close']
        ma = series.rolling(window).mean()
        sd = series.rolling(window).std()
        group[f'BB_upper_{window}'] = ma + (dev * sd)
        group[f'BB_lower_{window}'] = ma - (dev * sd)
        return group
        
    bb_df = data.groupby('stock_name', group_keys=False).apply(calculate_bb)
    
    # 밴드 종류에 따라 돌파율 계산 및 조건 설정
    if band == 'upper':
        touch_condition = bb_df['high_price'] >= bb_df[f'BB_upper_{window}']
        sort_key = 'penetration_rate'
        bb_df[sort_key] = ((bb_df['high_price'] - bb_df[f'BB_upper_{window}']) / bb_df[f'BB_upper_{window}']) * 100
        selected_cols = ['date', 'stock_name', 'market', 'high_price', f'BB_upper_{window}', sort_key]
    else:  # lower
        touch_condition = bb_df['low_price'] <= bb_df[f'BB_lower_{window}']
        sort_key = 'penetration_rate'
        bb_df[sort_key] = ((bb_df[f'BB_lower_{window}'] - bb_df['low_price']) / bb_df[f'BB_lower_{window}']) * 100
        selected_cols = ['date', 'stock_name', 'market', 'low_price', f'BB_lower_{window}', sort_key]

    result_df = bb_df[touch_condition]
    date_filtered_df = result_df[result_df['date'] == date].copy()

    if date_filtered_df.empty:
        return f"해당 날짜에 볼린저 밴드 {band} 밴드를 터치한 종목을 찾을 수 없습니다."

    # 돌파율(penetration_rate) 기준으로 내림차순 정렬
    sorted_df = date_filtered_df.sort_values(by=sort_key, ascending=False)
    
    # 최종 반환 문자열 생성
    final_df = sorted_df[selected_cols].reset_index(drop=True)
    
    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    
    df_string = df_to_show.to_string()
    final_output_string = f"{df_string}\n\n[Total {total_rows} rows]"

    return final_output_string

@tool_error_handler()
def fn_get_single_moving_average(DF_STOCK, date: str, window: int, stock_name: str = None, column_name: str = "adjusted_close", df=None):
    alias_map = {
        "close": "closing_price",
        "open": "opening_price",
        "high": "high_price",
        "low": "low_price",
        "volume": "trading_volume",
    }
    col = column_name.lower()
    column = alias_map.get(col, column_name)
    if column not in DF_STOCK.columns:
        raise KeyError(f"Column not found: {column}")
    source_data = DF_STOCK.copy() 
    ma_col_name = f"MA_{window}"
    source_data[ma_col_name] = source_data.groupby('stock_name')[column].rolling(window=window, min_periods=window).mean().reset_index(level=0, drop=True)
    result_df = source_data[source_data['date'] == date].copy()
    if stock_name: result_df = result_df[result_df['stock_name'] == stock_name]
    elif df is not None: result_df = result_df[result_df['stock_name'].isin(df['stock_name'].unique())]
    return result_df.dropna(subset=[ma_col_name])

@tool_error_handler()
def fn_find_top_volume_stocks(DF_STOCK, start_date: str, end_date: str, n: int, market: Optional[str] = None, df=None):
    data = df if df is not None else DF_STOCK
    period_data = data[(data['date'] >= start_date) & (data['date'] <= end_date)]
    if market:
        period_data = period_data[period_data['market'].str.upper() == market.upper()]
    volume_sum = (
        period_data
        .groupby('stock_name', as_index=False)['trading_volume'].sum().rename(columns={'trading_volume': 'trading_volume_sum'})
    )
    top_n = volume_sum.nlargest(n, 'trading_volume_sum')
    
    return top_n.reset_index(drop=True)


# 추가
def _calculate_cross_df(DF_STOCK, start_date: str, end_date: str, event_type: str, stock_name: Optional[str], short_window: int, long_window: int, column_name: str, df: Optional[pd.DataFrame]):
    """[내부용] 단일 이벤트 타입에 대한 크로스 DataFrame을 계산하고 정렬하여 반환"""
    data = df.copy() if df is not None else DF_STOCK.copy()
    if stock_name:
        data = data[data['stock_name'] == stock_name]
    
    s_date_calc, e_date_calc = pd.to_datetime(start_date) - pd.offsets.BDay(long_window + 5), pd.to_datetime(end_date)
    data['date'] = pd.to_datetime(data['date'])
    data = data[(data['date'] >= s_date_calc) & (data['date'] <= e_date_calc)]
    
    if data.empty: return pd.DataFrame()
        
    ma_short_col, ma_long_col = f'MA_{column_name}_{short_window}', f'MA_{column_name}_{long_window}'
    data[ma_short_col] = data.groupby('stock_name')[column_name].rolling(window=short_window).mean().reset_index(level=0, drop=True)
    data[ma_long_col] = data.groupby('stock_name')[column_name].rolling(window=long_window).mean().reset_index(level=0, drop=True)
    
    prev_ma_short = data.groupby('stock_name')[ma_short_col].shift(1)
    prev_ma_long = data.groupby('stock_name')[ma_long_col].shift(1)
    
    event_type_lower = event_type.lower()
    if "golden" in event_type_lower or "골든" in event_type_lower:
        mask = (data[ma_short_col] > data[ma_long_col]) & (prev_ma_short <= prev_ma_long)
    elif "dead" in event_type_lower or "데드" in event_type_lower:
        mask = (data[ma_short_col] < data[ma_long_col]) & (prev_ma_short >= prev_ma_long)
    else:
        return pd.DataFrame()
        
    cross_df = data[mask]
    final_df = cross_df[(cross_df['date'] >= pd.to_datetime(start_date)) & (cross_df['date'] <= pd.to_datetime(end_date))].copy()
    
    if not final_df.empty:
        final_df['event_type'] = event_type
    
    return final_df.sort_values(by='date', ascending=False)

@tool_error_handler()
def fn_get_cross_list(DF_STOCK, start_date: str, end_date: str, event_type, stock_name: str = None, short_window: int = 5, long_window: int = 20, column_name: str = 'closing_price', df=None):
    """지정된 기간 동안 골든/데드 크로스가 발생한 종목의 리스트를 반환합니다."""
    event_types = [event_type] if not isinstance(event_type, list) else event_type
    
    output_strings = []
    is_multi_call = len(event_types) > 1
    
    for et in event_types:
        # 내부 헬퍼 함수를 호출하여 계산된 데이터프레임을 받음
        result_df = _calculate_cross_df(DF_STOCK, start_date, end_date, et, stock_name, short_window, long_window, column_name, df)

        if result_df.empty:
            output_strings.append(f"\n=== {et} 결과 ===\n지정된 기간 내 이벤트를 찾을 수 없습니다.")
            continue
            
        n_to_show = 10 if is_multi_call else 20
        total_rows = len(result_df)
        df_to_show = result_df.head(n_to_show)
        
        ma_short_col = f'MA_{column_name}_{short_window}'
        ma_long_col = f'MA_{column_name}_{long_window}'
        cols_to_return = ['date', 'stock_name', 'event_type', column_name, ma_short_col, ma_long_col]
        final_cols = [c for c in cols_to_return if c in df_to_show.columns]
        
        df_string = df_to_show[final_cols].reset_index(drop=True).to_string()
        
        title = f"\n=== {et} 결과 ({total_rows}건) ==="
        summary = f"\n\n[Total {total_rows} rows, showing top {len(df_to_show)}]"
        output_strings.append(f"{title}\n{df_string}{summary}")

    return "\n\n---\n\n".join(output_strings)

@tool_error_handler()
def fn_count_cross_events(DF_STOCK, start_date: str, end_date: str, event_type, stock_name: str = None, short_window: int = 5, long_window: int = 20, column_name: str = 'closing_price', df=None):
    """지정된 기간 동안의 골든/데드 크로스 발생 횟수를 계산합니다."""
    event_types = [event_type] if not isinstance(event_type, list) else event_type
    
    counts = []
    for et in event_types:
        # 내부 헬퍼 함수를 호출하여 데이터프레임을 받음
        result_df = _calculate_cross_df(DF_STOCK, start_date, end_date, et, stock_name, short_window, long_window, column_name, df)
        # 데이터프레임의 길이(row 개수)를 계산
        count = len(result_df)
        counts.append(f"'{et}' 발생 횟수: {count}건")
        
    return "\n".join(counts)

@tool_error_handler()
def fn_find_stocks_by_ma_condition(DF_STOCK, date: str, ma_window: int, operator: str, threshold_percent: float = 0.0, column_name: str = "closing_price", df=None):
    stock_names_in_pipe = df['stock_name'].unique() if df is not None else None
    source_data = DF_STOCK.copy()
    if stock_names_in_pipe is not None: 
        source_data = source_data[source_data['stock_name'].isin(stock_names_in_pipe)]
    
    ma_col = f"MA_{column_name}_{ma_window}"
    source_data[ma_col] = source_data.groupby('stock_name')[column_name].rolling(window=ma_window).mean().reset_index(level=0, drop=True)
    
    target_date_df = source_data[source_data['date'] == date].copy()
    
    if target_date_df.empty or target_date_df[ma_col].isnull().all():
        return "해당 날짜의 데이터가 부족하여 이동평균을 계산할 수 없습니다."
    
    ma_values, current_values = target_date_df[ma_col], target_date_df[column_name]
    target_price = ma_values * (1 + threshold_percent / 100)
    
    op = operator.lower()
    if op in ['>=', '이상', 'gte']: passed = current_values >= target_price
    elif op in ['>', '초과', 'gt']: passed = current_values > target_price
    elif op in ['<=', '이하', 'lte']: passed = current_values <= target_price
    elif op in ['<', '미만', 'lt']: passed = current_values < target_price
    else: return "지원되지 않는 연산자입니다."
    
    result_df = target_date_df[passed].copy()
    
    if not result_df.empty:
        valid_ma_values = ma_values[passed]
        result_df['increase_rate'] = ((result_df[column_name] - valid_ma_values) / valid_ma_values.replace(0, pd.NA)) * 100
        result_df['target_price'] = target_price[passed]

    cols_to_return = ['stock_name', 'market', 'date', column_name, ma_col, 'increase_rate']
    final_cols = [c for c in cols_to_return if c in result_df.columns]
    
    if result_df.empty:
        return "조건에 맞는 종목을 찾을 수 없습니다."

    sorted_df = result_df.sort_values(by='increase_rate', ascending=False, na_position='last')
    
    final_df = sorted_df[final_cols].reset_index(drop=True)
    
    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    
    df_string = df_to_show.to_string()
    final_output_string = f"{df_string}\n\n[Total {total_rows} rows]"

    return final_output_string

def extract_json(raw: str) -> str:
    """LLM 응답에서 JSON 객체(또는 리스트)를 추출합니다."""
    m = re.search(r"```json\s*([\[\{].*?[\]\}])\s*```", raw, re.S)
    if m:
        return m.group(1).strip()
    m = re.search(r"([\[\{].*?[\]\}])", raw, re.S)
    if m:
        return m.group(1).strip()
    raise ValueError("응답에서 JSON 블록을 찾을 수 없습니다.")

@tool_error_handler()
def fn_calc_market_average_rate(
    DF_STOCK,
    date: str,
    market: Optional[str] = None,
    column_name: str = None,
    df: pd.DataFrame = None
) -> float:
    """
    date와 market/stock_name, column_name을 받아
    해당 시장 혹은 종목 시장의 지정 컬럼 평균을 계산해 반환합니다.
    """
    data = df if df is not None else DF_STOCK
# 1) 날짜 필터
    subset = data[data["date"] == date].copy()
    if subset.empty:
        raise ValueError(f"No data for date={date}")

    # 2) 시장 필터 (없으면 전체)
    if market:
        subset = subset[subset["market"].str.upper() == market.upper()]
        if subset.empty:
            raise ValueError(f"No data for market={market} on date={date}")

    # 3) 컬럼 숫자화 및 누락값 제거
    ser = subset[column_name].astype(str)
    if ser.str.endswith("%").any():
        ser = ser.str.rstrip("%")
    subset[column_name] = pd.to_numeric(ser, errors="coerce")
    subset = subset.dropna(subset=[column_name])
    if subset.empty:
        raise ValueError(f"No valid values for '{column_name}' on {date}")

    # 4) 평균 계산
    return subset[column_name].mean()


@tool_error_handler()
def fn_get_volume_rank(
    DF_STOCK,
    date: str,
    stock_name: str,
    column_name: str,
    market: Optional[str] = None,
    df: pd.DataFrame = None
) -> int:
    """
    date, stock_name, column_name, market(optional)을 받아
    해당 날짜·(옵션)시장 전체의 column_name 값 내림차순으로 정렬한 뒤,
    stock_name 종목의 1-based 순위를 반환합니다.
    """
    data = df if df is not None else DF_STOCK

    # 1) 날짜 필터
    subset = data[data["date"] == date].copy()
    if subset.empty:
        raise ValueError(f"No data for date={date}")

    # 2) 시장 필터 (없으면 전체 시장)
    if market:
        subset = subset[subset["market"].str.upper() == market.upper()]
        if subset.empty:
            raise ValueError(f"No data for market={market} on date={date}")

    # 3) 기준 컬럼 숫자화
    subset[column_name] = pd.to_numeric(subset[column_name], errors="coerce")
    subset = subset.dropna(subset=[column_name])
    if subset.empty:
        raise ValueError(f"No valid values for '{column_name}' on {date}")

    # 4) 내림차순 정렬
    subset = subset.sort_values(by=column_name, ascending=False).reset_index(drop=True)

    # 5) stock_name 위치 찾기
    mask = subset["stock_name"].str.upper() == stock_name.upper()
    if not mask.any():
        raise ValueError(f"Stock '{stock_name}' not found on {date}")
    return int(subset[mask].index[0] + 1)


@tool_error_handler()
def fn_calc_market_percentage(
    DF_STOCK,
    date: str,
    stock_name: str,
    column_name: str,
    market: Optional[str] = None,
    df: pd.DataFrame = None
) -> float:
    """
    date, stock_name, column_name, market(optional)을 받아
    해당 날짜·(optional)시장 전체의
    column_name 합계 대비 stock_name의 column_name 비율(%)을 반환합니다.
    """
    data = df if df is not None else DF_STOCK

    # 1) 날짜 필터
    subset = data[data["date"] == date].copy()
    if subset.empty:
        raise ValueError(f"No data for date={date}")

    # 2) 시장 필터 (market이 있으면, 없으면 전체 시장)
    if market:
        subset = subset[subset["market"].str.upper() == market.upper()]
        if subset.empty:
            raise ValueError(f"No data for market={market} on date={date}")

    # 3) column_name 숫자화 및 누락값 제거
    ser = subset[column_name].astype(str)
    if ser.str.endswith("%").any():
        ser = ser.str.rstrip("%")
    subset[column_name] = pd.to_numeric(ser, errors="coerce")
    subset = subset.dropna(subset=[column_name])
    if subset.empty:
        raise ValueError(f"No valid values for '{column_name}' on {date}")

    # 4) 전체 합계 및 대상 종목 값 추출
    total = subset[column_name].sum()
    row = subset[subset["stock_name"].str.upper() == stock_name.upper()]
    if row.empty:
        raise ValueError(f"Stock '{stock_name}' not found on {date}")
    value = float(row.iloc[0][column_name])

    # 5) 백분율 계산
    pct = (value / total) * 100
    # 소수점 셋째 자리에서 반올림하여 소수점 둘째 자리까지만 유지
    pct_rounded = round(pct, 4)  # 0.0348
    # 문자열로 '%' 붙여서 반환
    return f"{pct_rounded}%"


@tool_error_handler()
def fn_get_total_market_value(DF_STOCK, date: str, market: Optional[str] = None):
    """특정 날짜의 전체 또는 개별 시장의 총 추정 거래대금을 '일일 평균 가격'을 사용하여 계산합니다."""
    
    # 날짜로 데이터 필터링
    date_df = DF_STOCK[DF_STOCK['date'] == date].copy()
    if date_df.empty:
        return f"{date}에 대한 데이터가 없습니다."

    # 시장별로 데이터 필터링 (market이 지정된 경우)
    target_df = date_df
    market_name = "전체"
    if market:
        market_name = market.upper()
        target_df = date_df[date_df['market'].str.upper() == market_name]
        if target_df.empty:
            return f"{date}의 {market_name} 시장에 대한 데이터가 없습니다."

    # --- 거래대금 계산 로직 수정 ---

    # 1. 계산에 필요한 컬럼이 있는지 확인
    required_cols = ['high_price', 'low_price', 'closing_price', 'trading_volume']
    if not all(col in target_df.columns for col in required_cols):
        return "오류: 거래대금 계산에 필요한 컬럼(고가, 저가, 종가, 거래량)이 부족합니다."

    # 2. 일일 평균 가격(Typical Price) 계산
    typical_price = (target_df['high_price'] + target_df['low_price'] + target_df['closing_price']) / 3
    
    # 3. 추정 거래대금 계산 및 합산
    total_value = (typical_price * target_df['trading_volume']).sum()
    
    # --- 로직 수정 끝 ---

    # 읽기 쉽게 조/억 단위로 포맷팅
    def format_korean_currency(value):
        trillion = 1_000_000_000_000
        billion = 1_000_000_000
        if value >= trillion:
            return f"{value / trillion:,.2f}조 원"
        if value >= billion:
            return f"{value / billion:,.2f}억 원"
        return f"{value:,.0f} 원"
    
    formatted_value = format_korean_currency(total_value)
    
    return f"{date} {market_name} 시장의 총 추정 거래대금은 {formatted_value}입니다."

@tool_error_handler()
def fn_get_yf_market_cap(df_info: pd.DataFrame, stock_name: str, date: Optional[str] = None):
    """yfinance를 사용하여 '현재 시점'의 시가총액을 조회하고, 여러 종목일 경우 비교하여 정렬된 결과를 반환합니다."""
    
    # 쉼표로 구분된 문자열을 리스트로 변환 (단일 종목도 처리 가능)
    stock_list = [s.strip() for s in stock_name.split(',')]
    
    market_cap_results = []

    # 각 종목에 대해 yfinance API 호출
    for s_name in stock_list:
        info_row = df_info[df_info['stock_name'].str.upper() == s_name.upper()]
        if info_row.empty:
            market_cap_results.append({'stock_name': s_name, 'market_cap': '종목 정보 없음'})
            continue
        
        ticker = info_row.iloc[0]['ticker']
        
        # 안정적인 티커 생성 로직 적용
        if not any(ticker.endswith(suffix) for suffix in ['.KS', '.KQ']):
            market = info_row.iloc[0]['market']
            yf_ticker = f"{ticker}.KS" if market == 'KOSPI' else f"{ticker}.KQ"
        else:
            yf_ticker = ticker
        
        try:
            info = yf.Ticker(yf_ticker).info
            market_cap = info.get('marketCap')
            if market_cap:
                market_cap_results.append({'stock_name': s_name, 'market_cap': market_cap})
            else:
                market_cap_results.append({'stock_name': s_name, 'market_cap': 'yfinance에 정보 없음'})
        except Exception as e:
            market_cap_results.append({'stock_name': s_name, 'market_cap': 'API 조회 오류'})

    if not market_cap_results:
        return "시가총액 정보를 조회할 수 없습니다."

    # 결과를 데이터프레임으로 변환
    result_df = pd.DataFrame(market_cap_results)
    
    # 숫자형 데이터와 문자열(오류) 데이터를 분리
    numeric_df = result_df[pd.to_numeric(result_df['market_cap'], errors='coerce').notna()].copy()
    error_df = result_df[pd.to_numeric(result_df['market_cap'], errors='coerce').isna()]

    # 최종 결과 문자열을 담을 리스트
    output_parts = []

    # 숫자 결과가 있는 경우, 정렬하고 포맷팅하여 추가
    if not numeric_df.empty:
        numeric_df['market_cap'] = pd.to_numeric(numeric_df['market_cap'])
        sorted_df = numeric_df.sort_values(by='market_cap', ascending=False)

        def format_korean_currency(value):
            trillion = 1_000_000_000_000
            billion = 1_000_000_000
            if value >= trillion: return f"{value / trillion:,.2f}조 원"
            if value >= billion: return f"{value / billion:,.2f}억 원"
            return f"{value:,.0f} 원"

        sorted_df['market_cap_formatted'] = sorted_df['market_cap'].apply(format_korean_currency)
        
        final_numeric_df = sorted_df[['stock_name', 'market_cap_formatted']].rename(columns={'market_cap_formatted': 'current_market_cap'})
        output_parts.append(final_numeric_df.reset_index(drop=True).to_string())

    # 오류 결과가 있는 경우, 오류 정보도 추가
    if not error_df.empty:
        error_info_df = error_df.rename(columns={'market_cap': '조회 결과'})
        output_parts.append("\n\n--- 조회 실패 목록 ---\n" + error_info_df.to_string(index=False))

    # 최종 반환 문자열 생성
    final_output = "\n".join(output_parts)
    
    # 사용자가 날짜를 입력한 경우, 안내 문구 추가
    if date:
        date_info = f"\n\n(참고: 요청하신 '{date}'의 과거 시가총액은 조회가 불가능하여, 현재 시점의 정보로 제공합니다.)"
        final_output += date_info
        
    return final_output
# tools.py 파일에 아래 새 함수 추가

@tool_error_handler()
def fn_find_stocks_by_combined_conditions(DF_STOCK, date: str, price_change_rate_threshold: float, price_change_operator: str, volume_change_rate_threshold: float, volume_change_operator: str):
    """(효율성/유연성 개선 버전) 등락률과 거래량 변동률의 복합 조건으로 종목을 검색합니다."""
    
    # 1. 필요한 날짜(당일, 전일) 데이터 조회
    date = pd.to_datetime(date)
    prev_bday = DF_STOCK[DF_STOCK['date'] < date]['date'].max()
    if pd.isna(prev_bday):
        return "전일 데이터가 없어 비교가 불가능합니다."
    
    target_df = DF_STOCK[DF_STOCK['date'].isin([date, prev_bday])].copy()

    # 2. 전일 거래량을 효율적으로 매핑
    yesterday_volume_map = target_df[target_df['date'] == prev_bday].set_index('stock_name')['trading_volume']
    today_df = target_df[target_df['date'] == date].copy()
    today_df['yesterday_trading_volume'] = today_df['stock_name'].map(yesterday_volume_map)

    today_df.dropna(subset=['yesterday_trading_volume'], inplace=True)
    today_df = today_df[today_df['yesterday_trading_volume'] != 0]

    if today_df.empty:
        return "해당 날짜에는 모든 조건을 만족하는 종목이 없습니다."

    # 3. 변동률 컬럼 계산
    today_df['volume_change_percent'] = ((today_df['trading_volume'] - today_df['yesterday_trading_volume']) / today_df['yesterday_trading_volume']) * 100

    # 4. 동적 필터링 적용
    # 1차: 등락률 조건으로 필터링
    price_filtered_df = apply_common_filters(
        df=today_df,
        column='price_change_rate',
        operator=price_change_operator,
        threshold=price_change_rate_threshold
    )
    if price_filtered_df.empty:
        return "해당 날짜에는 등락률 조건을 만족하는 종목이 없습니다."
        
    # 2차: 거래량 변동률 조건으로 필터링
    final_df = apply_common_filters(
        df=price_filtered_df,
        column='volume_change_percent',
        operator=volume_change_operator,
        threshold=volume_change_rate_threshold
    )

    if final_df.empty:
        return "해당 날짜에는 모든 조건을 만족하는 종목이 없습니다."

    # 5. 최종 결과 포맷팅 및 반환
    final_df = final_df.sort_values(by='price_change_rate', ascending=False)
    
    cols_to_return = ['stock_name', 'market', 'date', 'price_change_rate', 'volume_change_percent']
    final_df = final_df[cols_to_return].reset_index(drop=True)
    
    total_rows = len(final_df)
    df_to_show = final_df.head(20)
    
    df_string = df_to_show.to_string()
    return f"{df_string}\n\n[Total {total_rows} rows]"


# add
@tool_error_handler(max_retries=3, delay=2)
def simulate_investment_return(
    stock_name: str,
    buy_date: str,
    quantity: int,
    df_stock: pd.DataFrame,
    df_info: pd.DataFrame,
    market: Optional[str] = None
) -> dict:
    """
    stock_name, buy_date, quantity를 입력받아 투자 수익률을 계산합니다.
    현재 가격은 yfinance에서 조회합니다.
    """
    buy_date = pd.to_datetime(buy_date).date()

    # 1. stock_name으로 ticker 찾기 (시장까지 고려 가능)
    info_subset = df_info[df_info["stock_name"].str.upper() == stock_name.upper()]
    if market:
        info_subset = info_subset[info_subset["market"].str.upper() == market.upper()]
    if info_subset.empty:
        raise ValueError(f"'{stock_name}'에 해당하는 종목 정보를 찾을 수 없습니다.")
    
    ticker = info_subset.iloc[0]["ticker"]
    yf_ticker = f"{ticker}.KS" if not ticker.endswith(".KS") else ticker  # 한국 종목 대응

    # 2. 매수 가격 조회 (df_stock 기반)
    df_ticker = df_stock[df_stock["ticker"] == ticker].copy()
    if df_ticker.empty:
        raise ValueError(f"'{ticker}'에 대한 주식 데이터가 없습니다.")

    df_ticker["date"] = pd.to_datetime(df_ticker["date"]).dt.date
    df_before = df_ticker[df_ticker["date"] <= buy_date]
    if df_before.empty:
        raise ValueError(f"{buy_date} 이전에 거래된 데이터가 없습니다.")
    buy_row = df_before.sort_values("date", ascending=False).iloc[0]
    buy_price = buy_row["closing_price"]

    # 3. 현재 가격 조회 (yfinance)
    try:
        # 비영업일일시, 자동으로 그 전 영업일의 데이터를 반환
        yf_data = yf.Ticker(yf_ticker).history(period="1d", interval="1d")
        if yf_data.empty:
            raise ValueError(f"yfinance에서 '{stock_name}'의 오늘 가격 데이터를 찾을 수 없습니다.")
        current_price = float(yf_data["Close"].iloc[0])
        current_date = yf_data.index[0].date()
    except Exception as e:
        raise RuntimeError(f"yfinance 조회 중 오류: {e}")

    # 4. 수익 계산
    total_buy = buy_price * quantity
    total_now = current_price * quantity
    profit = total_now - total_buy
    profit_rate = f"{(profit / total_buy * 100):.2f}%"

    return {
        "stock_name": stock_name,
        "ticker": ticker,
        "buy_date": str(buy_row["date"]),
        "buy_price": buy_price,
        "current_date": str(current_date),
        "current_price": current_price,
        "quantity": quantity,
        "profit": profit,
        "profit_rate": profit_rate,
    }

def format_financial_statement(statement_df, statement_name, items_to_show):
    """
    yfinance의 재무제표 DataFrame을 LLM이 이해하기 쉬운 문자열로 변환하는 헬퍼 함수
    """
    if statement_df.empty:
        return f"- {statement_name}: 데이터 없음\n"
    
    # 최근 4개년 데이터만 선택
    df = statement_df.iloc[:, :4]
    df.columns = [col.strftime('%Y') for col in df.columns] # 연도만 표시
    
    # 조 단위, 억원 단위 변환 함수
    def format_value(val):
        if abs(val) >= 1e12:
            return f"{val / 1e12:.2f}조"
        elif abs(val) >= 1e8:
            return f"{val / 1e8:.2f}억"
        return f"{val:,}"

    lines = [f"<{statement_name}>"]
    for item, name in items_to_show.items():
        if item in df.index:
            line = f"  - {name}: "
            values = [format_value(v) for v in df.loc[item].values]
            line += " -> ".join(values)
            lines.append(line)
            
    return "\n".join(lines) + "\n"

@tool_error_handler(max_retries=2, delay=1)
def fn_analyze_company_stability(llm, df_info, stock_name: str, ticker: Optional[str] = None) -> str:
    """
    기업의 재무 데이터와 과거 주가/거래량 데이터를 yfinance에서 조회하여 LLM을 통해 안정성을 종합적으로 분석하고 평가합니다.
    """
    # 1. Ticker 탐색
    yf_ticker = None
    if not ticker:
        info_row = df_info[df_info['stock_name'].str.upper() == stock_name.upper()]
        if info_row.empty:
            return f"Error: '{stock_name}'에 해당하는 종목 정보를 찾을 수 없습니다."
        ticker = info_row.iloc[0]['ticker']
        
    if not any(ticker.endswith(suffix) for suffix in ['.KS', '.KQ']):
        market = df_info.loc[df_info['ticker'] == ticker.replace('.KS', '').replace('.KQ', ''), 'market'].iloc[0]
        yf_ticker = f"{ticker}.KS" if market == 'KOSPI' else f"{ticker}.KQ"
    else:
        yf_ticker = ticker

    # 2. yfinance 데이터 조회
    try:
        company = yf.Ticker(yf_ticker)
        info = company.info
        if not info or 'longName' not in info: return f"Error: yfinance에서 '{stock_name}'({yf_ticker})의 상세 정보를 조회하지 못했습니다."
        hist = company.history(period="7mo")
        
        # 재무제표 데이터 추가 조회
        financials = company.financials
        balance_sheet = company.balance_sheet
        cashflow = company.cashflow
        
    except Exception as e:
        return f"Error: yfinance API 호출 중 오류 발생: {e}"

    # 3. LLM에게 전달할 핵심 지표 선택 및 가공 (이전과 동일)
    key_metrics = {
        "기업명": info.get("longName"), "업종": info.get("industry"), "사업 요약": info.get("longBusinessSummary"),
        "시가총액": f"{info.get('marketCap', 0) / 100000000:,.0f} 억원", "후행 PER": info.get("trailingPE"),
        "선행 PER": info.get("forwardPE"), "주당순이익 (EPS)": info.get("trailingEps"),
        "부채비율 (Debt to Equity)": info.get("debtToEquity"), "유동비율 (Current Ratio)": info.get("currentRatio"),
        "총자산순이익률 (ROA)": f"{info.get('returnOnAssets', 0) * 100:.2f}%", "자기자본순이익률 (ROE)": f"{info.get('returnOnEquity', 0) * 100:.2f}%",
        "영업현금흐름": f"{info.get('operatingCashflow', 0):,} 원", "잉여현금흐름": f"{info.get('freeCashflow', 0):,} 원",
        "배당수익률": f"{info.get('dividendYield', 0):.2f}%", "베타 (시장 변동성)": info.get("beta"),
    }
    metrics_str = "\n".join([f"- {key}: {value}" for key, value in key_metrics.items() if value is not None and str(value).lower() not in ['nan', 'none', 'n/a']])

    # 4. 과거 데이터 분석 (로직 수정)
    hist.index = pd.to_datetime(hist.index).tz_convert('Asia/Seoul')
    today = pd.Timestamp.now(tz='Asia/Seoul')

    periods = {
        "1주일": today - pd.DateOffset(weeks=1), "1개월": today - pd.DateOffset(months=1),
        "3개월": today - pd.DateOffset(months=3), "6개월": today - pd.DateOffset(months=6),
    }

    latest_data = hist.iloc[-1]
    
    historical_analysis = {
        "현재 종가": f"{latest_data['Close']:,.0f} 원", "현재 거래량": f"{latest_data['Volume']:,} 주"
    }

    for name, past_date in periods.items():
        past_data = hist.asof(past_date)
        
        if not pd.isna(past_data.name):
            price_change = (latest_data['Close'] - past_data['Close']) / past_data['Close'] * 100 if past_data['Close'] != 0 else 0
            historical_analysis[f"{name} 전 대비 종가"] = f"{price_change:+.2f}% (기준일: {past_data.name.strftime('%Y-%m-%d')})"
            
            volume_change = (latest_data['Volume'] - past_data['Volume']) / past_data['Volume'] * 100 if past_data['Volume'] != 0 else 0
            historical_analysis[f"{name} 전 대비 거래량"] = f"{volume_change:+.2f}%"
    
    historical_str = "\n".join([f"- {key}: {value}" for key, value in historical_analysis.items()])

    # 5. 재무제표 추세 분석 문자열 생성 (신규 추가)
    financial_trend_str = ""
    
    # 손익계산서 주요 항목
    income_items = {
        'Total Revenue': '총 매출',
        'Operating Income': '영업이익',
        'Net Income': '당기순이익'
    }
    financial_trend_str += format_financial_statement(financials, "손익계산서", income_items)

    # 재무상태표 주요 항목
    balance_items = {
        'Total Assets': '총자산',
        'Total Debt': '총부채',
        'Total Equity Gross Minority Interest': '총자본'
    }
    financial_trend_str += format_financial_statement(balance_sheet, "재무상태표", balance_items)
    
    # 현금흐름표 주요 항목
    cashflow_items = {
        'Operating Cash Flow': '영업활동 현금흐름',
        'Investing Cash Flow': '투자활동 현금흐름',
        'Financing Cash Flow': '재무활동 현금흐름',
        'Free Cash Flow': '잉여현금흐름(FCF)'
    }
    financial_trend_str += format_financial_statement(cashflow, "현금흐름표", cashflow_items)


    # 6. 최종 프롬프트 구성 (업데이트)
    prompt = f"""
        당신은 신중한 투자자를 위한 **금융 분석 전문가**입니다.

        아래 제공된 기업의 **1) 최신 재무 지표**, **2) 과거 주가 추세**, 그리고 **3) 연도별 재무제표 추이**를 종합적으로 분석하여, 해당 기업의 **재무 안정성**을 평가해주세요. 평가는 반드시 다음 형식에 맞춰, 각 항목을 명확하고 간결하게 설명해야 합니다.
        
        ## 핵심 분석 규칙
        1.  **근본 원인 추론 (Why?):** 부정적인 지표를 언급할 때, '왜냐하면 ~하기 때문이다' 형식으로 다른 재무제표 항목과 연결하여 그 근본 원인을 추론해야 합니다.
        2.  **객관적 비교 (Comparison):** 재무 비율을 평가할 때, 과거 데이터 또는 경쟁사와 비교하여 '높다/낮다'의 객관적인 기준을 제시해야 합니다.
        3.  **구체적 시그널 제시 (Actionable Signal):** 결론에서 '모니터링이 필요하다' 대신, 투자자가 주목해야 할 **핵심 관전 포인트 (긍정/부정 시그널)**를 명확하게 짚어줘야 합니다.
        4.  **데이터 이상치 의심:** 일반적이지 않은 극단적인 값(예: 기술주의 비정상적으로 높은 배당수익률)을 발견하면, 단정하지 말고 **'데이터 오류 또는 특이 현상일 수 있으므로 추가 확인이 필요함'** 이라고 명시적으로 언급해야 합니다.

        ---
        ### 1. 기업 재무 지표:
        {metrics_str}

        ### 2. 주가 및 거래량 추세 분석:
        {historical_str}
        
        ### 3. 재무제표 핵심 항목 추이:
        {financial_trend_str}
        ---

        ### 분석 결과:
        
        **1. 종합 평가:**
        (기업의 재무 상태, 성장성, 수익성, 현금흐름 등을 종합한 의견을 1~2문장으로 요약합니다.)

        **2. 긍정적 요인:**
        (재무/주가/추세 등 데이터에 기반하여 긍정적으로 평가할 수 있는 부분을 이유와 함께 설명합니다.)

        **3. 부정적 또는 우려 요인:**
        (데이터에 기반하여 잠재적 위험이나 부정적으로 볼 수 있는 부분을 이유와 함께 설명합니다.)

        **4. 안정성 점수:**
        (1점에서 10점까지 점수를 매기고, 그 이유를 위 데이터들을 근거로 간략하게 서술합니다. 10점이 가장 안정적임.)
    """

    # 7. LLM 호출 및 결과 반환
    try:
        response = llm.invoke(prompt, temperature=0.5, max_tokens=1500)
        return {
            "llm_analysis": response.content,
            "metrics_str": metrics_str,
            "historical_str": historical_str,
            "financial_trend_str": financial_trend_str
        }
    except Exception as e:
        return f"Error: LLM 호출 중 오류 발생: {e}"


# 3. 도구(Tool) 리스트 생성


def get_tools(client, df_stock: pd.DataFrame, df_info: pd.DataFrame) -> List[StructuredTool]:
    """
    주어진 주식 데이터프레임(df_stock)을 기반으로, 모든 금융 분석 도구를 반환합니다.
    """
    tools =  [
        StructuredTool.from_function(
            func=partial(fn_get_stock_details_and_filter,DF_STOCK=df_stock),
            args_schema=PriceQueryArgs,
            name="get_price",
            description=(
                "stock_name, date, column_name을 받아 "
                "특정 날짜에 특정 종목의 단일 정보(예: '종가', '거래량')를 정확히 조회할 때 사용합니다. "
                "'A와 B 비교' 질문처럼 특정 종목 간 비교 시에 가장 적합하고 안정적인 도구입니다."
            ),
        ),
        StructuredTool.from_function(
            func=partial(fn_get_stock_details_and_filter, DF_STOCK=df_stock),
            args_schema=StockFilterArgs,
            name="get_stock_details_and_filter",
            description=(
                "여러 조건(시장, 가격 등)으로 '다수의 불특정 종목을 필터링'할 때 사용합니다. "
                "주의: 'A와 B'처럼 두 개의 특정 종목을 비교할 때는 이 도구를 사용하지 마세요. 대신 'get_price'를 각 종목에 대해 한 번씩, 총 두 번 호출하세요."
            )
        ),
        StructuredTool.from_function(
            func=partial(fn_find_stocks_by_daily_change, DF_STOCK=df_stock),
            args_schema=RateFilterArgs,
            name="find_stocks_by_daily_change",
            description="date, rate_threshold, above, sort_by, ascending을 받아 전일 대비 등락률 조건에 맞는 종목을 정렬하여 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_get_rsi, DF_STOCK=df_stock),
            args_schema=RsiArgs,
            name="get_rsi",
            description="date, period, operator, threshold, market을 받아 RSI 조건에 맞는 종목을 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_find_bollinger_touch, DF_STOCK=df_stock),
            args_schema=BollingerTouchArgs,
            name="find_bollinger_band_touch",
            description="date, window, dev, band을 받아 볼린저 밴드 터치 종목을 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_get_single_moving_average, DF_STOCK=df_stock),
            args_schema=MovingAverageArgs,
            name="get_single_moving_average",
            description="date, stock_name, window, column_name을 받아 단일 이동평균 값을 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_find_top_volume_stocks, DF_STOCK=df_stock),
            args_schema=TopVolumeArgs,
            name="find_top_volume_stocks",
            description="start_date, end_date, n, market을 받아 지정 기간 누적 거래량 상위 종목을 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_count_cross_events, DF_STOCK=df_stock),
            args_schema=CrossCountArgs,
            name="count_cross_events",
            description="지정된 기간 동안의 골든/데드 크로스 발생 '횟수'를 계산하여 반환합니다. '몇 번' 또는 '얼마나' 같은 질문에 사용됩니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_get_cross_list, DF_STOCK=df_stock),
            args_schema=CrossDetectArgs, # 기존 스키마 재사용
            name="get_cross_list",
            description="지정된 기간 동안 골든/데드 크로스가 발생한 '종목의 리스트'를 반환합니다. '어떤 종목' 또는 '종목을 알려줘' 같은 질문에 사용됩니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_find_stocks_by_ma_condition, DF_STOCK=df_stock),
            args_schema=FindStocksByMaConditionArgs,
            name="find_stocks_by_ma_condition",
            description="date, ma_window, operator, threshold_percent, column_name을 받아 MA 조건 종목을 반환합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_calc_market_average_rate, DF_STOCK=df_stock),
            args_schema=MarketAverageArgs,
            name="calc_market_average_rate",
            description=(
                "date, column_name, market(optional), column_name을 받아 "
                "해당 날짜·(옵션)시장 전체의 지정 컬럼 평균을 계산해 반환합니다. "
                "market을 생략하면 전체 시장 데이터로 계산합니다."
                "column_name을 반드시 지정해야 합니다."
            ),
        ),
        StructuredTool.from_function(
            func=partial(fn_get_volume_rank, DF_STOCK=df_stock),
            args_schema=VolumeRankArgs,
            name="get_volume_rank",
            description=(
                "date, stock_name, column_name, market(optional)을 받아 "
                "해당 날짜·(옵션)시장 전체의 지정 컬럼 값을 내림차순 정렬한 뒤, "
                "stock_name 종목의 1-based 순위를 반환합니다."
            ),
        ),
        StructuredTool.from_function(
            func=partial(fn_calc_market_percentage, DF_STOCK=df_stock),
            args_schema=MarketPercentageArgs,
            name="calc_market_percentage",
            description=(
                "date, stock_name, column_name, market(optional)을 받아 "
                "해당 날짜·(옵션)시장 전체의 지정 컬럼 합계 대비 "
                "stock_name의 값이 차지하는 백분율을 계산하여, "
                "**소수점 둘째 자리까지** 반올림한 후 **문자열**로 '%'를 붙여 반환합니다. "
                "예: '0.035%'."
            ),
        ),
        StructuredTool.from_function(
            func=partial(simulate_investment_return, df_stock=df_stock, df_info=df_info),
            args_schema=SimulateInvestmentArgs,
            name="simulate_investment_return",
            description="특정 종목을 과거 날짜에 매수해서 오늘까지 보유한 경우의 수익률을 계산합니다. ticker, buy_date, quantity를 입력받습니다.",
        ),
        StructuredTool.from_function(
            func=fn_query_market_index_info,
            args_schema=MarketIndexInfoArgs,
            name="query_market_index_info",
            description=(
                "KOSPI와 KOSDAQ 지수를 조회하거나 비교합니다. "
                "date(날짜)와 mode('value', 'compare_value', 'compare_change')를 입력받아 "
                "지수 값 또는 전일 대비 상승률을 반환합니다."
             ),
        ),     
        StructuredTool.from_function(
            func=partial(fn_get_total_market_value, DF_STOCK=df_stock),
            args_schema=TotalMarketValueArgs,
            name="get_total_market_value",
            description="특정 날짜의 KOSPI, KOSDAQ, 또는 전체 시장의 총 거래대금을 계산합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_get_yf_market_cap, df_info=df_info),
            args_schema=YfMarketCapArgs,
            name="get_current_market_cap",
            description="yfinance를 통해 '현재 시점'의 시가총액을 조회합니다. 여러 종목을 쉼표로 구분하여 입력하면 비교 결과를 반환합니다. 과거 날짜 조회는 불가능합니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_find_stocks_by_combined_conditions, DF_STOCK=df_stock),
            args_schema=CombinedConditionArgs,
            name="find_stocks_by_combined_conditions",
            description="등락률과 거래량 변동률, 두 가지 복합 조건으로 종목을 검색할 때 사용하는 가장 적합한 도구입니다."
        ),
        StructuredTool.from_function(
            func=partial(fn_analyze_company_stability, llm=client, df_info=df_info),
            args_schema=CompanyAnalysisArgs,
            name="analyze_company_stability",
            description=(
                "특정 기업의 재무 데이터를 조회하고 LLM을 통해 안정성을 종합적으로 분석/평가하여, "
                "긍정/부정 요인과 안정성 점수를 포함한 상세 리포트를 생성합니다. "
                "투자 조언 전 기업의 기초 체력을 확인할 때 사용하세요."
            ),
        ),
    ]
    return tools
