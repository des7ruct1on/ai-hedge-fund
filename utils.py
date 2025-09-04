from models import State, AgentOpinion, AggregatedDecision, RiskAssessment


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