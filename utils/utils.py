from .models import State, AgentOpinion, AggregatedDecision, RiskAssessment
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


def _generate_summary_reasoning(ticker_ops: list, final_action: str, action_votes: dict) -> str:
    """Генерирует краткую суммаризацию мнений агентов"""
    if not ticker_ops:
        return "Нет мнений агентов для данного тикера."
    
    # Группируем мнения по действиям
    buy_opinions = [op for op in ticker_ops if op.action == "BUY"]
    sell_opinions = [op for op in ticker_ops if op.action == "SELL"]
    hold_opinions = [op for op in ticker_ops if op.action == "HOLD"]
    
    # Собираем основные аргументы для финального решения
    main_reasons = []
    if final_action == "BUY" and buy_opinions:
        main_reasons.extend([f"• {op.reasoning}" for op in buy_opinions[:2]])  # Берем до 2 основных аргументов
    elif final_action == "SELL" and sell_opinions:
        main_reasons.extend([f"• {op.reasoning}" for op in sell_opinions[:2]])
    elif final_action == "HOLD" and hold_opinions:
        main_reasons.extend([f"• {op.reasoning}" for op in hold_opinions[:2]])
    
    # Добавляем информацию о консенсусе
    total_agents = len(ticker_ops)
    consensus_info = f"Консенсус: {total_agents} агентов, {final_action} ({action_votes[final_action]:.1f} из {sum(action_votes.values()):.1f})"
    
    # Собираем финальную суммаризацию
    summary_parts = [consensus_info]
    if main_reasons:
        summary_parts.append("Основные аргументы:")
        summary_parts.extend(main_reasons[:2])  # Ограничиваем до 2 аргументов
    
    return "\n".join(summary_parts)


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
        
        # Генерируем суммаризацию мнений
        summary_reasoning = _generate_summary_reasoning(ticker_ops, final_action, action_votes)
        
        aggregated.append(AggregatedDecision(
            ticker=ticker,
            final_action=final_action,
            confidence_score=avg_confidence,
            agent_opinions=ticker_ops,
            consensus_strength=consensus_strength,
            summary_reasoning=summary_reasoning
        ))
    
    return aggregated

import requests
import datetime as _dt
from typing import List, Dict, Any

def get_primary_board_for_ticker(ticker: str) -> str:
    url = f"https://iss.moex.com/iss/securities/{ticker}.json"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    cols = data.get("securities", {}).get("columns", [])
    rows = data.get("securities", {}).get("data", [])
    if not rows:
        return ""
    idx = {c: i for i, c in enumerate(cols)}
    for key in ("primary_boardid", "boardid", "primary_board"):
        if key in idx:
            return rows[0][idx[key]] or ""
    return ""

def moex_candles_by_date(ticker: str, start_date: _dt.date, end_date: _dt.date, interval: int = 24, board: str = None) -> List[Dict[str, Any]]:
    engine = "stock"
    market = "shares"
    session = requests.Session()

    candidates = []
    candidates.append(f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/securities/{ticker}/candles.json")
    if board:
        candidates.insert(0, f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{ticker}/candles.json")
    else:
        pb = get_primary_board_for_ticker(ticker)
        if pb:
            candidates.append(f"https://iss.moex.com/iss/engines/{engine}/markets/{market}/boards/{pb}/securities/{ticker}/candles.json")

    params = {"from": start_date.isoformat(), "till": end_date.isoformat(), "interval": interval}
    for url in candidates:
        try:
            resp = session.get(url, params=params, timeout=15)
            print("Trying:", resp.url, "status:", resp.status_code)
            if resp.status_code != 200:
                print("Response text:", resp.text[:400])
                continue
            data = resp.json()
            candles = data.get("candles", {})
            cols = candles.get("columns", [])
            rows = candles.get("data", [])
            if rows:
                idx = {c: i for i, c in enumerate(cols)}
                return [
                    {
                        "begin": row[idx["begin"]],
                        "open": row[idx["open"]],
                        "high": row[idx["high"]],
                        "low": row[idx["low"]],
                        "close": row[idx["close"]],
                        "volume": row[idx["volume"]],
                    }
                    for row in rows
                ]
            else:
                print("No rows in candles for URL:", resp.url, "available blocks:", list(data.keys()))
        except Exception as e:
            print("Error fetching", url, "->", repr(e))
    return []
