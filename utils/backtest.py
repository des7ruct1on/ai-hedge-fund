"""
Модуль для бэктестинга торговых стратегий на основе решений агентов
"""
import json
import datetime as dt
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from .utils import moex_candles_by_date
from .investor_agents import InvestorAgentRoom
from .models import AgentOpinion, AggregatedDecision
from .utils import aggregate_agent_opinions



@dataclass
class BacktestPosition:
    """Позиция в портфеле для бэктеста"""
    ticker: str
    quantity: int
    avg_price: float
    current_price: float = 0.0
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_price
    
    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis


@dataclass
class BacktestDay:
    """Результат одного дня бэктеста"""
    date: dt.date
    ticker: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: int
    signal: str  # BUY/SELL/HOLD
    confidence: float
    position_before: BacktestPosition
    position_after: BacktestPosition
    daily_pnl: float
    cumulative_pnl: float


@dataclass
class BacktestResult:
    """Итоговый результат бэктеста"""
    start_date: dt.date
    end_date: dt.date
    initial_portfolio_value: float
    final_portfolio_value: float
    total_pnl: float
    total_return_pct: float
    daily_results: List[BacktestDay]
    ticker_performance: Dict[str, Dict[str, float]]


class BacktestEngine:
    """Движок для бэктестинга торговых стратегий"""
    
    def __init__(self, llm, initial_cash: float = 1000000.0):
        self.llm = llm
        self.initial_cash = initial_cash
        self.agent_room = InvestorAgentRoom(llm)
    
    def run_backtest(
        self, 
        days: int, 
        user_portfolio: Dict[str, Any],
        news_data: List[Dict[str, Any]]
    ) -> BacktestResult:
        """
        Запускает бэктест на указанное количество дней
        
        Args:
            days: количество дней для бэктеста
            user_portfolio: начальный портфель пользователя
            news_data: новости для анализа
            
        Returns:
            BacktestResult с результатами бэктеста
        """
        end_date = dt.date.today()
        start_date = end_date - dt.timedelta(days=days)
        
        print(f"🚀 Запуск бэктеста с {start_date} по {end_date} ({days} дней)")
        
        # Получаем список тикеров из портфеля
        tickers = list(user_portfolio.keys())
        if not tickers:
            raise ValueError("Портфель пуст - нет тикеров для бэктеста")
        
        print(f"📊 Анализируем {len(tickers)} тикеров: {', '.join(tickers)}")
        
        # Загружаем исторические данные для всех тикеров
        historical_data = self._load_historical_data(tickers, start_date, end_date)
        
        # Инициализируем портфель
        portfolio = self._initialize_portfolio(user_portfolio, historical_data, start_date)
        
        # Вычисляем начальную стоимость портфеля
        initial_value = sum(pos.market_value for pos in portfolio.values())
        
        daily_results = []
        cumulative_pnl = 0.0
        
        # Проходим по каждому дню
        current_date = start_date
        while current_date <= end_date:
            print(f"📅 Обрабатываем день: {current_date}")
            
            # Получаем решения агентов для текущего дня
            day_decisions = self._get_day_decisions(
                current_date, portfolio, news_data, historical_data
            )
            
            # Применяем решения и обновляем портфель
            day_pnl = self._apply_decisions(
                current_date, day_decisions, portfolio, historical_data
            )
            
            cumulative_pnl += day_pnl
            
            # Сохраняем результаты дня
            for ticker in tickers:
                if ticker in historical_data and current_date in historical_data[ticker]:
                    candle = historical_data[ticker][current_date]
                    decision = day_decisions.get(ticker)
                    
                    if decision and ticker in portfolio:
                        daily_results.append(BacktestDay(
                            date=current_date,
                            ticker=ticker,
                            open_price=candle['open'],
                            close_price=candle['close'],
                            high_price=candle['high'],
                            low_price=candle['low'],
                            volume=candle['volume'],
                            signal=decision.final_action,
                            confidence=decision.confidence_score,
                            position_before=portfolio[ticker],
                            position_after=portfolio[ticker],
                            daily_pnl=day_pnl / len(tickers),  # Распределяем PnL по тикерам
                            cumulative_pnl=cumulative_pnl
                        ))
            
            current_date += dt.timedelta(days=1)
        
        # Вычисляем финальную стоимость портфеля
        final_value = sum(pos.market_value for pos in portfolio.values())
        total_pnl = final_value - initial_value
        total_return_pct = (total_pnl / initial_value) * 100 if initial_value > 0 else 0
        
        # Анализируем производительность по тикерам
        ticker_performance = self._analyze_ticker_performance(daily_results)
        
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_portfolio_value=initial_value,
            final_portfolio_value=final_value,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            daily_results=daily_results,
            ticker_performance=ticker_performance
        )
    
    def _load_historical_data(
        self, 
        tickers: List[str], 
        start_date: dt.date, 
        end_date: dt.date
    ) -> Dict[str, Dict[dt.date, Dict[str, float]]]:
        """Загружает исторические данные с MOEX"""
        historical_data = {}
        
        for ticker in tickers:
            print(f"📈 Загружаем данные для {ticker}...")
            candles = moex_candles_by_date(ticker, start_date, end_date)
            
            ticker_data = {}
            for candle in candles:
                # Парсим дату из формата MOEX
                date_str = candle['begin'][:10]  # YYYY-MM-DD
                date = dt.datetime.strptime(date_str, '%Y-%m-%d').date()
                
                ticker_data[date] = {
                    'open': float(candle['open']),
                    'high': float(candle['high']),
                    'low': float(candle['low']),
                    'close': float(candle['close']),
                    'volume': int(candle['volume'])
                }
            
            historical_data[ticker] = ticker_data
            print(f"✅ Загружено {len(ticker_data)} дней данных для {ticker}")
        
        return historical_data
    
    def _initialize_portfolio(
        self, 
        user_portfolio: Dict[str, Any], 
        historical_data: Dict[str, Dict[dt.date, Dict[str, float]]],
        start_date: dt.date
    ) -> Dict[str, BacktestPosition]:
        """Инициализирует портфель для бэктеста"""
        portfolio = {}
        
        for ticker, position_data in user_portfolio.items():
            if ticker in historical_data and start_date in historical_data[ticker]:
                current_price = historical_data[ticker][start_date]['close']
                
                portfolio[ticker] = BacktestPosition(
                    ticker=ticker,
                    quantity=position_data.get('quantity', 0),
                    avg_price=position_data.get('avg_price', current_price),
                    current_price=current_price
                )
        
        return portfolio
    
    def _get_day_decisions(
        self,
        current_date: dt.date,
        portfolio: Dict[str, BacktestPosition],
        news_data: List[Dict[str, Any]],
        historical_data: Dict[str, Dict[dt.date, Dict[str, float]]]
    ) -> Dict[str, AggregatedDecision]:
        """Получает решения агентов для конкретного дня"""
        # Создаем "текущий" портфель для агентов
        current_portfolio = {}
        for ticker, pos in portfolio.items():
            current_portfolio[ticker] = {
                'quantity': pos.quantity,
                'avg_price': pos.avg_price
            }
        
        # Получаем мнения агентов
        agent_opinions = self.agent_room.discuss_portfolio(current_portfolio, news_data)
        
        # Агрегируем решения
        aggregated_decisions = aggregate_agent_opinions(agent_opinions)
        
        # Преобразуем в словарь для удобства
        decisions_dict = {decision.ticker: decision for decision in aggregated_decisions}
        
        return decisions_dict
    
    def _apply_decisions(
        self,
        current_date: dt.date,
        decisions: Dict[str, AggregatedDecision],
        portfolio: Dict[str, BacktestPosition],
        historical_data: Dict[str, Dict[dt.date, Dict[str, float]]]
    ) -> float:
        """Применяет решения агентов и обновляет портфель"""
        total_pnl = 0.0
        
        for ticker, decision in decisions.items():
            if ticker not in portfolio or ticker not in historical_data:
                continue
            
            if current_date not in historical_data[ticker]:
                continue
            
            current_price = historical_data[ticker][current_date]['close']
            position = portfolio[ticker]
            
            # Обновляем текущую цену
            position.current_price = current_price
            
            # Вычисляем PnL для текущей позиции
            position_pnl = position.pnl
            total_pnl += position_pnl
            
            # Здесь можно добавить логику исполнения сделок
            # Пока просто обновляем цены и фиксируем PnL
        
        return total_pnl
    
    def _analyze_ticker_performance(
        self, 
        daily_results: List[BacktestDay]
    ) -> Dict[str, Dict[str, float]]:
        """Анализирует производительность по тикерам"""
        ticker_performance = {}
        
        for result in daily_results:
            ticker = result.ticker
            if ticker not in ticker_performance:
                ticker_performance[ticker] = {
                    'total_pnl': 0.0,
                    'total_return_pct': 0.0,
                    'max_drawdown': 0.0,
                    'win_rate': 0.0,
                    'avg_confidence': 0.0
                }
            
            ticker_performance[ticker]['total_pnl'] += result.daily_pnl
            ticker_performance[ticker]['avg_confidence'] += result.confidence
        
        # Нормализуем средние значения
        for ticker in ticker_performance:
            ticker_data = ticker_performance[ticker]
            ticker_days = [r for r in daily_results if r.ticker == ticker]
            
            if ticker_days:
                ticker_data['avg_confidence'] /= len(ticker_days)
                
                # Вычисляем общую доходность
                initial_value = ticker_days[0].position_before.market_value
                if initial_value > 0:
                    ticker_data['total_return_pct'] = (ticker_data['total_pnl'] / initial_value) * 100
        
        return ticker_performance
