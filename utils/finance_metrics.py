from __future__ import annotations
import dataclasses
from dataclasses import dataclass
from typing import Optional, Tuple, Dict
import numpy as np
import pandas as pd

DAYS_PER_YEAR = 252  # торговых дней в году, можно настроить


@dataclass
class MetricsResult:
    total_return: float
    cagr: float
    annualized_vol: float
    sharpe: float
    sortino: float
    max_drawdown: float
    max_drawdown_start: Optional[pd.Timestamp]
    max_drawdown_end: Optional[pd.Timestamp]
    calmar: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    skewness: float
    kurtosis: float
    var_historical: float
    cvar: float
    alpha: Optional[float] = None
    beta: Optional[float] = None
    additional: Dict[str, float] = dataclasses.field(default_factory=dict)


class PortfolioMetrics:
    """
    Утилитарный класс для расчёта финансовых/портфельных метрик.

    Основные входы:
      - values: pd.Series индекст дат -> стоимость портфеля (float).
      - или returns: pd.Series индекст дат -> периодные доходности (float, например daily returns).
    """

    @staticmethod
    def _ensure_returns_series(values: Optional[pd.Series] = None,
                               returns: Optional[pd.Series] = None,
                               freq_days: int = 1) -> pd.Series:
        """Возвращает pd.Series доходностей (дневных), индекс даты."""
        if returns is not None:
            r = returns.dropna().astype(float)
            if r.empty:
                raise ValueError("Передана пустая серия returns")
            return r
        if values is not None:
            vs = values.dropna().astype(float)
            if vs.empty:
                raise ValueError("Передана пустая серия values")
            # относительные приросты: r_t = V_t / V_{t-1} - 1
            r = vs.pct_change().dropna()
            if r.empty:
                raise ValueError("Недостаточно точек в values для расчёта доходностей")
            return r
        raise ValueError("Требуется либо values (pd.Series), либо returns (pd.Series)")

    @staticmethod
    def total_return_from_values(values: pd.Series) -> float:
        v = values.dropna().astype(float)
        if v.empty:
            return 0.0
        return (v.iloc[-1] / v.iloc[0]) - 1.0

    @staticmethod
    def cagr_from_values(values: pd.Series, days_per_year: int = DAYS_PER_YEAR) -> float:
        v = values.dropna().astype(float)
        if len(v) < 2:
            return 0.0
        days = (v.index[-1] - v.index[0]).days or len(v)  # fallback
        years = days / 365.0 if days > 0 else len(v) / days_per_year
        # use counts if calendar days led to 0
        if years <= 0:
            years = len(v) / days_per_year
        total_ret = (v.iloc[-1] / v.iloc[0]) - 1.0
        if total_ret <= -1.0:
            return -1.0
        cagr = (v.iloc[-1] / v.iloc[0]) ** (1.0 / years) - 1.0
        return float(cagr)

    @staticmethod
    def annualized_volatility(returns: pd.Series, days_per_year: int = DAYS_PER_YEAR) -> float:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0
        return float(r.std(ddof=1) * np.sqrt(days_per_year))

    @staticmethod
    def sharpe_ratio(returns: pd.Series, rf: float = 0.0, days_per_year: int = DAYS_PER_YEAR) -> float:
        """
        Простая Sharpe: (annualized_return - rf) / annualized_vol
        rf — годовая безрисковая ставка (в долях, например 0.02)
        """
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0
        ann_ret = ((1.0 + r).prod()) ** (days_per_year / len(r)) - 1.0
        ann_vol = PortfolioMetrics.annualized_volatility(r, days_per_year)
        if ann_vol == 0:
            return 0.0
        return float((ann_ret - rf) / ann_vol)

    @staticmethod
    def sortino_ratio(returns: pd.Series, rf: float = 0.0, days_per_year: int = DAYS_PER_YEAR) -> float:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0
        ann_ret = ((1.0 + r).prod()) ** (days_per_year / len(r)) - 1.0
        # downside deviation (only negative returns)
        negative_r = r[r < 0]
        if negative_r.empty:
            denom = 0.0
        else:
            downside_dev = negative_r.std(ddof=1) * np.sqrt(days_per_year)
            denom = downside_dev
        if denom == 0:
            return float('inf') if ann_ret - rf > 0 else 0.0
        return float((ann_ret - rf) / denom)

    @staticmethod
    def max_drawdown(values: pd.Series) -> Tuple[float, Optional[pd.Timestamp], Optional[pd.Timestamp]]:
        """
        Возвращает (max_drawdown (отрицательное число), start_date_of_peak, end_date_of_trough)
        max_drawdown выражается как отрицательная доля (например -0.25 = падение 25%).
        """
        v = values.dropna().astype(float)
        if v.empty:
            return 0.0, None, None
        running_max = v.cummax()
        drawdown = (v - running_max) / running_max
        min_dd = float(drawdown.min())
        if np.isclose(min_dd, 0.0):
            return 0.0, None, None
        end_idx = drawdown.idxmin()
        # начинаем поиск пика до trough
        start_idx_candidates = v[:end_idx]
        if start_idx_candidates.empty:
            return min_dd, None, end_idx
        start_idx = start_idx_candidates.idxmax()
        return min_dd, pd.to_datetime(start_idx), pd.to_datetime(end_idx)

    @staticmethod
    def calmar_ratio(cagr: float, max_drawdown: float) -> float:
        # max_drawdown отрицательное -> используем абсолютное значение
        if max_drawdown >= 0:
            return float('inf') if cagr > 0 else 0.0
        dd = abs(max_drawdown)
        if dd == 0:
            return float('inf') if cagr > 0 else 0.0
        return float(cagr / dd)

    @staticmethod
    def win_loss_stats(returns: pd.Series) -> Tuple[float, float, float, float]:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0, 0.0, 0.0, 0.0
        wins = r[r > 0]
        losses = r[r <= 0]
        win_rate = len(wins) / len(r) if len(r) > 0 else 0.0
        avg_win = float(wins.mean()) if not wins.empty else 0.0
        avg_loss = float(losses.mean()) if not losses.empty else 0.0
        gross_win = wins.sum() if not wins.empty else 0.0
        gross_loss = -losses.sum() if not losses.empty else 0.0  # positive
        profit_factor = float(gross_win / gross_loss) if gross_loss > 0 else float('inf') if gross_win > 0 else 0.0
        return float(win_rate), float(avg_win), float(avg_loss), float(profit_factor)

    @staticmethod
    def skew_kurt(returns: pd.Series) -> Tuple[float, float]:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0, 0.0
        return float(r.skew()), float(r.kurt())

    @staticmethod
    def var_historical(returns: pd.Series, alpha: float = 0.05) -> float:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0
        return float(np.percentile(r, 100.0 * alpha))

    @staticmethod
    def cvar_historical(returns: pd.Series, alpha: float = 0.05) -> float:
        r = returns.dropna().astype(float)
        if r.empty:
            return 0.0
        threshold = PortfolioMetrics.var_historical(r, alpha)
        tail = r[r <= threshold]
        if tail.empty:
            return float(threshold)
        return float(tail.mean())

    @staticmethod
    def alpha_beta(returns: pd.Series, market_returns: pd.Series, days_per_year: int = DAYS_PER_YEAR) -> Tuple[Optional[float], Optional[float]]:
        """
        Регрессируем portfolio_returns ~ alpha_daily + beta * market_returns_daily
        Возвращаем annualized_alpha (в долях) и beta.
        Annualized alpha — прибл. intercept * days_per_year.
        """
        r = returns.dropna().astype(float)
        m = market_returns.dropna().astype(float)
        # align
        df = pd.concat([r, m], axis=1, join='inner').dropna()
        if df.shape[0] < 2:
            return None, None
        y = df.iloc[:, 0].values
        x = df.iloc[:, 1].values
        # add constant
        X = np.vstack([np.ones_like(x), x]).T
        try:
            coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            intercept, beta = float(coef[0]), float(coef[1])
            # annualize intercept (approx)
            alpha_annual = intercept * days_per_year
            return float(alpha_annual), float(beta)
        except Exception:
            return None, None

    @staticmethod
    def turnover_from_trades(trades: pd.DataFrame, avg_portfolio_value: float) -> float:
        """
        trades: DataFrame with колонкой 'traded_value' (абсолютная стоимость покупок+продаж за период)
        avg_portfolio_value: средняя стоимость портфеля за период
        turnover = sum(traded_value) / avg_portfolio_value
        """
        if trades is None or trades.empty:
            return 0.0
        total_traded = trades['traded_value'].abs().sum()
        if avg_portfolio_value == 0:
            return float('inf') if total_traded > 0 else 0.0
        return float(total_traded / avg_portfolio_value)

    @staticmethod
    def contributions_by_ticker(daily_results: pd.DataFrame, initial_value: float) -> Dict[str, float]:
        """
        daily_results: DataFrame с колонками ['date','ticker','daily_pnl'] или аналог.
        Возвращает словарь ticker -> вклад в итоговый PnL (% от initial_value).
        """
        if daily_results is None or daily_results.empty:
            return {}
        if 'ticker' not in daily_results.columns or 'daily_pnl' not in daily_results.columns:
            raise ValueError("daily_results должен содержать колонки 'ticker' и 'daily_pnl'")
        grouped = daily_results.groupby('ticker')['daily_pnl'].sum()
        if initial_value == 0:
            return {t: float(p) for t, p in grouped.items()}
        return {t: float(p / initial_value) for t, p in grouped.items()}

    @staticmethod
    def build_metrics(values: Optional[pd.Series] = None,
                      returns: Optional[pd.Series] = None,
                      market_returns: Optional[pd.Series] = None,
                      rf: float = 0.0,
                      days_per_year: int = DAYS_PER_YEAR,
                      alpha: float = 0.05) -> MetricsResult:
        """
        Главный метод: строит и возвращает MetricsResult.
        Передавайте либо values (series портфельных значений), либо returns (series доходностей).
        """
        r = PortfolioMetrics._ensure_returns_series(values=values, returns=returns, freq_days=1)
        # Если есть values, используем их для total_return/cagr/max_drawdown
        total_ret = 0.0
        cagr = 0.0
        max_dd = 0.0
        md_start = None
        md_end = None
        if values is not None:
            vs = values.dropna().astype(float)
            if not vs.empty:
                total_ret = PortfolioMetrics.total_return_from_values(vs)
                cagr = PortfolioMetrics.cagr_from_values(vs, days_per_year=days_per_year)
                md, md_start, md_end = PortfolioMetrics.max_drawdown(vs)
                max_dd = md
        else:
            # если values нет, посчитаем накопленную серию wealth index
            wealth = (1.0 + r).cumprod()
            total_ret = float(wealth.iloc[-1] - 1.0)
            cagr = ((wealth.iloc[-1]) ** (days_per_year / len(r))) - 1.0
            max_dd, md_start, md_end = PortfolioMetrics.max_drawdown(wealth)
            max_dd = float(max_dd)

        ann_vol = PortfolioMetrics.annualized_volatility(r, days_per_year=days_per_year)
        sharpe = PortfolioMetrics.sharpe_ratio(r, rf=rf, days_per_year=days_per_year)
        sortino = PortfolioMetrics.sortino_ratio(r, rf=rf, days_per_year=days_per_year)
        calmar = PortfolioMetrics.calmar_ratio(cagr, max_dd)
        win_rate, avg_win, avg_loss, profit_factor = PortfolioMetrics.win_loss_stats(r)
        skewness, kurtosis = PortfolioMetrics.skew_kurt(r)
        var_hist = PortfolioMetrics.var_historical(r, alpha=alpha)
        cvar = PortfolioMetrics.cvar_historical(r, alpha=alpha)

        alpha_val = None
        beta_val = None
        if market_returns is not None:
            alpha_val, beta_val = PortfolioMetrics.alpha_beta(r, market_returns, days_per_year=days_per_year)

        extra = {
            "days": int(len(r)),
            "annualized_return_approx": float(((1.0 + r).prod()) ** (days_per_year / len(r)) - 1.0)
        }

        return MetricsResult(
            total_return=float(total_ret),
            cagr=float(cagr),
            annualized_vol=float(ann_vol),
            sharpe=float(sharpe),
            sortino=float(sortino),
            max_drawdown=float(max_dd),
            max_drawdown_start=md_start,
            max_drawdown_end=md_end,
            calmar=float(calmar),
            win_rate=float(win_rate),
            avg_win=float(avg_win),
            avg_loss=float(avg_loss),
            profit_factor=float(profit_factor),
            skewness=float(skewness),
            kurtosis=float(kurtosis),
            var_historical=float(var_hist),
            cvar=float(cvar),
            alpha=alpha_val,
            beta=beta_val,
            additional=extra
        )
