# risk_tools.py
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

@dataclass
class RiskFeatures:
    stl_trend_strength: float
    stl_season_strength: float
    stl_resid_vol: float
    ann_vol_close2close: float
    ann_vol_parkinson: float | None
    ann_vol_garman_klass: float | None
    max_drawdown: float
    current_drawdown: float
    rolling_beta_20d: float | None
    regime: str
    notes: str

def _annualize_vol(ret: pd.Series, periods_per_year: int = 252) -> float:
    return float(ret.std(ddof=0) * np.sqrt(periods_per_year))

def parkinson_vol(high: pd.Series, low: pd.Series, window: int = 20, periods_per_year: int = 252) -> pd.Series:
    # σ_P = sqrt( (1/(4 ln 2)) * mean( ln(Hi/Li)^2 ) ) annualized
    rng2 = np.log(high / low) ** 2
    coef = 1.0 / (4.0 * np.log(2.0))
    daily_sigma = np.sqrt(coef * rng2.rolling(window).mean())
    return daily_sigma * np.sqrt(periods_per_year)

def garman_klass_vol(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series,
                     window: int = 20, periods_per_year: int = 252) -> pd.Series:
    # σ_GK^2 = 0.5*(ln(H/L))^2 - (2ln2 - 1)*(ln(C/O))^2 ; annualized
    term1 = 0.5 * (np.log(high / low) ** 2)
    term2 = (2 * np.log(2) - 1) * (np.log(close / open_) ** 2)
    daily_var = (term1 - term2).rolling(window).mean()
    daily_sigma = np.sqrt(daily_var.clip(lower=0))
    return daily_sigma * np.sqrt(periods_per_year)

def max_drawdown(series: pd.Series) -> tuple[float, float]:
    cummax = series.cummax()
    dd = series / cummax - 1.0
    return float(dd.min()), float(dd.iloc[-1])

def rolling_beta(asset_ret: pd.Series, bench_ret: pd.Series, window: int = 20) -> float | None:
    both = pd.concat([asset_ret, bench_ret], axis=1).dropna()
    if len(both) < window:
        return None
    cov = both.iloc[-window:, 0].cov(both.iloc[-window:, 1])
    var = both.iloc[-window:, 1].var()
    return float(cov / var) if var > 0 else None

def compute_risk_features(
    px_close_daily: pd.Series,
    bench_close_daily: pd.Series | None = None,
    ohlc_daily: pd.DataFrame | None = None,
    stl_period: int = 5  # недельная сезонность по дневкам
) -> RiskFeatures:
    s = px_close_daily.dropna().astype(float).sort_index()
    logp = np.log(s)
    ret = logp.diff().dropna()

    # STL на лог-цене
    stl = STL(logp, period=stl_period, robust=True).fit()
    total_var = float((stl.trend + stl.seasonal + stl.resid).var())
    trend_var = float(stl.trend.var())
    season_var = float(stl.seasonal.var())
    trend_strength = (trend_var / total_var) if total_var > 0 else 0.0
    season_strength = (season_var / total_var) if total_var > 0 else 0.0
    resid_vol = float(stl.resid.std())

    # Волатильности
    ann_vol_c2c = _annualize_vol(ret)
    ann_vol_p = None
    ann_vol_gk = None
    if ohlc_daily is not None and not ohlc_daily.empty:
        od = ohlc_daily.copy()
        # нормализация индекса на дату
        if "end" in od.columns:
            od["date"] = pd.to_datetime(od["end"]).dt.date
        elif "date" in od.columns:
            od["date"] = pd.to_datetime(od["date"]).dt.date
        od = od.set_index("date").sort_index()
        if set(["high","low"]).issubset(od.columns):
            pv = parkinson_vol(od["high"].astype(float), od["low"].astype(float), window=20)
            ann_vol_p = float(pv.iloc[-1]) if pv.dropna().size else None
        if set(["open","high","low","close"]).issubset(od.columns):
            gkv = garman_klass_vol(od["open"].astype(float), od["high"].astype(float),
                                   od["low"].astype(float), od["close"].astype(float), window=20)
            ann_vol_gk = float(gkv.iloc[-1]) if gkv.dropna().size else None

    mdd, cur_dd = max_drawdown(s)

    beta = None
    if bench_close_daily is not None:
        br = np.log(bench_close_daily.dropna().astype(float).sort_index()).diff().dropna()
        beta = rolling_beta(ret, br)

    regime = "trend" if (trend_strength >= 0.55 and resid_vol <= 0.02) else "range"
    notes = f"trend={trend_strength:.2f}, season={season_strength:.2f}, resid_vol={resid_vol:.3f}"
    return RiskFeatures(
        stl_trend_strength=trend_strength,
        stl_season_strength=season_strength,
        stl_resid_vol=resid_vol,
        ann_vol_close2close=float(ann_vol_c2c),
        ann_vol_parkinson=ann_vol_p,
        ann_vol_garman_klass=ann_vol_gk,
        max_drawdown=mdd,
        current_drawdown=cur_dd,
        rolling_beta_20d=beta,
        regime=regime,
        notes=notes
    )