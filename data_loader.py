
import duckdb
import pandas as pd


def load_data(db_path: str):
    """DuckDB에서 주식 데이터를 로드하고 초기 설정을 수행합니다."""
    try:
        con = duckdb.connect(db_path)
        df_stock = con.execute("SELECT * FROM stock_prices").fetchdf()
        con.close()
    except Exception as e:
        print(f"데이터 로드 중 오류 발생: {e}")
        return None, None

    df_stock.rename(columns={
        'open': 'opening_price',
        'high': 'high_price',
        'low': 'low_price',
        'close': 'closing_price'}, inplace=True)

    df_info = df_stock[['ticker', 'stock_name', 'market']].drop_duplicates().reset_index(drop=True)
    
    return df_stock, df_info