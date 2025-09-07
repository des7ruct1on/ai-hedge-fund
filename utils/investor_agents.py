import json
import re
from typing import List, Dict
from .models import AgentOpinion
from .prompts import PROMPTS
from llm.cloudrugpt import CloudRuGPT
from ui.server.logger import ChatLogger

logger = ChatLogger("main")

class InvestorAgent:
    def __init__(self, name: str, llm: CloudRuGPT):
        self.name = name
        self.llm = llm
        self.prompt = PROMPTS.get(name, "")
    
    def analyze_ticker(self, ticker: str, news_data: List[Dict], user_portfolio: Dict) -> AgentOpinion:
        """Анализирует конкретный тикер и возвращает мнение агента"""
        
        print(f"\n💭 {self.name} анализирует {ticker}...")
        logger.log_read_message(f"💭 {self.name}", f"анализирует {ticker}...")
        context = self._build_context(ticker, news_data, user_portfolio)
        
        full_prompt = f"{self.prompt}\n\n{context}"
        
        try:
            response = self.llm.complete(full_prompt, temperature=0.7, max_tokens=1000)
            
            print(f"📝 {self.name} говорит:")
            print(f"   {response.strip()}")
            logger.log_read_message(f"📝 {self.name} говорит:", f"   {response.strip()}")
            opinion = self._parse_agent_response(ticker, response)
            
            print(f"✅ {self.name} решает: {opinion.action} {ticker} (уверенность: {opinion.confidence}/10)")
            logger.log_read_message(f"✅ {self.name} решает:", f"{opinion.action} {ticker} (уверенность: {opinion.confidence}/10)")
            
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
    
    def _build_context(self, ticker: str, news_data: List[Dict], user_portfolio: Dict) -> str:
        """Строит контекст для анализа"""
        context = f"Анализируй акцию {ticker}.\n\n"
        
        ticker_news = [news for news in news_data if news.get('ticker') == ticker]
        if ticker_news:
            context += "Новости по акции:\n"
            for news in ticker_news[:5]:  
                context += f"- {news.get('title', '')}: {news.get('summary', '')}\n"
            context += "\n"
        
        if ticker in user_portfolio:
            position = user_portfolio[ticker]
            context += f"Текущая позиция в портфеле: {position.get('quantity', 0)} акций, "
            context += f"средняя цена покупки: {position.get('avg_price', 0)} руб.\n\n"
        
        context += "Дай свое мнение в формате:\n"
        context += "ДЕЙСТВИЕ: [КУПИТЬ/ПРОДАТЬ/ДЕРЖАТЬ]\n"
        context += "УВЕРЕННОСТЬ: [1-10]\n"
        context += "ОБОСНОВАНИЕ: [подробное объяснение решения]"
        
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
    
    def discuss_portfolio(self, user_portfolio: Dict, news_data: List[Dict], logger=None) -> List[AgentOpinion]:
        """Проводит обсуждение портфеля всеми агентами"""
        all_opinions = []
        
        tickers = set()
        if user_portfolio:
            tickers.update(user_portfolio.keys())
        
        for news in news_data:
            if news.get('ticker'):
                tickers.add(news['ticker'])
        
        logger.log_read_message("", f"\n🏛️ НАЧИНАЕТСЯ СОВЕЩАНИЕ ИНВЕСТИЦИОННОГО КОМИТЕТА")
        logger.log_read_message("", f"📊 Анализируем {len(tickers)} тикеров: {', '.join(sorted(tickers))}")
        logger.log_read_message("", f"👥 Участники: {', '.join(self.agents.keys())}")
        print("=" * 60)
        
        for i, ticker in enumerate(tickers, 1):
            logger.log_read_message("", f"\n📈 ОБСУЖДЕНИЕ ТИКЕРА {i}/{len(tickers)}: {ticker}")
            print("-" * 40)
            
            for agent_name, agent in self.agents.items():
                # Передаем логгер агенту для рассуждений
                opinion = agent.analyze_ticker(ticker, news_data, user_portfolio)
                all_opinions.append(opinion)
            
            print(f"🏁 Обсуждение {ticker} завершено")
        
        logger.log_read_message("", f"\n🎯 СОВЕЩАНИЕ ЗАВЕРШЕНО")
        logger.log_read_message("", f"📋 Получено {len(all_opinions)} мнений от агентов")
        print("=" * 60)
        
        return all_opinions
