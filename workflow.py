import json
from langgraph.graph import StateGraph, START, END
from models import State, AgentOpinion, AggregatedDecision, RiskAssessment
from enums import StageEnum
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from investor_agents import InvestorAgentRoom
from utils import aggregate_agent_opinions
from prompts import RISK_MANAGER_PROMPT, PORTFOLIO_AGENT_PROMPT
from langgraph.types import Command

class Graph(StateGraph):
    def __init__(self, llm):
        self.llm = llm
        self.memory = MemorySaver()
        self.agent_room = InvestorAgentRoom(llm)

    def get_graph(self):
        graph = StateGraph(State)

        graph.add_node(StageEnum.USER_DATA_NODE, self.user_data_node)
        graph.add_node(StageEnum.NEWS_DATA_NODE, self.news_data_node)
        graph.add_node(StageEnum.DISCUSSION_NODE, self.discussion_node)
        graph.add_node(StageEnum.RISK_NODE, self.risk_node)
        graph.add_node(StageEnum.FINALIZER_NODE, self.finalizer_node)

        graph.add_edge(START, StageEnum.DISCUSSION_NODE)
        graph.add_edge(StageEnum.RISK_NODE, StageEnum.FINALIZER_NODE)
        graph.add_edge(StageEnum.FINALIZER_NODE, END)

        return graph.compile(checkpointer=self.memory)

    def user_data_node(self, state: State) -> State:
        print("User data node")
        try:
            with open("user_portfolio.json", "r", encoding="utf-8") as f:
                user_data = json.load(f)
            
            print("User data loaded")
            return Command(
                goto=StageEnum.DISCUSSION_NODE,
                update={
                    "user_data": user_data,
                    "stage": StageEnum.DISCUSSION_NODE
                }
            )

        except Exception as e:
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка загрузки портфеля: {e}"
                }
            )

    def news_data_node(self, state: State) -> State:
        print("News data node")
        try:
            with open("sample_news.json", "r", encoding="utf-8") as f:
                news_data = json.load(f)
            
            print("News data loaded")
            return Command(
                goto=StageEnum.DISCUSSION_NODE,
                update={
                    "news_data": news_data,
                    "stage": StageEnum.DISCUSSION_NODE
                }
            )

        except Exception as e:
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка загрузки новостей: {e}"
                }
            )
    
    def discussion_node(self, state: State) -> State:
        print("Discussion node")
        try:
            # Проверяем наличие данных
            print("Checking user data")
            if not state.get("user_data"):
                return Command(
                    goto=StageEnum.USER_DATA_NODE,
                    update={
                        "stage": StageEnum.USER_DATA_NODE
                    }
                )

            print("Checking news data")
            if not state.get("news_data"):
                return Command(
                    goto=StageEnum.NEWS_DATA_NODE,
                    update={
                        "stage": StageEnum.NEWS_DATA_NODE
                    }
                )
            
            # Проводим обсуждение между агентами
            print("🤖 Агенты начинают обсуждение портфеля...")
            agent_opinions = self.agent_room.discuss_portfolio(
                state["user_data"], 
                state["news_data"]
            )
            
            # Агрегируем мнения агентов
            print(f"\n🔄 АГРЕГАЦИЯ РЕШЕНИЙ АГЕНТОВ")
            print("-" * 40)
            aggregated_decisions = aggregate_agent_opinions(agent_opinions)
            
            print(f"✅ Получено {len(agent_opinions)} мнений от агентов")
            print(f"📊 Агрегировано {len(aggregated_decisions)} решений")
            
            # Показываем агрегированные решения
            for decision in aggregated_decisions:
                print(f"📋 {decision.ticker}: {decision.final_action} "
                      f"(уверенность: {decision.confidence_score:.1f}, "
                      f"консенсус: {decision.consensus_strength:.1f})")

            return Command(
                goto=StageEnum.RISK_NODE,
                update={
                    "agent_opinions": agent_opinions,
                    "aggregated_decisions": aggregated_decisions,
                    "stage": StageEnum.RISK_NODE
                }
            )

        except Exception as e:
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка в обсуждении агентов: {e}"
                }
            )
                

    def risk_node(self, state: State) -> State:
        print("Risk node")
        try:
            print("⚠️ Риск-менеджер оценивает риски...")
            
            risk_assessments = []
            aggregated_decisions = state.get("aggregated_decisions", [])
            
            for decision in aggregated_decisions:
                # Формируем контекст для риск-менеджера
                context = f"""
                Тикер: {decision.ticker}
                Рекомендуемое действие: {decision.final_action}
                Уровень уверенности: {decision.confidence_score}
                Сила консенсуса: {decision.consensus_strength}
                
                Мнения агентов:
                """
                
                for opinion in decision.agent_opinions:
                    context += f"- {opinion.agent_name}: {opinion.action} (уверенность: {opinion.confidence})\n"
                    context += f"  Обоснование: {opinion.reasoning}\n"
                
                # Получаем оценку риска от LLM
                full_prompt = f"{RISK_MANAGER_PROMPT}\n\n{context}"
                
                try:
                    response = self.llm.complete(full_prompt, temperature=0.3, max_tokens=500)
                    
                    # Парсим ответ риск-менеджера
                    risk_level = self._extract_risk_level(response)
                    risk_factors = self._extract_risk_factors(response)
                    
                    risk_assessments.append(RiskAssessment(
                        ticker=decision.ticker,
                        risk_level=risk_level,
                        risk_factors=risk_factors,
                        recommendations=response
                    ))
                    
                except Exception as e:
                    print(f"Ошибка оценки риска для {decision.ticker}: {e}")
                    risk_assessments.append(RiskAssessment(
                        ticker=decision.ticker,
                        risk_level=5,
                        risk_factors=["Ошибка анализа"],
                        recommendations="Требуется дополнительный анализ"
                    ))
            
            print(f"✅ Оценены риски для {len(risk_assessments)} позиций")
            
            # Показываем оценки рисков
            for risk in risk_assessments:
                print(f"⚠️ {risk.ticker}: уровень риска {risk.risk_level}/10")

            return Command(
                goto=StageEnum.FINALIZER_NODE,
                update={
                    "risk_assessments": risk_assessments,
                    "stage": StageEnum.FINALIZER_NODE
                }
            )

        except Exception as e:
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка в оценке рисков: {e}"
                }
            )   
            

    def finalizer_node(self, state: State) -> State:
        print("Finalizer node")
        try:
            print("📋 Формирование итоговых рекомендаций...")
            
            # Формируем контекст для финализатора
            context = self._build_finalizer_context(state)
            
            # Получаем итоговые рекомендации
            full_prompt = f"{PORTFOLIO_AGENT_PROMPT}\n\n{context}"
            
            final_recommendations = self.llm.complete(full_prompt, temperature=0.5, max_tokens=2000)
            
            print("✅ Итоговые рекомендации сформированы")

            return Command(
                goto=END,
                update={
                "final_recommendations": final_recommendations,
                    "message_to_user": final_recommendations,
                    "stage": END
                }
            )

        except Exception as e:
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка формирования рекомендаций: {e}"
                }
            )

    def _extract_risk_level(self, response: str) -> int:
        """Извлекает уровень риска из ответа риск-менеджера"""
        import re
        risk_match = re.search(r'риск[а-я]*\s*[:\-]?\s*(\d+)', response, re.IGNORECASE)
        if risk_match:
            return int(risk_match.group(1))
        return 5  # Средний риск по умолчанию

    def _extract_risk_factors(self, response: str) -> list:
        """Извлекает факторы риска из ответа"""
        factors = []
        lines = response.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['риск', 'опасность', 'угроза']):
                factors.append(line.strip())
        return factors[:3]  # Берем первые 3 фактора

    def _build_finalizer_context(self, state: State) -> str:
        """Строит контекст для финализатора"""
        context = "АНАЛИЗ ПОРТФЕЛЯ\n\n"
        
        # Добавляем информацию о портфеле
        user_data = state.get("user_data", {})
        if user_data:
            context += "Текущий портфель:\n"
            for ticker, position in user_data.items():
                context += f"- {ticker}: {position.get('quantity', 0)} акций, "
                context += f"средняя цена: {position.get('avg_price', 0)} руб.\n"
            context += "\n"
        
        # Добавляем решения агентов
        aggregated_decisions = state.get("aggregated_decisions", [])
        if aggregated_decisions:
            context += "Рекомендации агентов:\n"
            for decision in aggregated_decisions:
                context += f"- {decision.ticker}: {decision.final_action} "
                context += f"(уверенность: {decision.confidence_score:.1f}, "
                context += f"консенсус: {decision.consensus_strength:.1f})\n"
            context += "\n"
        
        # Добавляем оценку рисков
        risk_assessments = state.get("risk_assessments", [])
        if risk_assessments:
            context += "Оценка рисков:\n"
            for risk in risk_assessments:
                context += f"- {risk.ticker}: уровень риска {risk.risk_level}/10\n"
            context += "\n"
        
        context += "Сформируй четкие рекомендации по управлению портфелем."
        
        return context