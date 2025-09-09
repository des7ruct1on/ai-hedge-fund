from __future__ import annotations
import time
from typing import Dict, Optional, Literal, Any
import requests
import pandas as pd
import logging
from .finance_metrics import MetricsResult, PortfolioMetrics

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

    def get_price_by_date(self, ticker: str, target_date: str) -> Optional[float]:
        """Получает цену акции на конкретную дату"""
        from datetime import datetime, timedelta
        
        try:
            # Преобразуем target_date в datetime если это строка
            if isinstance(target_date, str):
                target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            else:
                target_dt = target_date
            
            # Получаем данные за несколько дней вокруг целевой даты
            start_date = (target_dt - timedelta(days=5)).strftime("%Y-%m-%d")
            end_date = (target_dt + timedelta(days=5)).strftime("%Y-%m-%d")
            
            # Получаем свечи для конкретного тикера
            candles = self.get_candles(
                secid=ticker,
                start_date=start_date,
                end_date=end_date,
                interval=24
            )
            
            if not candles.empty:
                # Ищем цену на целевую дату или ближайшую торговую дату
                target_date_str = target_dt.strftime("%Y-%m-%d")
                
                # Сначала ищем точную дату
                exact_match = candles[candles['begin'].str[:10] == target_date_str]
                if not exact_match.empty:
                    price = float(exact_match.iloc[0]['close'])
                    logging.info(f"Found exact price for {ticker} on {target_date_str}: {price}")
                    return price
                
                # Если точной даты нет, ищем ближайшую торговую дату до целевой
                candles['date'] = pd.to_datetime(candles['begin']).dt.date
                target_date_only = target_dt.date()
                
                # Фильтруем даты до целевой даты включительно
                before_target = candles[candles['date'] <= target_date_only]
                if not before_target.empty:
                    # Берем последнюю доступную дату
                    latest_candle = before_target.iloc[-1]
                    price = float(latest_candle['close'])
                    actual_date = latest_candle['date'].strftime("%Y-%m-%d")
                    logging.info(f"Found nearest price for {ticker} on {actual_date} (target: {target_date_str}): {price}")
                    return price
                
                # Если нет данных до целевой даты, берем первую доступную дату после
                after_target = candles[candles['date'] > target_date_only]
                if not after_target.empty:
                    earliest_candle = after_target.iloc[0]
                    price = float(earliest_candle['close'])
                    actual_date = earliest_candle['date'].strftime("%Y-%m-%d")
                    logging.info(f"Found next available price for {ticker} on {actual_date} (target: {target_date_str}): {price}")
                    return price
            
            logging.warning(f"No price data found for {ticker} around {target_date}")
            return None
            
        except Exception as e:
            logging.error(f"Error getting price for {ticker} on {target_date}: {e}")
            return None


    def get_prices_by_date(self, user_data: dict, target_date: str) -> dict:
        """Обновляет цены всех акций в портфеле на конкретную дату"""
        updated_data = user_data.copy()
        
        for ticker, stock_data in user_data.items():
            try:
                price = self.get_price_by_date(ticker, target_date)
                if price is not None:
                    updated_data[ticker]['current_price'] = price
                    logging.info(f"Updated {ticker} price for {target_date}: {price}")
                else:
                    logging.warning(f"Could not get price for {ticker} on {target_date}, keeping old price: {stock_data.get('current_price', 'N/A')}")
                    
            except Exception as e:
                logging.error(f"Error updating price for {ticker} on {target_date}: {e}")
                continue
        
        return updated_data    
        
    def _candles_to_price_series(self, candles: Any, price_field: str = "close") -> pd.Series:
        """
        Приводит результат MoexISS.get_candles (DataFrame или list[dict]) к pd.Series цен,
        индекс = pd.DatetimeIndex (даты), значения = float цены.
        Попытки распознать поля: 'begin' -> datetime, иначе пытается использовать индекс.
        """
        if candles is None:
            raise ValueError("candles is None")

        # DataFrame или list/dict -> DataFrame
        if isinstance(candles, pd.DataFrame):
            df = candles.copy()
        else:
            # допускаем list[dict] или iterable
            df = pd.DataFrame(candles)

        if df.empty:
            raise ValueError("candles пустые")

        # Найдём колонку с датой (понижая регистр для поиска)
        lowered = {c.lower(): c for c in df.columns}
        for candidate in ("begin", "date", "tradedate", "trade_date", "datetime"):
            if candidate in lowered:
                df['__date'] = pd.to_datetime(df[lowered[candidate]])
                break
        else:
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.copy()
                df['__date'] = pd.to_datetime(df.index)
            else:
                # если нет явной date колонке — попробуем привести первую колонку, содержащую ISO-строки
                try:
                    df['__date'] = pd.to_datetime(df.iloc[:, 0])
                except Exception:
                    raise ValueError("Не удалось определить колонку с датой в candles")

        df.set_index('__date', inplace=True)
        df.index.name = None

        # Найдём колонку цены
        possible_price_cols = [c for c in df.columns if c.lower() == price_field.lower()]
        if not possible_price_cols:
            # fallback: common names
            for name in ("close", "last", "close_price", "c", "open"):
                if name in df.columns:
                    possible_price_cols = [name]
                    break
        if not possible_price_cols:
            raise ValueError(f"Не найдена колонка цены ('{price_field}' или fallback) в candles: {list(df.columns)}")

        col = possible_price_cols[0]
        ser = df[col].astype(float).sort_index()
        # убрать дубли по индексу
        ser = ser[~ser.index.duplicated(keep='first')]
        return ser


    def metrics_from_moex_candles(
        self,
        candles: Any,
        *,
        price_field: str = "close",
        market_price_field: str = "close",
        rf: float = 0.0,
        days_per_year: int = 252,
        alpha: float = 0.05
    ):
        """
        Основной wrapper: берёт свечи инструмента и (опционально) бенчмарка,
        формирует series цен и вызывает PortfolioMetrics.build_metrics.
        Возвращает MetricsResult.
        """
        # transform main asset candles -> price series
        prices = self._candles_to_price_series(candles, price_field=price_field)
        if prices.empty or len(prices) < 2:
            raise ValueError("Недостаточно точек в ценах инструмента для расчёта метрик")

        # подготовим market_returns (если есть)


        # вызываем build_metrics: передаём values=prices (PortfolioMetrics сам посчитает returns)
        metrics = PortfolioMetrics.build_metrics(
            values=prices,
            returns=None, 
            rf=rf,
            days_per_year=days_per_year,
            alpha=alpha
        )
        return metrics
    

from datetime import datetime, timedelta

# Инициализируем MoexISS
moex_iss = MoexISS()

# Параметры для запроса
secid = "SBER"  # Тикер, например, Сбербанк
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")  # Данные за год


candles = moex_iss.get_candles(
        secid=secid,
        start_date=start_date,
        end_date=end_date,
        interval=24  
    )
print(f"Получено {len(candles)} свечей для {secid}")
print(candles)

    # Запускаем функцию
result = moex_iss.metrics_from_moex_candles(
        candles=candles,
        price_field="close",
        market_price_field="close",
        rf=0.0,
        days_per_year=252,
        alpha=0.05
    )
    # Выводим результат
print("Результат метрик:")
print(result)
