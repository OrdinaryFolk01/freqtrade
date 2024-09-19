# --- Do not remove these libs ---
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame
import talib.abstract as ta
from datetime import datetime
import numpy as np
import pandas as pd  # 添加 pandas 库


class RangeFilterStrategyV3(IStrategy):
    # 使用 Freqtrade 的参数优化功能
    rng_per = IntParameter(10, 100, default=20, space="optimize")
    rng_qty = DecimalParameter(1.0, 10.0, default=4.5, space="optimize")

    # Minimal ROI designed for the strategy.
    minimal_roi = {"0": 10}  # 设置为 10% 的收益目标

    # Stoploss:
    stoploss = -0.5  # 将止损设置为 -5%

    # Trailing stoploss
    trailing_stop = False
    trailing_stop_positive = 0.2
    trailing_stop_positive_offset = 0.3
    trailing_only_offset_is_reached = True

    # Optimal timeframe for the strategy
    timeframe = "5m"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 40

    # Enable shorting
    can_short = True

    # Experimental settings (configuration will overide these if set)
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Optional order type mapping
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "emergency_exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
        "stoploss_on_exchange_limit_ratio": 0.99,
    }

    def rng_size(self, dataframe: DataFrame, qty, n):
        # 计算平均真实波幅 (ATR)
        avrng = ta.EMA(ta.TRANGE(dataframe), timeperiod=n)
        wper = (n * 2) - 1
        AC = ta.EMA(avrng, timeperiod=wper) * qty
        return AC

    def rng_filt(self, series, rng_, n):
        # 使用向量化操作替代循环，提升性能
        filt = pd.Series(index=series.index, dtype="float64")
        filt.iloc[:n] = series.iloc[:n]

        for i in range(n, len(series)):
            if series.iloc[i] - rng_.iloc[i] > filt.iloc[i - 1]:
                filt.iloc[i] = series.iloc[i] - rng_.iloc[i]
            elif series.iloc[i] + rng_.iloc[i] < filt.iloc[i - 1]:
                filt.iloc[i] = series.iloc[i] + rng_.iloc[i]
            else:
                filt.iloc[i] = filt.iloc[i - 1]
        return filt

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        n = self.rng_per.value
        qty = self.rng_qty.value

        # 计算区间大小和过滤器值
        dataframe["range_size"] = self.rng_size(dataframe, qty, n)
        dataframe["filter"] = self.rng_filt(dataframe["close"], dataframe["range_size"], n)

        # 确定趋势方向
        dataframe["fdir"] = np.where(
            dataframe["filter"] > dataframe["filter"].shift(1),
            1,
            np.where(dataframe["filter"] < dataframe["filter"].shift(1), -1, 0),
        )

        dataframe["upward"] = (dataframe["fdir"] == 1).astype(int)
        dataframe["downward"] = (dataframe["fdir"] == -1).astype(int)

        # 初始化条件状态跟踪
        dataframe["CondIni"] = np.where(
            (dataframe["close"] > dataframe["filter"])
            & (dataframe["close"] > dataframe["close"].shift(1))
            & (dataframe["upward"] > 0),
            1,
            np.where(
                (dataframe["close"] < dataframe["filter"])
                & (dataframe["close"] < dataframe["close"].shift(1))
                & (dataframe["downward"] > 0),
                -1,
                0,
            ),
        )

        # 传播之前的 CondIni 状态，避免在每根K线时翻转
        dataframe["CondIni"] = dataframe["CondIni"].replace(0, np.nan).ffill().fillna(0)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 多头开仓条件
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["filter"])
                & (dataframe["upward"] > 0)
                & (dataframe["close"] > dataframe["close"].shift(1))
                & (dataframe["CondIni"].shift(1) == -1)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "买入")

        # 空头开仓条件
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["filter"])
                & (dataframe["downward"] > 0)
                & (dataframe["close"] < dataframe["close"].shift(1))
                & (dataframe["CondIni"].shift(1) == 1)
            ),
            ["enter_short", "enter_tag"],
        ] = (1, "卖出")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 多头平仓条件
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["filter"])
                & (dataframe["downward"] > 0)
                & (dataframe["CondIni"].shift(1) != -1)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "平多")

        # 空头平仓条件
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["filter"])
                & (dataframe["upward"] > 0)
                & (dataframe["CondIni"].shift(1) != 1)
            ),
            ["exit_short", "exit_tag"],
        ] = (1, "平空")

        return dataframe

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        side: str,
        **kwargs,
    ) -> float:
        # 根据风险管理，设置合适的杠杆倍数
        # leverage = min(3.0, max_leverage)  # 设定最大使用3倍杠杆
        return max_leverage
