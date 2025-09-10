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
class Trade:
    """Сделка в бэктесте"""
    date: dt.date
    ticker: str
    action: str  # BUY/SELL
    quantity: int
    price: float
    value: float  # quantity * price
    commission: float = 0.0  # комиссия
    
    @property
    def net_value(self) -> float:
        return self.value - self.commission


class TradingEngine:
    """Движок для исполнения торговых решений"""
    
    def __init__(self, initial_cash: float = 1000000.0, commission_rate: float = 0.001):
        self.initial_cash = initial_cash
        self.current_cash = initial_cash
        self.commission_rate = commission_rate
        self.positions: Dict[str, BacktestPosition] = {}
        self.trades: List[Trade] = []
    
    def initialize_portfolio(self, user_portfolio: Dict[str, Any], historical_data: Dict, start_date: dt.date) -> None:
        """Инициализирует портфель из пользовательских данных"""
        self.positions = {}
        
        for ticker, position_data in user_portfolio.items():
            if ticker in historical_data and start_date in historical_data[ticker]:
                current_price = historical_data[ticker][start_date]['close']
                
                self.positions[ticker] = BacktestPosition(
                    ticker=ticker,
                    quantity=position_data.get('quantity', 0),
                    avg_price=position_data.get('avg_price', current_price),
                    current_price=current_price
                )
    
    def update_prices(self, current_date: dt.date, historical_data: Dict) -> None:
        """Обновляет текущие цены всех позиций"""
        for ticker, position in self.positions.items():
            if ticker in historical_data and current_date in historical_data[ticker]:
                position.current_price = historical_data[ticker][current_date]['close']
    
    def calculate_position_size(self, ticker: str, action: str, confidence: float, current_price: float) -> int:
        """Вычисляет размер позиции на основе уверенности агента и доступных средств"""
        if action not in ['BUY', 'SELL']:
            return 0
        
        # Базовый размер позиции как процент от портфеля
        base_position_pct = 0.1  # 10% от портфеля на одну позицию
        confidence_multiplier = confidence / 10.0  # от 0.1 до 1.0
        
        total_portfolio_value = self.get_total_portfolio_value()
        target_position_value = total_portfolio_value * base_position_pct * confidence_multiplier
        
        if action == 'BUY':
            # Ограничиваем размер покупки доступными средствами
            max_affordable = self.current_cash * 0.95  # оставляем 5% на комиссии
            target_position_value = min(target_position_value, max_affordable)
            quantity = int(target_position_value / current_price) if current_price > 0 else 0
        else:  # SELL
            # Продаем весь объем позиции или часть
            current_position = self.positions.get(ticker)
            if current_position and current_position.quantity > 0:
                # Продаем от 25% до 100% позиции в зависимости от уверенности
                sell_pct = 0.25 + (confidence_multiplier * 0.75)  # от 25% до 100%
                quantity = int(current_position.quantity * sell_pct)
            else:
                quantity = 0
        
        return max(0, quantity)
    
    def execute_trades(self, current_date: dt.date, decisions: Dict[str, AggregatedDecision], historical_data: Dict) -> List[Trade]:
        """Исполняет торговые решения"""
        executed_trades = []

        # Разделяем решения: сначала выполняем продажи, затем покупки, чтобы покупки могли
        # финансироваться за счет выручки от продаж в тот же день
        sell_first: Dict[str, AggregatedDecision] = {}
        buy_later: Dict[str, AggregatedDecision] = {}

        for ticker, decision in decisions.items():
            action = decision.final_action
            if action == 'SELL':
                sell_first[ticker] = decision
            elif action == 'BUY':
                buy_later[ticker] = decision

        def process(decisions_batch: Dict[str, AggregatedDecision]) -> None:
            for ticker, decision in decisions_batch.items():
                if ticker not in historical_data or current_date not in historical_data[ticker]:
                    continue
                current_price = historical_data[ticker][current_date]['close']
                action = decision.final_action
                confidence = decision.confidence_score
                if action not in ['BUY', 'SELL']:
                    continue
                quantity = self.calculate_position_size(ticker, action, confidence, current_price)
                if quantity <= 0:
                    continue
                trade = self._execute_trade(current_date, ticker, action, quantity, current_price)
                if trade:
                    executed_trades.append(trade)

        # Сначала SELL, потом BUY (расчет количества для BUY делается уже после обновления self.current_cash после SELL)
        process(sell_first)
        process(buy_later)

        return executed_trades
    
    def _execute_trade(self, date: dt.date, ticker: str, action: str, quantity: int, price: float) -> Optional[Trade]:
        """Исполняет одну сделку"""
        value = quantity * price
        commission = value * self.commission_rate
        net_value = value + commission  # для покупки добавляем комиссию, для продажи вычитаем
        
        if action == 'BUY':
            if self.current_cash < net_value:
                # Недостаточно средств
                return None
            
            # Создаем или обновляем позицию
            if ticker not in self.positions:
                self.positions[ticker] = BacktestPosition(
                    ticker=ticker, quantity=0, avg_price=0.0, current_price=price
                )
            
            self.positions[ticker].add_shares(quantity, price)
            self.current_cash -= net_value
            
        elif action == 'SELL':
            if ticker not in self.positions or self.positions[ticker].quantity < quantity:
                # Недостаточно акций для продажи
                return None
            
            self.positions[ticker].remove_shares(quantity)
            self.current_cash += value - commission  # вычитаем комиссию из выручки
        
        # Создаем запись о сделке
        trade = Trade(
            date=date,
            ticker=ticker,
            action=action,
            quantity=quantity,
            price=price,
            value=value,
            commission=commission
        )
        
        self.trades.append(trade)
        return trade
    
    def get_total_portfolio_value(self) -> float:
        """Вычисляет общую стоимость портфеля"""
        positions_value = sum(pos.market_value for pos in self.positions.values())
        return self.current_cash + positions_value
    
    def get_position_value(self, ticker: str) -> float:
        """Возвращает стоимость позиции по тикеру"""
        if ticker in self.positions:
            return self.positions[ticker].market_value
        return 0.0
    
    def get_available_cash(self) -> float:
        """Возвращает доступные средства"""
        return self.current_cash
    
    def get_trades_summary(self) -> Dict[str, Any]:
        """Возвращает сводку по сделкам"""
        if not self.trades:
            return {"total_trades": 0, "total_volume": 0, "total_commission": 0}
        
        total_volume = sum(trade.value for trade in self.trades)
        total_commission = sum(trade.commission for trade in self.trades)
        
        return {
            "total_trades": len(self.trades),
            "total_volume": total_volume,
            "total_commission": total_commission,
            "buy_trades": len([t for t in self.trades if t.action == 'BUY']),
            "sell_trades": len([t for t in self.trades if t.action == 'SELL'])
        }


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

    def add_shares(self, quantity: int, price: float) -> None:
        """Добавляет акции к позиции (покупка)"""
        if quantity <= 0:
            return
        
        total_cost = self.cost_basis + (quantity * price)
        self.quantity += quantity
        self.avg_price = total_cost / self.quantity if self.quantity > 0 else 0.0

    def remove_shares(self, quantity: int) -> int:
        """Удаляет акции из позиции (продажа)"""
        if quantity <= 0 or self.quantity <= 0:
            return 0
        
        actual_quantity = min(quantity, self.quantity)
        self.quantity -= actual_quantity
        
        # Если позиция полностью закрыта, сбрасываем среднюю цену
        if self.quantity == 0:
            self.avg_price = 0.0
            
        return actual_quantity


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
    final_portfolio: Dict[str, BacktestPosition] = None  # Добавляем финальный портфель
    available_cash: float = 0.0  # Добавляем доступные средства
    trades_summary: Dict[str, Any] = None  # Добавляем сводку по сделкам





class BacktestEngine:
    """Движок для бэктестинга торговых стратегий"""
    
    def __init__(self, llm, initial_cash: float = 100000.0):
        self.llm = llm
        self.initial_cash = initial_cash
        self.agent_room = InvestorAgentRoom(llm)
        self.trading_engine = TradingEngine(initial_cash)  # Новый торговый движок

    def run_backtest(
            self, 
            days: int, 
            user_portfolio: Dict[str, Any],
            news_data: List[Dict[str, Any]],
            logger
        ) -> BacktestResult:
        """
        Запускает бэктест на указанное количество дней.
        Расчёт дневного PnL сделан корректно: 
        - PnL от изменения цен рассчитывается по количеству позиций, удерживаемых **в начале дня** (position_before).
        - PnL от исполненных решений (realized trades) добавляется если _apply_decisions возвращает значение.
        - Доходность портфеля (в процентах) — это взвешенное по стоимости портфеля изменение (price PnL / total_value_before).
        """
        end_date = dt.date.today()
        start_date = end_date - dt.timedelta(days=days)
        
        logger.info(f"🚀 Запуск бэктеста с {start_date} по {end_date} ({days} дней)")
        
        # tickers
        tickers = list(user_portfolio.keys())
        if not tickers:
            raise ValueError("Портфель пуст - нет тикеров для бэктеста")
        
        logger.info(f"📊 Анализируем {len(tickers)} тикеров: {', '.join(tickers)}")
        
        # Загружаем исторические данные
        historical_data = self._load_historical_data(tickers, start_date, end_date)
        
        # Инициализируем портфель (объекты позиций с полями quantity, market_value и т.д.)
        portfolio = self._initialize_portfolio(user_portfolio, historical_data, start_date)
        logger.info(f"Инициализирован портфель: {portfolio}")
        # Логируем стартовое состояние портфеля с кэшем
        try:
            self._log_portfolio_state(
                logger=logger,
                title=f"Стартовый портфель на {start_date}",
                positions=self.trading_engine.positions,
                cash=self.trading_engine.current_cash
            )
        except Exception as e:
            logger.info(f"Не удалось вывести стартовый портфель: {e}")
        # Начальная стоимость портфеля — вычислим на базе начальных цен
        initial_value = 0.0
        for ticker, pos in portfolio.items():
            if ticker in historical_data and start_date in historical_data[ticker]:
                start_price = historical_data[ticker][start_date]['close']
                ticker_value = pos.quantity * start_price
                initial_value += ticker_value
                logger.info(f"Начальная стоимость {ticker}: {pos.quantity} * {start_price:.2f} = {ticker_value:.2f}")
            else:
                initial_value += pos.market_value  # fallback
                logger.info(f"Начальная стоимость {ticker} (fallback): {pos.market_value:.2f}")
        logger.info(f"Начальная стоимость портфеля: {initial_value:.2f}")

        
        daily_results: List[BacktestDay] = []
        cumulative_pnl = 0.0
        
        current_date = start_date
        while current_date <= end_date:
            logger.info(f"📅 Обрабатываем день: {current_date}")
            
            # Получаем решения агентов для текущего дня
            logger.info(f"Получаем решения агентов для {current_date}")
            day_decisions = self._get_day_decisions(
                current_date, portfolio, news_data, historical_data, logger
            )
            logger.info(f"Получили решения агентов для {current_date}")
            
            # Снимаем snapshot позиций на начало дня (quantity и market_value)
            position_snapshot = {}
            for ticker, pos in portfolio.items():
                # Сохраняем минимум: quantity и market_value
                position_snapshot[ticker] = {
                    "quantity": pos.quantity,
                    "market_value": pos.market_value
                }
            
            # Вычисляем PnL от изменения цен (по движению open->close) исходя из quantity на начало дня
            price_pnl_total = 0.0
            total_value_before = 0.0  
            per_ticker_price_pnls = {}  # ticker -> pnl по движению цен
            
            for ticker in tickers:
                pos_snap = position_snapshot.get(ticker)
                if not pos_snap:
                    continue
                
                
                if ticker in historical_data and current_date in historical_data[ticker]:
                    candle = historical_data[ticker][current_date]
                    open_price = candle.get("open")
                    close_price = candle.get("close")
                    
                    if open_price is None or close_price is None:
                        per_ticker_price_pnls[ticker] = 0.0
                        continue
                    
                    qty = float(pos_snap["quantity"] or 0.0)
                    pos_value_before = qty * open_price if open_price and qty else float(pos_snap["market_value"] or 0.0)
                    total_value_before += pos_value_before
                    
                    ticker_price_pnl = qty * (close_price - open_price)
                    per_ticker_price_pnls[ticker] = ticker_price_pnl
                    price_pnl_total += ticker_price_pnl
                else:
                    per_ticker_price_pnls[ticker] = 0.0
            
            if total_value_before > 0:
                weighted_return_pct = (price_pnl_total / total_value_before) * 100.0
            else:
                weighted_return_pct = 0.0
            
            logger.info(
                f"Доходность по изменению цен за {current_date}: {weighted_return_pct:.4f}% "
                f"(price_pnl_total={price_pnl_total:.2f}, total_value_before={total_value_before:.2f})"
            )
            
            logger.info(f"Применяем решения и обновляем портфель для {current_date}")
            try:
                trades_pnl = self._apply_decisions(
                    current_date, day_decisions, portfolio, historical_data
                )
                # если _apply_decisions возвращает None, считаем 0
                trades_pnl = float(trades_pnl or 0.0)
            except Exception as e:
                logger.exception(f"Ошибка при применении решений на {current_date}: {e}")
                trades_pnl = 0.0
            logger.info(f"Применили решения для {current_date}, trades_pnl={trades_pnl:.2f}")
            
            day_pnl = price_pnl_total + trades_pnl
            cumulative_pnl += day_pnl
            
            day_results_for_log = []
            for ticker in tickers:
                if ticker in historical_data and current_date in historical_data[ticker]:
                    candle = historical_data[ticker][current_date]
                    decision = day_decisions.get(ticker)
                    
                    ticker_price_pnl = per_ticker_price_pnls.get(ticker, 0.0)
                    

                    pos_after = portfolio.get(ticker)
                    pos_before_snapshot = position_snapshot.get(ticker)
                    
                    day_result = BacktestDay(
                        date=current_date,
                        ticker=ticker,
                        open_price=candle['open'],
                        close_price=candle['close'],
                        high_price=candle.get('high'),
                        low_price=candle.get('low'),
                        volume=candle.get('volume'),
                        signal=getattr(decision, "final_action", None) if decision else None,
                        confidence=getattr(decision, "confidence_score", None) if decision else None,
                        position_before=pos_before_snapshot,
                        position_after=pos_after,
                        daily_pnl=ticker_price_pnl,
                        cumulative_pnl=cumulative_pnl
                    )
                    daily_results.append(day_result)
                    day_results_for_log.append(day_result)
            
            logger.info(f"День {current_date}: price_pnl={price_pnl_total:.2f}, trades_pnl={trades_pnl:.2f}, day_pnl={day_pnl:.2f}, cumulative_pnl={cumulative_pnl:.2f}")
            self._log_day_results(current_date, day_results_for_log, day_pnl, cumulative_pnl, initial_value, logger)

            current_date += dt.timedelta(days=1)
        
        logger.info("Вычисляем финальную стоимость портфеля")
        final_value = 0.0
        # Используем цены на end_date
        final_value = initial_value + cumulative_pnl
        
        total_pnl = final_value - initial_value
        total_return_pct = (total_pnl / initial_value) * 100 if initial_value > 0 else 0.0
        
        logger.info(f"Финальная стоимость: {final_value:.2f}, Total PnL: {total_pnl:.2f}, Total Return: {total_return_pct:.2f}%")
        
        # Анализ производительности по тикерам (используем дневные записи)
        logger.info("Анализируем производительность по тикерам")
        ticker_performance = self._analyze_ticker_performance(daily_results)
        
        logger.info("Логируем итоговый результат")
        self._log_final_results(
            start_date, end_date, initial_value, final_value, 
            total_pnl, total_return_pct, ticker_performance, logger
        )
        # Перед выводом финального портфеля обновим цены на конечную дату и выведем состояние портфеля
        try:
            self.trading_engine.update_prices(end_date, historical_data)
            self._log_portfolio_state(
                logger=logger,
                title=f"Финальный портфель на {end_date}",
                positions=self.trading_engine.positions,
                cash=self.trading_engine.current_cash
            )
        except Exception as e:
            logger.info(f"Не удалось вывести финальный портфель: {e}")
        logger.info(f"start_value: {initial_value}, end_value: {final_value}, total_pnl: {total_pnl}, total_return_pct: {total_return_pct}")
        
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

    def _log_portfolio_state(
        self,
        logger,
        title: str,
        positions: Dict[str, BacktestPosition],
        cash: float
    ) -> None:
        """Выводит в лог текущее состояние портфеля: кэш, позиции и итоги."""
        total_positions_value = sum((pos.market_value for pos in positions.values())) if positions else 0.0
        total_portfolio_value = total_positions_value + float(cash or 0.0)

        lines = [
            f"{title}",
            f"💵 Кэш: {cash:,.2f} ₽",
            f"📦 Стоимость позиций: {total_positions_value:,.2f} ₽",
            f"💼 Итого портфель: {total_portfolio_value:,.2f} ₽",
            "",
            "Позиции:" if positions else "Позиции: (нет)"
        ]
        for ticker, pos in sorted(positions.items()):
            lines.append(
                f"  • {ticker}: qty={pos.quantity}, avg={pos.avg_price:.2f} ₽, price={pos.current_price:.2f} ₽, value={pos.market_value:,.2f} ₽"
            )

        message = "\n".join(lines)
        # Используем message для красивого многострочного вывода, если доступно
        try:
            logger.message("", message)
        except Exception:
            logger.info(message)

    
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
        
        # Извлекаем стартовый кэш, если указан специальным ключом
        starting_cash = user_portfolio.get("__cash__")
        if isinstance(starting_cash, (int, float)):
            self.trading_engine.current_cash = float(starting_cash)
        else:
            self.trading_engine.current_cash = self.initial_cash

        for ticker, position_data in user_portfolio.items():
            if ticker == "__cash__":
                continue
            if ticker in historical_data and start_date in historical_data[ticker]:
                current_price = historical_data[ticker][start_date]['close']
                
                portfolio[ticker] = BacktestPosition(
                    ticker=ticker,
                    quantity=position_data.get('quantity', 0),
                    avg_price=position_data.get('avg_price', current_price),
                    current_price=current_price
                )
        
        # Синхронизируем стартовые позиции в торговом движке
        self.trading_engine.positions = {t: BacktestPosition(
            ticker=pos.ticker,
            quantity=pos.quantity,
            avg_price=pos.avg_price,
            current_price=pos.current_price
        ) for t, pos in portfolio.items()}
        return portfolio
    
    def _get_day_decisions(
        self,
        current_date: dt.date,
        portfolio: Dict[str, BacktestPosition],
        news_data: List[Dict[str, Any]],
        historical_data: Dict[str, Dict[dt.date, Dict[str, float]]],
        logger
    ) -> Dict[str, AggregatedDecision]:
        """Получает решения агентов для конкретного дня"""
        logger.info(f"🤖 Агенты обсуждают портфель на {current_date}")
        
        # Создаем "текущий" портфель для агентов
        current_portfolio = {}
        for ticker, pos in portfolio.items():
            current_portfolio[ticker] = {
                'quantity': pos.quantity,
                'avg_price': pos.avg_price
            }
        
        # Получаем мнения агентов
        agent_opinions = self.agent_room.discuss_portfolio(current_portfolio, news_data, logger=logger)
        
        # Агрегируем решения
        aggregated_decisions = aggregate_agent_opinions(agent_opinions)
        
        # Логируем решения агентов
        logger.info(f"📋 Решения агентов на {current_date}:")
        for decision in aggregated_decisions:
            signal_emoji = {
                'BUY': '🟢',
                'SELL': '🔴', 
                'HOLD': '🟡'
            }.get(decision.final_action, '⚪')
            logger.info(f"  {signal_emoji} {decision.ticker}: {decision.final_action} (уверенность: {decision.confidence_score:.1f}/10)")
        
        # Преобразуем в словарь для удобства
        decisions_dict = {decision.ticker: decision for decision in aggregated_decisions}
        
        return decisions_dict
    
    def _apply_decisions(self, current_date, decisions, portfolio, historical_data) -> float:
        """Применяет решения агентов через торговый движок"""
        # Обновляем цены в торговом движке
        self.trading_engine.update_prices(current_date, historical_data)
        
        # Исполняем сделки
        executed_trades = self.trading_engine.execute_trades(current_date, decisions, historical_data)
        
        # Обновляем портфель из торгового движка
        for ticker, position in self.trading_engine.positions.items():
            portfolio[ticker] = position
        
        # Вычисляем PnL от сделок
        trades_pnl = sum(trade.net_value for trade in executed_trades if trade.action == 'SELL') - \
                    sum(trade.net_value for trade in executed_trades if trade.action == 'BUY')
        
        return trades_pnl
    
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
                position_before = ticker_days[0].position_before
                if isinstance(position_before, dict):
                    initial_value = position_before.get('market_value', 0.0)
                else:
                    initial_value = position_before.market_value
                if initial_value > 0:
                    ticker_data['total_return_pct'] = (ticker_data['total_pnl'] / initial_value) * 100
        
        return ticker_performance
    
    def _log_day_results(
        self, 
        current_date: dt.date, 
        day_results: List[BacktestDay], 
        day_pnl: float, 
        cumulative_pnl: float, 
        initial_value: float,
        logger
    ) -> None:
        """Логирует результаты за день"""
        logger.info(f"Логируем результаты за день для {current_date}")
        if not day_results:
            logger.info(f"📊 {current_date}: Нет данных для отображения")
            return
        
        # Вычисляем текущую стоимость портфеля
        logger.info(f"Вычисляем текущую стоимость портфеля для {current_date}")
        current_portfolio_value = initial_value + cumulative_pnl
        daily_return_pct = (day_pnl / current_portfolio_value) * 100 if current_portfolio_value > 0 else 0
        total_return_pct = (cumulative_pnl / initial_value) * 100 if initial_value > 0 else 0
        

        # Детали по тикерам
        tmp_message = "Детали по тикерам:\n"
        for result in day_results:
            price_change = result.close_price - result.open_price
            price_change_pct = (price_change / result.open_price) * 100 if result.open_price > 0 else 0
            
            # Эмодзи для сигнала
            signal_emoji = {
                'BUY': '🟢',
                'SELL': '🔴', 
                'HOLD': '🟡'
            }.get(result.signal, '⚪')
            
            tmp_message += f"  {signal_emoji} {result.ticker}: {result.open_price:.2f} → {result.close_price:.2f} ₽ ({price_change_pct:+.2f}%) | {result.signal} (уверенность: {result.confidence:.1f}/10)\n"
        
        logger.message(
            "",
            (
                f"📊 {current_date}: Результаты дня\n"
                f"💰 PnL за день: {day_pnl:,.2f} ₽ ({daily_return_pct:+.2f}%)\n"
                f"📈 Общий PnL: {cumulative_pnl:,.2f} ₽ ({total_return_pct:+.2f}%)\n"
                f"💼 Стоимость портфеля: {current_portfolio_value:,.2f} ₽\n"
                f"{tmp_message}"
            )
        )

        logger.info("─" * 50)
    
    def _log_final_results(
        self,
        start_date: dt.date,
        end_date: dt.date, 
        initial_value: float,
        final_value: float,
        total_pnl: float,
        total_return_pct: float,
        ticker_performance: Dict[str, Dict[str, float]],
        logger
    ) -> None:
        """Логирует итоговые результаты бэктеста"""
        logger.info("🎯 ИТОГОВЫЕ РЕЗУЛЬТАТЫ БЭКТЕСТА")
        logger.info("=" * 60)
        logger.info(f"📅 Период: {start_date} - {end_date}")
        logger.info(f"💰 Начальная стоимость: {initial_value:,.2f} ₽")
        logger.info(f"💰 Финальная стоимость: {final_value:,.2f} ₽")
        logger.info(f"📈 Общий PnL: {total_pnl:,.2f} ₽")
        logger.info(f"📊 Общая доходность: {total_return_pct:+.2f}%")
        
        # Производительность по тикерам
        if ticker_performance:
            logger.info("📊 Производительность по тикерам:")
            for ticker, perf in ticker_performance.items():
                logger.info(f"  {ticker}: PnL {perf['total_pnl']:,.2f} ₽ ({perf['total_return_pct']:+.2f}%) | Уверенность: {perf['avg_confidence']:.1f}/10")
        
        logger.info("=" * 60)
