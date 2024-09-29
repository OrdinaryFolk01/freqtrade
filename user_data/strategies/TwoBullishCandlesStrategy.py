from freqtrade.strategy.interface import IStrategy
from pandas import DataFrame
from datetime import datetime
from freqtrade.persistence import Trade
from typing import Optional


class TwoBullishCandlesFixedStopStrategy(IStrategy):
    """
    优化后的策略，当出现连续两个阳线时开仓，并使用固定的止损价。
    """

    # 策略参数
    timeframe = "1d"
    process_only_new_candles = True

    # 最小回报率
    minimal_roi = {}

    # 默认止损（不会使用，因为我们使用固定的止损价）
    stoploss = -0.5

    # 允许开空
    can_short = True

    # 绘图配置
    plot_config = {
        "main_plot": {
            "prev_bullish_low": {"color": "green"},
            "prev_bearish_high": {"color": "red"},
        }
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 标记阳线
        dataframe["bullish"] = dataframe["close"] > dataframe["open"]
        # 标记阴线
        dataframe["bearish"] = dataframe["close"] < dataframe["open"]
        # 标记连续两个阳线
        dataframe["two_consecutive_bullish"] = dataframe["bullish"] & dataframe["bullish"].shift(1)
        # 标记连续两个阴线
        dataframe["two_consecutive_bearish"] = dataframe["bearish"] & dataframe["bearish"].shift(1)
        # 存储阳线的最低价
        dataframe["bullish_low"] = dataframe["low"].where(dataframe["bullish"])
        # 存储阴线的最高价
        dataframe["bearish_high"] = dataframe["high"].where(dataframe["bearish"])
        # 存储上一个阳线的最低价。如果前一个K线是阴线，则使用上一次阳线的low
        dataframe["prev_bullish_low"] = dataframe["bullish_low"].shift(1).ffill()
        # 存储上一个阴线的最高价。如果前一个K线是阳线，则使用上一次阴线的low
        dataframe["prev_bearish_high"] = dataframe["bearish_high"].shift(1).ffill()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 当出现连续两个阳线时，设置进场信号
        entry_conditions = dataframe["two_consecutive_bullish"]
        dataframe.loc[entry_conditions, "enter_long"] = 1

        # 当收盘价低于或等于上一个阴线的最低价时，设置进场信号
        entry_conditions = dataframe["two_consecutive_bearish"]
        dataframe.loc[entry_conditions, "enter_short"] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 当收盘价低于或等于上一个阳线的最低价时，触发离场
        exit_conditions = dataframe["close"] <= dataframe["prev_bullish_low"]
        dataframe.loc[exit_conditions, "exit_long"] = 1

        # 当收盘价高于或等于上一个阴线的最低价时，触发离场
        exit_conditions = dataframe["close"] >= dataframe["prev_bearish_high"]
        dataframe.loc[exit_conditions, "exit_short"] = 1

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
        # return max_leverage
        return 30.0

    def custom_exit_price(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        proposed_rate: float,
        current_profit: float,
        exit_tag: Optional[str],
        **kwargs,
    ) -> float:
        """
        使用固定的止损价
        """
        dataframe, last_updated = self.dp.get_analyzed_dataframe(
            pair=pair, timeframe=self.timeframe
        )

        if trade.entry_side == "buy":
            # 获取最新的 prev_bullish_low 值
            prev_bullish_low = dataframe["prev_bullish_low"].iat[-1]
            return prev_bullish_low

        if trade.entry_side == "sell":
            # 获取最新的 prev_bearish_high 值
            prev_bearish_high = dataframe["prev_bearish_high"].iat[-1]
            return prev_bearish_high
