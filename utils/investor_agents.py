import json
import re
from typing import List, Dict, Optional
from .models import AgentOpinion
from .prompts import PROMPTS
from llm.cloudrugpt import CloudRuGPT
from ui.server.logger import ChatLogger
from .moex_parcer import MoexISS
from datetime import date, timedelta, datetime
from langchain_core.prompts import ChatPromptTemplate

logger = ChatLogger("main")

class InvestorAgent:
    def __init__(self, name: str, llm: CloudRuGPT):
        self.name = name
        self.llm = llm
        self.prompt = PROMPTS.get(name, "")
    
    def analyze_ticker(
        self,
        ticker: str,
        news_data: List[Dict],
        user_portfolio: Dict,
        metrics=None,
        use_moex: bool = True,
        market_ticker: Optional[str] = "IMOEX",
        interval: int = 24,
        days: int = 365
    ) -> AgentOpinion:
        """Анализирует конкретный тикер и возвращает мнение агента с учетом метрик."""
        print(f"\n💭 {self.name} анализирует {ticker}...")
        logger.log_read_message(f"💭 {self.name}", f"анализирует {ticker}...")

        if metrics is None and use_moex:
            try:
                moex = MoexISS()

                # Вычисляем даты для запроса свечей
                end_date = datetime.now().strftime("%Y-%m-%d")
                start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

                # Получаем свечи для основного тикера
                candles = moex.get_candles(
                    secid=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    interval=24  
                )


                metrics = moex.metrics_from_moex_candles(
                    candles=candles,
                    price_field="close",
                    market_price_field="close",
                    rf=0.0,
                    days_per_year=252,
                    alpha=0.05
                )
                print("📊 Метрики рассчитаны по данным MoexISS")

            except Exception as e:
                print(f"⚠️ Ошибка при загрузке данных через MoexISS: {e}")

        # Формируем контекст
        context = self._build_context(ticker, news_data, user_portfolio)
        metrics_str = "Метрики отсутствуют"
        if metrics:
            metrics_str = self._format_metrics(metrics)
            context += f"\n\n📊 Метрики тикера {ticker}:\n{metrics_str}"


        prompt = ChatPromptTemplate.from_template(self.prompt)
        chain = prompt | self.llm

        # Запрашиваем LLM
        try:
            response = chain.invoke({"context": context, "metrics": metrics_str})
            print(f"📝 {self.name} говорит:")
            print(f"   {response.content.strip()}")
            logger.log_read_message(f"📝 {self.name} говорит:", f"   {response.content.strip()}")

            opinion = self._parse_agent_response(ticker, response.content)
            print(f"✅ {self.name} решает: {opinion.action} {ticker} (уверенность: {opinion.confidence}/10)")
            logger.log_read_message(
                f"✅ {self.name} решает:",
                f"{opinion.action} {ticker} (уверенность: {opinion.confidence}/10)"
            )
            return opinion

        except Exception as e:
            print(f"❌ Ошибка при анализе {ticker} агентом {self.name}: {e}")
            return AgentOpinion(
                agent_name=self.name,
                ticker=ticker,
                action="HOLD",
                confidence=1,
                reasoning=f"Ошибка анализа: {e}"
            )

    def _format_metrics(self, metrics) -> str:
        """Форматирует метрики из MetricsResult в строку для включения в контекст."""
        if not metrics:
            return "Метрики отсутствуют."

        metrics_lines = []
        # Основные метрики
        metrics_lines.append(f"Общая доходность: {metrics.total_return:.2%}")
        metrics_lines.append(f"CAGR (среднегодовая доходность): {metrics.cagr:.2%}")
        metrics_lines.append(f"Годовая волатильность: {metrics.annualized_vol:.2%}")
        metrics_lines.append(f"Коэффициент Шарпа: {metrics.sharpe:.2f}")
        metrics_lines.append(f"Коэффициент Сортино: {metrics.sortino:.2f}")
        metrics_lines.append(f"Максимальная просадка: {metrics.max_drawdown:.2%}")
        if metrics.max_drawdown_start and metrics.max_drawdown_end:
            metrics_lines.append(
                f"Период максимальной просадки: {metrics.max_drawdown_start.strftime('%Y-%m-%d')} - "
                f"{metrics.max_drawdown_end.strftime('%Y-%m-%d')}"
            )
        metrics_lines.append(f"Коэффициент Калмара: {metrics.calmar:.2f}")
        metrics_lines.append(f"Доля выигрышных сделок: {metrics.win_rate:.2%}")
        metrics_lines.append(f"Средняя прибыль по выигрышным сделкам: {metrics.avg_win:.2%}")
        metrics_lines.append(f"Средний убыток по проигрышным сделкам: {metrics.avg_loss:.2%}")
        metrics_lines.append(f"Фактор прибыли: {metrics.profit_factor:.2f}")
        metrics_lines.append(f"Асимметрия (Skewness): {metrics.skewness:.2f}")
        metrics_lines.append(f"Куртозис: {metrics.kurtosis:.2f}")
        metrics_lines.append(f"CVaR: {metrics.cvar:.2%}")

        # Метрики, зависящие от бенчмарка
        if metrics.alpha is not None:
            metrics_lines.append(f"Альфа: {metrics.alpha:.2f}")
        if metrics.beta is not None:
            metrics_lines.append(f"Бета: {metrics.beta:.2f}")

        # Дополнительные метрики
        if metrics.additional:
            metrics_lines.append("\nДополнительные метрики:")
            for key, value in metrics.additional.items():
                metrics_lines.append(f"{key}: {value:.2f}")

        return "\n".join(metrics_lines) if metrics_lines else "Метрики не содержат значимых данных."
        
    def _build_context(self, ticker: str, news_data: List[Dict], user_portfolio: Dict) -> str:
        """Строит контекст для анализа"""
        context = f"Анализируй акцию {ticker}.\n\n"
        
        ticker_news = [news for news in news_data if news.get('ticker') == ticker]
        if ticker_news:
            context += "Новости по акции:\n"
            for news in ticker_news[:5]:  
                context += f"- {news.get('title', '')}: {news.get('summary', '')}, {news.get('news', '')}\n"
                context += f"- Сентимент: {news.get('sentiment', '')}, значимость: {news.get('significance', '')}\n"
            context += "\n"
        
        if ticker in user_portfolio:
            position = user_portfolio[ticker]
            context += f"Текущая позиция в портфеле: {position.get('quantity', 0)} акций, "
            context += f"средняя цена покупки: {position.get('avg_price', 0)} руб.\n\n"
        
        context += "Дай свое мнение в формате:\n"
        context += "ДЕЙСТВИЕ: [КУПИТЬ/ПРОДАТЬ/ДЕРЖАТЬ]\n"
        context += "УВЕРЕННОСТЬ: [1-10]\n"
        context += "ОБОСНОВАНИЕ: [подробное объяснение решения]"
        # logger.message("investor_agents", f"{context}")
        return context
    
    def _parse_agent_response(self, ticker: str, response: str) -> AgentOpinion:
        """Парсит ответ агента и извлекает структурированную информацию"""

        action = "HOLD"  
        response_upper = response.upper()
        
        if "КУПИТЬ" in response_upper or "BUY" in response_upper:
            action = "BUY"
        elif "ПРОДАТЬ" in response_upper or "SELL" in response_upper:
            action = "SELL"
        elif "ДЕРЖАТЬ" in response_upper or "HOLD" in response_upper:
            action = "HOLD"
        
        confidence = 5 
        numbers = re.findall(r'\b(\d+)\b', response)
        if numbers:
            for num in numbers:
                num_int = int(num)
                if 1 <= num_int <= 10:
                    confidence = num_int
                    break
        
        reasoning = response.strip()
        
        return AgentOpinion(
            agent_name=self.name,
            ticker=ticker,
            action=action,
            confidence=confidence,
            reasoning=reasoning
        )


class InvestorAgentRoom:
    def __init__(self, llm: CloudRuGPT):
        self.llm = llm
        self.agents = {
            "Buffett": InvestorAgent("Buffett", llm),
            "Trump": InvestorAgent("Trump", llm),
            "Dalio": InvestorAgent("Dalio", llm)
        }
    
    def discuss_portfolio(self, user_portfolio: Dict, news_data: List[Dict], metrics: Dict = None, logger=None) -> List[AgentOpinion]:
        """Проводит обсуждение портфеля всеми агентами с учетом метрик."""
        all_opinions = []
        
        tickers = set()
        if user_portfolio:
            # Игнорируем специальные ключи, такие как __cash__
            tickers.update([t for t in user_portfolio.keys() if not str(t).startswith("__")])
        
        for news in news_data:
            if news.get('ticker'):
                tickers.add(news['ticker'])
        
        logger.log_read_message("", f"\n🏛️ НАЧИНАЕТСЯ СОВЕЩАНИЕ ИНВЕСТИЦИОННОГО КОМИТЕТА")
        logger.log_read_message("", f"📊 Анализируем {len(tickers)} тикеров: {', '.join(sorted(tickers))}")
        logger.log_read_message("", f"👥 Участники: {', '.join(self.agents.keys())}")
        print("=" * 60)
        
        for i, ticker in enumerate(tickers, 1):
            logger.log_read_message("", f"\n📈 ОБСУЖДЕНИЕ ТИКЕРА {i}/{len(tickers)}: {ticker}")
            # logger.message("investor_agents", f"📈 ОБСУЖДЕНИЕ ТИКЕРА {i}/{len(tickers)}: {ticker}")
            print("-" * 40)
            
            # Получаем метрики для текущего тикера, если они есть
            ticker_metrics = metrics.get(ticker) if metrics else None
            if ticker_metrics:
                logger.log_read_message("", f"📊 Метрики для {ticker}: {ticker_metrics}")
                # logger.message("investor_agents", f"📊 Метрики для {ticker}: {ticker_metrics}")
            
            for agent_name, agent in self.agents.items():
                opinion = agent.analyze_ticker(ticker, news_data, user_portfolio, metrics=ticker_metrics)
                # logger.message("investor_agents", f"💭 {agent_name} говорит: {opinion}")
                all_opinions.append(opinion)
            
            print(f"🏁 Обсуждение {ticker} завершено")
        
        logger.log_read_message("", f"\n🎯 СОВЕЩАНИЕ ЗАВЕРШЕНО")
        logger.log_read_message("", f"📋 Получено {len(all_opinions)} мнений от агентов")
        print("=" * 60)
        
        return all_opinions