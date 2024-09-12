# --- Do not remove these libs ---
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame
import talib.abstract as ta
from datetime import datetime
import numpy as np


class RangeFilterStrategyV3(IStrategy):
    # Minimal ROI designed for the strategy.
    minimal_roi = {"0": 99}

    # Stoploss:
    stoploss = -0.7

    # Trailing stoploss
    trailing_stop = False
    trailing_stop_positive = 1  # 1%
    trailing_stop_positive_offset = 0.9  # 2%, move stop to 1% once 2% profit is reached
    trailing_only_offset_is_reached = False

    # Optimal timeframe for the strategy
    timeframe = "5m"

    # Run "populate_indicators" only for new candle
    process_only_new_candles = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count = 110

    # Enable shorting
    can_short = True

    # Define parameters for optimization in V3 format
    rng_per = 55
    rng_qty = 4.5

    # Experimental settings (configuration will overide these if set)
    use_exit_signal = True
    exit_profit_only = True
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
        # Calculate average range using high, low, and close prices
        avrng = ta.EMA(
            ta.TRANGE(dataframe["high"], dataframe["low"], dataframe["close"]), timeperiod=n
        )
        wper = (n * 2) - 1
        AC = ta.EMA(avrng, timeperiod=wper) * qty
        return AC

        # abs_diff = np.abs(dataframe["close"] - np.roll(dataframe["close"], 1))
        # abs_diff[0] = 0
        # wper = (n * 2) - 1
        # AC = ta.EMA(abs_diff, timeperiod=wper) * qty
        # return AC

    def rng_filt(self, series, rng_, n):
        r = rng_
        filt = series.copy()
        filt.iloc[:n] = series.iloc[:n]  # Ensure indexing is done using .iloc for Series
        for i in range(n, len(series)):
            if series.iloc[i] - r.iloc[i] > filt.iloc[i - 1]:
                filt.iloc[i] = series.iloc[i] - r.iloc[i]
            elif series.iloc[i] + r.iloc[i] < filt.iloc[i - 1]:
                filt.iloc[i] = series.iloc[i] + r.iloc[i]
            else:
                filt.iloc[i] = filt.iloc[i - 1]
        return filt

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Calculate range size and filter values
        dataframe["range_size"] = self.rng_size(dataframe, self.rng_qty, self.rng_per)
        dataframe["filter"] = self.rng_filt(
            dataframe["close"], dataframe["range_size"], self.rng_per
        )

        # Direction Conditions
        dataframe["fdir"] = 0
        dataframe.loc[dataframe["filter"] > dataframe["filter"].shift(1), "fdir"] = 1
        dataframe.loc[dataframe["filter"] < dataframe["filter"].shift(1), "fdir"] = -1

        dataframe["upward"] = (dataframe["fdir"] == 1).astype(int)
        dataframe["downward"] = (dataframe["fdir"] == -1).astype(int)

        # Initialize CondIni state tracking
        dataframe["CondIni"] = 0
        dataframe.loc[
            (dataframe["close"] > dataframe["filter"])
            & (dataframe["close"] > dataframe["close"].shift(1))
            & (dataframe["upward"] > 0),
            "CondIni",
        ] = 1  # Long condition

        dataframe.loc[
            (dataframe["close"] < dataframe["filter"])
            & (dataframe["close"] < dataframe["close"].shift(1))
            & (dataframe["downward"] > 0),
            "CondIni",
        ] = -1  # Short condition

        # Propagate previous CondIni state to avoid flipping on each candle
        dataframe["CondIni"] = dataframe["CondIni"].replace(0, None).ffill().fillna(0)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long entry conditions - ensure not entering long after previous long signal
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["filter"])
                & (dataframe["upward"] > 0)
                & (dataframe["close"] > dataframe["close"].shift(1))
                & (
                    dataframe["CondIni"].shift(1) == -1
                )  # Only enter long if previous condition was short
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "买入")

        # Short entry conditions - ensure not entering short after previous short signal
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["filter"])
                & (dataframe["downward"] > 0)
                & (dataframe["close"] < dataframe["close"].shift(1))
                & (
                    dataframe["CondIni"].shift(1) == 1
                )  # Only enter short if previous condition was long
            ),
            ["enter_short", "enter_tag"],
        ] = (1, "卖出")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long exit conditions
        dataframe.loc[
            ((dataframe["close"] < dataframe["filter"]) & (dataframe["downward"] > 0)),
            ["exit_long", "exit_tag"],
        ] = (1, "平多")

        # Short exit conditions
        dataframe.loc[
            ((dataframe["close"] > dataframe["filter"]) & (dataframe["upward"] > 0)),
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
