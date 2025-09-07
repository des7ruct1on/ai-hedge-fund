"""
Упрощенная версия workflow для работы без FastAPI
"""
import json
import logging
from langgraph.graph import StateGraph, START, END
from utils.models import State, AgentOpinion, AggregatedDecision, RiskAssessment
from utils.enums import StageEnum
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from utils.investor_agents import InvestorAgentRoom
from ui.server.logger import ChatLogger
from utils.utils import aggregate_agent_opinions
from utils.prompts import RISK_MANAGER_PROMPT, PORTFOLIO_AGENT_PROMPT, ROUTER_PROMPT, FACT_NODE_PROMPT, OTHER_NODE_PROMPT
from langgraph.types import Command
from utils.backtest import BacktestEngine

logging.basicConfig(
    filename='simple_workflow.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

# Глобальные переменные для хранения результатов
analysis_results = {
    "agent_opinions": [],
    "aggregated_decisions": [],
    "risk_assessments": [],
    "final_recommendations": ""
}

class SimpleGraph(StateGraph):
    def __init__(self, llm):
        self.llm = llm
        self.memory = MemorySaver()
        self.agent_room = InvestorAgentRoom(llm)
        self.backtest_engine = BacktestEngine(llm)

    def get_graph(self):
        graph = StateGraph(State)

        graph.add_node(StageEnum.ROUTER_NODE, self.router_node)
        graph.add_node(StageEnum.USER_DATA_NODE, self.user_data_node)
        graph.add_node(StageEnum.NEWS_DATA_NODE, self.news_data_node)
        graph.add_node(StageEnum.DISCUSSION_NODE, self.discussion_node)
        graph.add_node(StageEnum.RISK_NODE, self.risk_node)
        graph.add_node(StageEnum.FINALIZER_NODE, self.finalizer_node)
        graph.add_node(StageEnum.FACT_NODE, self.fact_node)
        graph.add_node(StageEnum.OTHER_NODE, self.other_node)
        graph.add_node(StageEnum.BACKTEST_NODE, self.backtest_node)

        graph.add_edge(START, StageEnum.ROUTER_NODE)

        # Роутер выбирает путь
        graph.add_conditional_edges(
            StageEnum.ROUTER_NODE,
            lambda x: x["stage"],
            {
                StageEnum.DISCUSSION_NODE: StageEnum.DISCUSSION_NODE,
                StageEnum.FACT_NODE: StageEnum.FACT_NODE,
                StageEnum.OTHER_NODE: StageEnum.OTHER_NODE,
                StageEnum.BACKTEST_NODE: StageEnum.BACKTEST_NODE,
            }
        )

        graph.add_conditional_edges(
            StageEnum.DISCUSSION_NODE,
            lambda x: x["stage"],
            {
                StageEnum.RISK_NODE: StageEnum.RISK_NODE,
                StageEnum.USER_DATA_NODE: StageEnum.USER_DATA_NODE,
                StageEnum.NEWS_DATA_NODE: StageEnum.NEWS_DATA_NODE,
            }
        )
        graph.add_edge(StageEnum.RISK_NODE, StageEnum.FINALIZER_NODE)
        graph.add_edge(StageEnum.FINALIZER_NODE, END)
        graph.add_edge(StageEnum.FACT_NODE, END)
        graph.add_edge(StageEnum.OTHER_NODE, END)
        graph.add_edge(StageEnum.BACKTEST_NODE, END)

        return graph.compile(checkpointer=self.memory)
    
    def router_node(self, state: State) -> State:
        logging.info("Router node")
        user_input = state.get("message_from_user", "").strip()
        if not user_input:
            return Command(
                goto=END,
                update={"message_to_user": "Пустой запрос.", "stage": END}
            )

        try:
            prompt = ROUTER_PROMPT.format(user_input=user_input)
            response = self.llm.complete(prompt, temperature=0.0, max_tokens=10)
            category = response.strip().lower()

            logging.info(f"Router detected category: {category}")

            if category == "analysis":
                return Command(goto=StageEnum.DISCUSSION_NODE, update={"stage": StageEnum.DISCUSSION_NODE})
            elif category == "fact":
                return Command(goto=StageEnum.FACT_NODE, update={"stage": StageEnum.FACT_NODE})
            elif category == "backtest":
                return Command(goto=StageEnum.BACKTEST_NODE, update={"stage": StageEnum.BACKTEST_NODE})
            else:
                return Command(goto=StageEnum.OTHER_NODE, update={"stage": StageEnum.OTHER_NODE})

        except Exception as e:
            logging.error(f"Ошибка в router_node: {e}")
            return Command(
                goto=StageEnum.OTHER_NODE,
                update={"message_to_user": "Не удалось определить тип запроса."}
            )

    def fact_node(self, state: State) -> State:
        logging.info("Fact node")
        try:
            user_input = state.get("message_from_user", "")
            user_data = state.get("user_data", {})
            news_data = state.get("news_data", {})

            prompt = FACT_NODE_PROMPT.format(
                user_input=user_input,
                user_data=json.dumps(user_data, ensure_ascii=False, indent=2),
                news_data=json.dumps(news_data, ensure_ascii=False, indent=2)
            )

            response = self.llm.complete(prompt, temperature=0.3, max_tokens=500)

            return Command(
                goto=END,
                update={
                    "message_to_user": response,
                    "stage": END
                }
            )
        except Exception as e:
            logging.error(f"Ошибка в fact_node: {e}")
            return Command(
                goto=END,
                update={
                    "message_to_user": "Ошибка при обработке фактического запроса.",
                    "stage": END
                }
            )
        
    def other_node(self, state: State) -> State:
        logging.info("Other node")
        try:
            user_input = state.get("message_from_user", "")

            prompt = OTHER_NODE_PROMPT.format(user_input=user_input)
            response = self.llm.complete(prompt, temperature=0.7, max_tokens=300)

            return Command(
                goto=END,
                update={
                    "message_to_user": response,
                    "stage": END
                }
            )
        except Exception as e:
            logging.error(f"Ошибка в other_node: {e}")
            return Command(
                goto=END,
                update={
                    "message_to_user": "Не удалось обработать запрос.",
                    "stage": END
                }
            )

    def user_data_node(self, state: State) -> State:
        logging.info("User data node")
        try:
            with open("info/user_portfolio.json", "r", encoding="utf-8") as f:
                user_data = json.load(f)
            
            logging.info("User data loaded")
            return Command(
                goto=StageEnum.DISCUSSION_NODE,
                update={
                    "user_data": user_data,
                    "stage": StageEnum.DISCUSSION_NODE
                }
            )

        except Exception as e:
            logging.error(f"Ошибка загрузки портфеля: {e}")
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка загрузки портфеля: {e}"
                }
            )

    def news_data_node(self, state: State) -> State:
        logging.info("News data node")
        try:
            with open("info/sample_news.json", "r", encoding="utf-8") as f:
                news_data = json.load(f)
            
            logging.info("News data loaded")
            return Command(
                goto=StageEnum.DISCUSSION_NODE,
                update={
                    "news_data": news_data,
                    "stage": StageEnum.DISCUSSION_NODE
                }
            )

        except Exception as e:
            logging.error(f"Ошибка загрузки новостей: {e}")
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка загрузки новостей: {e}"
                }
            )
    
    def discussion_node(self, state: State) -> State:
        logging.info("Discussion node")
        try:
            logging.info("Checking user data")
            if not state.get("user_data"):
                return Command(
                    goto=StageEnum.USER_DATA_NODE,
                    update={
                        "stage": StageEnum.USER_DATA_NODE
                    }
                )

            logging.info("Checking news data")
            if not state.get("news_data"):
                return Command(
                    goto=StageEnum.NEWS_DATA_NODE,
                    update={
                        "stage": StageEnum.NEWS_DATA_NODE
                    }
                )
            
            logging.info("🤖 Агенты начинают обсуждение портфеля...")
            
            # Создаем логгер для рассуждений
            logger = ChatLogger('agent_reasoning')
            
            # Передаем логгер в agent_room для рассуждений
            agent_opinions = self.agent_room.discuss_portfolio(
                state["user_data"], 
                state["news_data"],
                logger=logger
            )
            
            logging.info("🔄 АГРЕГАЦИЯ РЕШЕНИЙ АГЕНТОВ")
            logging.info("-" * 40)
            aggregated_decisions = aggregate_agent_opinions(agent_opinions)
            
            logging.info(f"✅ Получено {len(agent_opinions)} мнений от агентов")
            logging.info(f"📊 Агрегировано {len(aggregated_decisions)} решений")
            
            for decision in aggregated_decisions:
                logging.info(
                    f"📋 {decision.ticker}: {decision.final_action} "
                    f"(уверенность: {decision.confidence_score:.1f}, "
                    f"консенсус: {decision.consensus_strength:.1f})"
                )

            analysis_results["agent_opinions"] = agent_opinions
            analysis_results["aggregated_decisions"] = aggregated_decisions

            return Command(
                goto=StageEnum.RISK_NODE,
                update={
                    "agent_opinions": agent_opinions,
                    "aggregated_decisions": aggregated_decisions,
                    "stage": StageEnum.RISK_NODE
                }
            )

        except Exception as e:
            logging.error(f"Ошибка в обсуждении агентов: {e}")
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка в обсуждении агентов: {e}"
                }
            )

    def backtest_node(self, state: State) -> State:
        try:
            # Создаем логгер для бэктеста
            logger = ChatLogger('backtest')
            
            # Загружаем данные портфеля и новостей
            with open("info/user_portfolio.json", "r", encoding="utf-8") as f:
                user_portfolio = json.load(f)
            
            with open("info/sample_news.json", "r", encoding="utf-8") as f:
                news_data = json.load(f)
            
            # Запускаем бэктест
            logger.info("Запускаем бэктест")
            result = self.backtest_engine.run_backtest(3, user_portfolio, news_data, logger)
            logger.info("Пишу результаты бэктеста")
            # Форматируем результаты в markdown таблицу
            markdown_result = self._format_backtest_results(result)

            return Command(
                goto=END,
                update={
                    "message_to_user": markdown_result,
                    "stage": END
                }
            )
        
        except Exception as e:
            logging.error(f"Ошибка в backtest_node: {e}")
            return Command(
                goto=END,
                update={
                    "message_to_user": "Не удалось выполнить бэктест.",
                    "stage": END
                }
            )

    def risk_node(self, state: State) -> State:
        logging.info("Risk node")
        try:
            logging.info("⚠️ Риск-менеджер оценивает риски...")
            
            risk_assessments = []
            aggregated_decisions = state.get("aggregated_decisions", [])
            
            for decision in aggregated_decisions:
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
                
                full_prompt = f"{RISK_MANAGER_PROMPT}\n\n{context}"
                
                try:
                    response = self.llm.complete(full_prompt, temperature=0.3, max_tokens=500)
                    
                    risk_level = self._extract_risk_level(response)
                    risk_factors = self._extract_risk_factors(response)
                    
                    risk_assessments.append(RiskAssessment(
                        ticker=decision.ticker,
                        risk_level=risk_level,
                        risk_factors=risk_factors,
                        recommendations=response
                    ))
                    
                except Exception as e:
                    logging.error(f"Ошибка оценки риска для {decision.ticker}: {e}")
                    risk_assessments.append(RiskAssessment(
                        ticker=decision.ticker,
                        risk_level=5,
                        risk_factors=["Ошибка анализа"],
                        recommendations="Требуется дополнительный анализ"
                    ))
            
            logging.info(f"✅ Оценены риски для {len(risk_assessments)} позиций")
            
            for risk in risk_assessments:
                logging.info(f"⚠️ {risk.ticker}: уровень риска {risk.risk_level}/10")

            analysis_results["risk_assessments"] = risk_assessments

            return Command(
                goto=StageEnum.FINALIZER_NODE,
                update={
                    "risk_assessments": risk_assessments,
                    "stage": StageEnum.FINALIZER_NODE
                }
            )

        except Exception as e:
            logging.error(f"Ошибка в оценке рисков: {e}")
            return Command(
                goto=END,
                update={
                    "stage": END,
                    "message_to_user": f"Ошибка в оценке рисков: {e}"
                }
            )
            
    def finalizer_node(self, state: State) -> State:
        logging.info("Finalizer node")
        try:
            logging.info("📋 Формирование итоговых рекомендаций...")
            
            context = self._build_finalizer_context(state)
            
            full_prompt = f"{PORTFOLIO_AGENT_PROMPT}\n\n{context}"
            
            final_recommendations = self.llm.complete(full_prompt, temperature=0.5, max_tokens=2000)
            
            logging.info("✅ Итоговые рекомендации сформированы")

            analysis_results["final_recommendations"] = final_recommendations

            return Command(
                goto=END,
                update={
                    "final_recommendations": final_recommendations,
                    "message_to_user": final_recommendations,
                    "stage": END
                }
            )

        except Exception as e:
            logging.error(f"Ошибка формирования рекомендаций: {e}")
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
        return 5 

    def _extract_risk_factors(self, response: str) -> list:
        """Извлекает факторы риска из ответа"""
        factors = []
        lines = response.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['риск', 'опасность', 'угроза']):
                factors.append(line.strip())
        return factors[:3] 

    def _build_finalizer_context(self, state: State) -> str:
        """Строит контекст для финализатора"""
        context = "АНАЛИЗ ПОРТФЕЛЯ\n\n"
        
        user_data = state.get("user_data", {})
        if user_data:
            context += "Текущий портфель:\n"
            for ticker, position in user_data.items():
                context += f"- {ticker}: {position.get('quantity', 0)} акций, "
                context += f"средняя цена: {position.get('avg_price', 0)} руб.\n"
            context += "\n"
        
        aggregated_decisions = state.get("aggregated_decisions", [])
        if aggregated_decisions:
            context += "Рекомендации агентов:\n"
            for decision in aggregated_decisions:
                context += f"- {decision.ticker}: {decision.final_action} "
                context += f"(уверенность: {decision.confidence_score:.1f}, "
                context += f"консенсус: {decision.consensus_strength:.1f})\n"
            context += "\n"
        
        risk_assessments = state.get("risk_assessments", [])
        if risk_assessments:
            context += "Оценка рисков:\n"
            for risk in risk_assessments:
                context += f"- {risk.ticker}: уровень риска {risk.risk_level}/10\n"
            context += "\n"
        
        context += "Сформируй четкие рекомендации по управлению портфелем."
        
        return context
    
    def _format_backtest_results(self, result) -> str:
        """Форматирует результаты бэктеста в markdown таблицу"""
        # Заголовок
        markdown = f"# 📊 Результаты бэктеста\n\n"
        
        # Общая информация
        markdown += f"**Период:** {result.start_date.strftime('%d.%m.%Y')} - {result.end_date.strftime('%d.%m.%Y')}\n\n"
        markdown += f"**Начальная стоимость портфеля:** {result.initial_portfolio_value:,.2f} ₽\n\n"
        markdown += f"**Финальная стоимость портфеля:** {result.final_portfolio_value:,.2f} ₽\n\n"
        markdown += f"**Общий PnL:** {result.total_pnl:,.2f} ₽\n\n"
        markdown += f"**Общая доходность:** {result.total_return_pct:+.2f}%\n\n"
        
        # Производительность по тикерам
        if result.ticker_performance:
            markdown += "## 📈 Производительность по тикерам\n\n"
            markdown += "| Тикер | PnL (₽) | Доходность (%) | Уверенность |\n"
            markdown += "|-------|---------|----------------|-------------|\n"
            
            for ticker, perf in result.ticker_performance.items():
                markdown += f"| {ticker} | {perf['total_pnl']:,.2f} | {perf['total_return_pct']:+.2f} | {perf['avg_confidence']:.1f}/10 |\n"
            
            markdown += "\n"
        
        # Ежедневные результаты
        if result.daily_results:
            markdown += "## 📅 Ежедневные результаты\n\n"
            markdown += "| Дата | Тикер | Открытие | Закрытие | Изменение | Сигнал | Уверенность | PnL дня |\n"
            markdown += "|------|-------|----------|----------|-----------|--------|-------------|----------|\n"
            
            for day in result.daily_results:
                price_change = day.close_price - day.open_price
                price_change_pct = (price_change / day.open_price) * 100 if day.open_price > 0 else 0
                
                # Эмодзи для сигнала
                signal_emoji = {
                    'BUY': '🟢',
                    'SELL': '🔴', 
                    'HOLD': '🟡'
                }.get(day.signal, '⚪')
                
                markdown += f"| {day.date.strftime('%d.%m.%Y')} | {day.ticker} | {day.open_price:.2f} | {day.close_price:.2f} | {price_change_pct:+.2f}% | {signal_emoji} {day.signal} | {day.confidence:.1f}/10 | {day.daily_pnl:,.2f} |\n"
            
            markdown += "\n"
        
        # Итоговая статистика
        markdown += "## 🎯 Итоговая статистика\n\n"
        markdown += f"- **Общее количество дней:** {len(result.daily_results)}\n"
        markdown += f"- **Средний PnL в день:** {result.total_pnl / len(result.daily_results):,.2f} ₽\n"
        markdown += f"- **Лучший день:** {max(result.daily_results, key=lambda x: x.daily_pnl).date.strftime('%d.%m.%Y')} ({max(result.daily_results, key=lambda x: x.daily_pnl).daily_pnl:,.2f} ₽)\n"
        markdown += f"- **Худший день:** {min(result.daily_results, key=lambda x: x.daily_pnl).date.strftime('%d.%m.%Y')} ({min(result.daily_results, key=lambda x: x.daily_pnl).daily_pnl:,.2f} ₽)\n"
        
        return markdown

def get_analysis_results():
    """Возвращает результаты анализа"""
    return analysis_results

