from __future__ import annotations
import time
from typing import Dict, Optional, Literal
import requests
import pandas as pd
import logging

ISS_BASE = "https://iss.moex.com/iss"
DEFAULT_ENGINE = "stock"
DEFAULT_MARKET = "shares"
DEFAULT_BOARD = "TQBR"

Interval = Literal[1, 10, 60, 24]  # 24=daily candles per ISS

class MoexISS:
    """Thin client for MOEX ISS history & candles endpoints."""

    def __init__(self, engine: str = DEFAULT_ENGINE, market: str = DEFAULT_MARKET, session: Optional[requests.Session] = None):
        self.engine = engine
        self.market = market
        self.http = session or requests.Session()
        self.http.headers.update({"User-Agent": "moex-iss-client/1.0"})

    # -------- low-level --------
    def _get_json(self, url: str, params: Dict, retries: int = 4, backoff: float = 0.5) -> Dict:
        for attempt in range(1, retries + 1):
            try:
                r = self.http.get(url, params=params, timeout=30)
                r.raise_for_status()
                return r.json()
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(backoff * attempt)

    def _paginate(self, url: str, params: Dict, block: str) -> pd.DataFrame:
        frames = []
        start = 0
        while True:
            p = dict(params)
            p["start"] = start
            data = self._get_json(url, p)
            if block not in data:
                break
            cols = data[block]["columns"]
            rows = data[block]["data"]
            if not rows:
                break
            df = pd.DataFrame(rows, columns=cols)
            frames.append(df)

            cursor_key = f"{block}.cursor"
            if cursor_key in data and data[cursor_key]["data"]:
                total, pagesize, index = data[cursor_key]["data"][0]
                if index + pagesize >= total:
                    break
                start = index + pagesize
            else:
                break
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # -------- high-level --------
    def get_history_daily(
        self,
        secid: str,
        start_date: str,
        end_date: str,
        board: str = DEFAULT_BOARD,
        columns: Optional[str] = "TRADEDATE,OPEN,HIGH,LOW,CLOSE,LEGALCLOSEPRICE,VOLUME,VALUE,NUMTRADES"
    ) -> pd.DataFrame:
        """
        Daily EOD ('history') for a security on a board (e.g., TQBR).
        Returns columns incl. TRADEDATE, OPEN,HIGH,LOW,CLOSE,LEGALCLOSEPRICE, VOLUME, VALUE, NUMTRADES.
        """
        url = f"{ISS_BASE}/history/engines/{self.engine}/markets/{self.market}/boards/{board}/securities/{secid}.json"
        params = {"from": start_date, "till": end_date}
        if columns:
            params["history.columns"] = columns
        df = self._paginate(url, params, "history")
        if df.empty:
            return df
        # Normalize
        df.insert(0, "SECID", secid)
        df.rename(columns={"TRADEDATE": "date"}, inplace=True)
        # choose close_pref: LEGALCLOSEPRICE if present, else CLOSE
        if "LEGALCLOSEPRICE" in df.columns and df["LEGALCLOSEPRICE"].notna().any():
            df["close_pref"] = df["LEGALCLOSEPRICE"].fillna(df.get("CLOSE"))
        else:
            df["close_pref"] = df.get("CLOSE")
        return df

    def get_candles(
        self,
        secid: str,
        start_date: str,
        end_date: str,
        interval: Interval = 24,  # 24 = daily candles per ISS
    ) -> pd.DataFrame:
        """
        Interval candles (OHLCV) from /candles.
        For daily use interval=24. For intraday: 1/10/60 etc.
        """
        url = f"{ISS_BASE}/engines/{self.engine}/markets/{self.market}/securities/{secid}/candles.json"
        params = {"from": start_date, "till": end_date, "interval": interval}
        df = self._paginate(url, params, "candles")
        if df.empty:
            return df
        df.insert(0, "SECID", secid)
        # Normalize column names to lower-case ohlcv + begin/end
        rename_map = {
            "open": "open", "high": "high", "low": "low", "close": "close",
            "volume": "volume", "value": "value",
            "begin": "begin", "end": "end"
        }
        # Existing names might already match; just ensure lower-case
        df.columns = [c.lower() for c in df.columns]
        df.rename(columns=rename_map, inplace=True)
        return df
    
    def get_latest_price(self, user_data: dict) -> dict:
        """Обновляет текущие цены всех акций в портфеле"""
        from datetime import datetime, timedelta
        
        updated_data = user_data.copy()
        
        for ticker, stock_data in user_data.items():
            try:
                # Получаем даты для последнего торгового дня
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
                
                # Получаем свечи для конкретного тикера
                candles = self.get_candles(
                    secid=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    interval=24
                )
                
                if not candles.empty:
                    latest_price = float(candles.iloc[-1]['close'])
                    updated_data[ticker]['current_price'] = latest_price
                    logging.info(f"Updated {ticker} price: {latest_price}")
                else:
                    logging.warning(f"No candle data for {ticker}, keeping old price: {stock_data['current_price']}")
                    # Оставляем старую цену
                    continue
                    
            except Exception as e:
                logging.error(f"Error updating price for {ticker}: {e}")
                # Оставляем старую цену в случае ошибки
                continue
        
        return updated_data