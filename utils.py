from models import State, AgentOpinion, AggregatedDecision, RiskAssessment
from typing import Dict, Any, List
import datetime as _dt
import requests


def create_initial_state() -> State:
    return State(
        messages=[],
        message_to_user="",
        message_from_user="",
        stage="",
        user_data={},
        news_data=[],
        agent_opinions=[],
        aggregated_decisions=[],
        risk_assessments=[],
        final_recommendations=""
    )


def aggregate_agent_opinions(opinions: list) -> list:
    """Агрегирует мнения агентов в общие решения"""
    ticker_opinions = {}
    
    # Группируем мнения по тикерам
    for opinion in opinions:
        if opinion.ticker not in ticker_opinions:
            ticker_opinions[opinion.ticker] = []
        ticker_opinions[opinion.ticker].append(opinion)
    
    aggregated = []
    for ticker, ticker_ops in ticker_opinions.items():
        # Подсчитываем голоса за каждое действие
        action_votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
        total_confidence = 0
        
        for opinion in ticker_ops:
            action_votes[opinion.action] += opinion.confidence
            total_confidence += opinion.confidence
        
        # Определяем финальное действие
        final_action = max(action_votes, key=action_votes.get)
        
        # Вычисляем силу консенсуса
        max_votes = max(action_votes.values())
        total_votes = sum(action_votes.values())
        consensus_strength = max_votes / total_votes if total_votes > 0 else 0
        
        # Средняя уверенность
        avg_confidence = total_confidence / len(ticker_ops) if ticker_ops else 0
        
        aggregated.append(AggregatedDecision(
            ticker=ticker,
            final_action=final_action,
            confidence_score=avg_confidence,
            agent_opinions=ticker_ops,
            consensus_strength=consensus_strength
        ))
    
    return aggregated


def moex_candles_by_date(
    ticker: str,
    start_date: _dt.date,
    end_date: _dt.date,
    interval: int = 24,
) -> List[Dict[str, Any]]:
    """
    Fetch OHLC candles from MOEX ISS for a security between dates (inclusive).

    - interval=24 means daily bars (per MOEX ISS docs)
    - returns list of dicts with begin, open, high, low, close, volume
    - empty list on error
    """
    board = "TQBR"  # default board for most liquid shares
    engine = "stock"
    market = "shares"
    url = (
        f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{board}/"
        f"securities/{ticker}/candles.json"
    )
    params = {
        "from": start_date.isoformat(),
        "till": end_date.isoformat(),
        "interval": interval,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        columns = data.get("candles", {}).get("columns", [])
        rows = data.get("candles", {}).get("data", [])
        col_index = {name: i for i, name in enumerate(columns)}
        result: List[Dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "begin": row[col_index.get("begin")],
                    "open": row[col_index.get("open")],
                    "high": row[col_index.get("high")],
                    "low": row[col_index.get("low")],
                    "close": row[col_index.get("close")],
                    "volume": row[col_index.get("volume")],
                }
            )
        return result
    except Exception:
        return []