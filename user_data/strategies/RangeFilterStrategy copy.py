import numpy as np
import talib.abstract as ta
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame
from datetime import datetime


class RangeFilterStrategy(IStrategy):
    timeframe = "5m"
    INTERFACE_VERSION = 3  # 确保使用V3版本接口
    startup_candle_count = 20
    minimal_roi = {
        "0": 100,
    }
    stoploss = -0.3

    # 定义参数
    rng_per = 20
    rng_qty = 4.5

    # 允许做空
    can_short = True

    order_types = {
        'entry': 'market',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    def range_size(self, x, qty, n):
        wper = (n * 2) - 1
        avrng = ta.EMA(np.abs(x - x.shift(1)), timeperiod=n)
        AC = ta.EMA(avrng, timeperiod=wper) * qty

        return AC

    def filt(sefl, series, rng_, n):
        r = rng_.to_numpy()
        filt = np.full(len(series), series.iloc[0])

        # 向量化处理：从第 n 个元素开始，逐步更新 filt 数组
        for i in range(n, len(series)):
            filt[i] = np.where(
                series.iloc[i] - r[i] > filt[i - 1],
                series.iloc[i] - r[i],
                np.where(series.iloc[i] + r[i] < filt[i - 1], series.iloc[i] + r[i], filt[i - 1]),
            )

        # 计算 hi_band 和 lo_band
        hi_band = filt + r
        lo_band = filt - r

        # 返回结果
        return hi_band, lo_band, filt

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 计算 Range Size
        dataframe["range_size"] = self.range_size(dataframe["close"], self.rng_qty, self.rng_per)

        # 计算 Range Filter
        hi_band, lo_band, rng_filt = self.filt(
            dataframe["close"], dataframe["range_size"], self.rng_per
        )
        # 将结果添加到 dataframe 中
        dataframe["range_filt"] = rng_filt
        dataframe["hi_band"] = hi_band
        dataframe["lo_band"] = lo_band

        # 计算方向
        dataframe["fdir"] = np.where(
            dataframe["range_filt"] > dataframe["range_filt"].shift(1),
            1,
            np.where(dataframe["range_filt"] < dataframe["range_filt"].shift(1), -1, 0),
        )

        dataframe["upward"] = dataframe["fdir"] == 1
        dataframe["downward"] = dataframe["fdir"] == -1

        # 初始化CondIni
        dataframe["CondIni"] = 0

        # 计算longCond 和 shortCond
        longCond = (dataframe["close"] > dataframe["range_filt"]) & (
            (dataframe["close"] > dataframe["close"].shift(1)) & dataframe["upward"]
        ) | ((dataframe["close"] < dataframe["close"].shift(1)) & dataframe["upward"])

        shortCond = (dataframe["close"] < dataframe["range_filt"]) & (
            (dataframe["close"] < dataframe["close"].shift(1)) & dataframe["downward"]
        ) | ((dataframe["close"] > dataframe["close"].shift(1)) & dataframe["downward"])

        # 更新 CondIni
        dataframe.loc[longCond, "CondIni"] = 1
        dataframe.loc[shortCond, "CondIni"] = -1

        dataframe["CondIni"] = dataframe["CondIni"].replace(to_replace=0, method="ffill")

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        long_condition = (dataframe["close"] > dataframe["range_filt"]) & (
            dataframe["CondIni"].shift(1) == -1
        ) & ((dataframe["close"] > dataframe["close"].shift(1)) & dataframe["upward"]) | (
            (dataframe["close"] < dataframe["close"].shift(1)) & dataframe["upward"]
        )
        dataframe.loc[long_condition, "enter_long"] = 1

        short_condition = (dataframe["close"] < dataframe["range_filt"]) & (
            dataframe["CondIni"].shift(1) == 1
        ) & ((dataframe["close"] < dataframe["close"].shift(1)) & dataframe["downward"]) | (
            (dataframe["close"] > dataframe["close"].shift(1)) & dataframe["downward"]
        )
        dataframe.loc[short_condition, "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 退出长仓条件
        exit_long_condition = (
            (dataframe["CondIni"].shift(1) == 1)  # 之前为多头
            & (dataframe["close"] < dataframe["range_filt"])  # 当前价格低于过滤器
            & dataframe["downward"]  # 当前方向向下
        )
        dataframe.loc[exit_long_condition, "exit_long"] = 1

        # 退出短仓条件
        exit_short_condition = (
            (dataframe["CondIni"].shift(1) == -1)  # 之前为空头
            & (dataframe["close"] > dataframe["range_filt"])  # 当前价格高于过滤器
            & dataframe["upward"]  # 当前方向向上
        )
        dataframe.loc[exit_short_condition, "exit_short"] = 1

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
        """
        Customize leverage for each new trade.

        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in exit_pricing.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """
        return max_leverage
