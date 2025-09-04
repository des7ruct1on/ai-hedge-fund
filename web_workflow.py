"""
Веб-версия workflow с сохранением результатов в глобальные переменные
"""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from dateutil.relativedelta import relativedelta
import pandas as pd
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
from moex_parser import MoexISS
from risk_tools import compute_risk_features

logging.basicConfig(
    filename='web_workflow.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

web_analysis_results = {
    "agent_opinions": [],
    "aggregated_decisions": [],
    "risk_assessments": [],
    "final_recommendations": ""
}

moex_equity = MoexISS(engine="stock", market="shares")  # акции
moex_index  = MoexISS(engine="stock", market="index")   # индексы (IMOEX, RTSI, IMOEXTR и т.д.)


class WebGraph(StateGraph):
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

        return graph.compile(checkpointer=self.memory)

    def user_data_node(self, state: State) -> State:
        logging.info("User data node")
        try:
            with open("user_portfolio.json", "r", encoding="utf-8") as f:
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
            with open("sample_news.json", "r", encoding="utf-8") as f:
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
            agent_opinions = self.agent_room.discuss_portfolio(
                state["user_data"], 
                state["news_data"]
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

            web_analysis_results["agent_opinions"] = agent_opinions
            web_analysis_results["aggregated_decisions"] = aggregated_decisions

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
                
    def risk_node(self, state: State) -> State:
        logging.info("Risk node")
        try:
            logging.info("⚠️ Риск-менеджер оценивает риски...")
            
            risk_assessments = []
            aggregated_decisions = state.get("aggregated_decisions", [])

            start_date, end_date = self.get_range()
            
            for decision in aggregated_decisions:

                risk_features_json = self._build_risk_features_json(decision.ticker, start_date, end_date)

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
                
                full_prompt = (
                f"{RISK_MANAGER_PROMPT}\n\n"
                f"[QUANT_RISK_CONTEXT]\n{risk_features_json}\n\n"
                f"{context}"
                )

                print(full_prompt)
                
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

            web_analysis_results["risk_assessments"] = risk_assessments

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

            web_analysis_results["final_recommendations"] = final_recommendations

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
    

    def get_range(self, months_back: int = 1, tz: str = 'Europe/Moscow') -> tuple[str, str]:
        
        today_local = datetime.now(ZoneInfo(tz)).date()
        start_date = (today_local - relativedelta(months=months_back)).isoformat()
        end_date = today_local.isoformat()
        return start_date, end_date
    
    def _bench_close_series(self, bench_secid: str, start: str, end: str) -> pd.Series | None:
        
        c = moex_index.get_candles(bench_secid, start, end, interval=24)
        if c is None or c.empty:
            return None
        s = c[["end", "close"]].copy()
        s["date"] = pd.to_datetime(s["end"]).dt.date
        return s.set_index("date")["close"].astype(float).sort_index()

    def _build_risk_features_json(self, secid: str, start: str, end: str) -> str:
        # базовый дневной ряд закрытий (LEGALCLOSEPRICE/CLOSE)
        px = moex_equity.get_daily_close_series(secid, start, end, board="TQBR")
        # дневные свечи (OHLC) — для Parkinson/Garman–Klass
        ohlc = moex_equity.get_candles(secid, start, end, interval=24)
        # бенчмарк
        bench = self._bench_close_series("IMOEX", start, end)
        rf = compute_risk_features(px_close_daily=px, bench_close_daily=bench, ohlc_daily=ohlc, stl_period=5)
        return json.dumps(rf.__dict__, ensure_ascii=False, default=float)


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

def get_web_analysis_results():
    """Возвращает результаты анализа для веб-интерфейса"""
    return web_analysis_results
