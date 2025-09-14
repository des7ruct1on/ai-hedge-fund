#!/usr/bin/env python3
"""
Тест для проверки суммаризации мнений агентов
"""

from utils.models import AgentOpinion, AggregatedDecision
from utils.utils import aggregate_agent_opinions

def test_agent_opinions_summarization():
    """Тестирует новую функциональность суммаризации мнений агентов"""
    
    # Создаем тестовые мнения агентов для разных тикеров
    test_opinions = [
        # Мнения для SBER
        AgentOpinion(
            agent_name="Fundamental Analyst",
            ticker="SBER",
            action="BUY",
            confidence=8,
            reasoning="Сильные финансовые показатели и стабильный дивидендный доход"
        ),
        AgentOpinion(
            agent_name="Technical Analyst", 
            ticker="SBER",
            action="BUY",
            confidence=7,
            reasoning="Пробитие сопротивления на уровне 280 рублей"
        ),
        AgentOpinion(
            agent_name="Risk Analyst",
            ticker="SBER", 
            action="HOLD",
            confidence=6,
            reasoning="Высокая волатильность на фоне геополитики"
        ),
        
        # Мнения для GAZP
        AgentOpinion(
            agent_name="Fundamental Analyst",
            ticker="GAZP",
            action="SELL",
            confidence=9,
            reasoning="Снижение экспорта газа в Европу и санкции"
        ),
        AgentOpinion(
            agent_name="Technical Analyst",
            ticker="GAZP",
            action="SELL", 
            confidence=8,
            reasoning="Нисходящий тренд и пробой поддержки"
        ),
    ]
    
    print("🧪 Тестирование суммаризации мнений агентов")
    print("=" * 50)
    
    # Агрегируем мнения
    aggregated = aggregate_agent_opinions(test_opinions)
    
    # Выводим результаты
    for decision in aggregated:
        print(f"\n📊 Тикер: {decision.ticker}")
        print(f"🎯 Финальное решение: {decision.final_action}")
        print(f"📈 Уверенность: {decision.confidence_score:.1f}/10")
        print(f"🤝 Сила консенсуса: {decision.consensus_strength:.1%}")
        print(f"👥 Количество агентов: {len(decision.agent_opinions)}")
        
        print(f"\n📝 Суммаризация мнений:")
        print(decision.summary_reasoning)
        
        print(f"\n👤 Детальные мнения агентов:")
        for opinion in decision.agent_opinions:
            print(f"  • {opinion.agent_name}: {opinion.action} (уверенность: {opinion.confidence}/10)")
            print(f"    Обоснование: {opinion.reasoning}")
        
        print("-" * 50)

if __name__ == "__main__":
    test_agent_opinions_summarization()
