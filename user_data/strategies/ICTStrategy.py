import datetime
import numpy as np
import pandas as pd
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class ICTStrategy(IStrategy):
    # 设置策略的时间框架和基础参数
    timeframe = "5m"  # 使用的K线时间框架
    can_short = True  # 允许做空
    startup_candle_count = 50  # 启动时需要的初始K线数量

    # 设置回测的参数
    minimal_roi = {
        "0": 0.1,  # 最小止盈比例设置为10%
    }

    stoploss = -0.02  # 止损设置为2%

    trailing_stop = True  # 开启追踪止损
    trailing_stop_positive = 0.01  # 追踪止损正偏差为1%
    trailing_stop_positive_offset = 0.015  # 追踪止损的偏移设置为1.5%

    plot_config = {
        "main_plot": {"ema200": {}},
        "subplots": {
            "看涨信号": {
                "bullish_order_block": {"color": "blue"},
            },
            "看跌信号": {
                "bearish_order_block": {"color": "red"},
            },
        },
    }

    # 自定义买入资金量（可选）
    def custom_stake_amount(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_stake: float,
        min_stake: float,
        max_stake: float,
        entry_tag: str,
        **kwargs,
    ) -> float:
        return proposed_stake  # 使用建议的买入资金量

    # 定义订单块检测函数
    def detect_order_blocks(self, dataframe: DataFrame, window_size: int = 3) -> DataFrame:
        # 检测看涨订单块
        dataframe["bullish_order_block"] = (
            (dataframe["low"].rolling(window=window_size).min() > dataframe["high"].shift(1))
            & (
                dataframe["low"].shift(1).rolling(window=window_size).min()
                > dataframe["high"].shift(2)
            )
        ).astype("int")

        # 检测看跌订单块
        dataframe["bearish_order_block"] = (
            (dataframe["high"].rolling(window=window_size).max() < dataframe["low"].shift(1))
            & (
                dataframe["high"].shift(1).rolling(window=window_size).max()
                < dataframe["low"].shift(2)
            )
        ).astype("int")

        return dataframe

    def detect_fvg(self, dataframe: DataFrame) -> DataFrame:
        """
        检测公平价值缺口（FVG）和内部公平价值缺口（iFVG）
        """
        dataframe["FVG"] = (
            (dataframe["low"].shift(2) > dataframe["high"].shift(1))
            & (dataframe["low"] < dataframe["high"].shift(2))
        ).astype("int")

        dataframe["iFVG"] = (
            (dataframe["low"].shift(1) > dataframe["high"])
            & (dataframe["low"] < dataframe["high"].shift(1))
        ).astype("int")

        return dataframe

    # 定义指标的计算
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 计算200周期的指数移动平均线（EMA）
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)

        # 调用订单块检测函数
        dataframe = self.detect_order_blocks(dataframe)

        # 检测FVG和iFVG
        dataframe = self.detect_fvg(dataframe)


        return dataframe

    # 定义买入（入场）条件
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bullish_order_block"] == 1)  # 检测到看涨订单块
                & (dataframe["close"] > dataframe["ema200"])  # 当前价格高于200周期EMA
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "ICT_Bullish_OB")  # 生成入场信号，并设置标签

        dataframe.loc[
            (
                (dataframe["bearish_order_block"] == 1)  # 检测到看跌订单块
                & (dataframe["close"] < dataframe["ema200"])  # 当前价格低于200周期EMA
            ),
            ["enter_short", "enter_tag"],
        ] = (1, "ICT_Bearish_OB")  # 生成做空信号，并设置标签

        return dataframe

    # 定义卖出（出场）条件
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["bullish_order_block"] == 1)  # 检测到看涨订单块
                & (dataframe["close"] < dataframe["ema200"])  # 当前价格低于200周期EMA
            ),
            ["exit_long", "enter_tag"],
        ] = (1, "ICT_Bullish_OB_Exit")  # 生成退出多头信号，并设置标签

        dataframe.loc[
            (
                (dataframe["bearish_order_block"] == 1)  # 检测到看跌订单块
                & (dataframe["close"] > dataframe["ema200"])  # 当前价格高于200周期EMA
            ),
            ["exit_short", "enter_tag"],
        ] = (1, "ICT_Bearish_OB_Exit")  # 生成退出空头信号，并设置标签

        return dataframe

    # 新增 leverage 函数，用于设置杠杆

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
