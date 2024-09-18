import datetime
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta


class OptimizedICTStrategy(IStrategy):
    # 设置策略的时间框架和基础参数
    timeframe = "5m"  # 使用的K线时间框架
    can_short = True  # 允许做空
    startup_candle_count = 200  # 启动时需要的初始K线数量

    # 设置回测的参数（移除固定的 minimal_roi 和 stoploss）
    minimal_roi = {}
    stoploss = -0.70  # 设置一个较大的初始止损，实际止损由 ATR 动态计算

    trailing_stop = False  # 关闭固定的追踪止损

    # 自定义绘图配置
    plot_config = {
        "main_plot": {"ema200": {"color": "white"}},
        "subplots": {
            "ATR_STOP": {"atr_stop": {"color": "red"}},
            "RSI": {
                "rsi": {},
            },
            "MACD": {
                "macd": {},
                "macdsignal": {},
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

    # 优化后的订单块检测函数
    def detect_order_blocks(self, dataframe: DataFrame, window_size: int = 12) -> DataFrame:
        # 使用更大的窗口和更严格的条件来检测订单块
        rolling_max = dataframe["high"].rolling(window=window_size).max()
        rolling_min = dataframe["low"].rolling(window=window_size).min()

        dataframe["bullish_order_block"] = (
            (dataframe["close"] > dataframe["open"])
            & (dataframe["low"] <= rolling_min.shift(1))
            & (dataframe["close"] >= dataframe["open"].shift(1))
        ).astype("int")

        dataframe["bearish_order_block"] = (
            (dataframe["close"] < dataframe["open"])
            & (dataframe["high"] >= rolling_max.shift(1))
            & (dataframe["close"] <= dataframe["open"].shift(1))
        ).astype("int")

        return dataframe

    # 检测公平价值缺口（FVG）和内部公平价值缺口（iFVG）
    def detect_fvg(self, dataframe: DataFrame) -> DataFrame:
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

        # 计算平均真实波幅（ATR）用于动态止损和止盈
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_stop"] = dataframe["atr"] * 1.5  # 动态止损设置为1.5倍的ATR

        # 计算相对强弱指数（RSI）
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        # 计算MACD指标
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]

        # 调用订单块检测函数
        dataframe = self.detect_order_blocks(dataframe)

        # 检测FVG和iFVG
        dataframe = self.detect_fvg(dataframe)

        return dataframe

    # 定义买入（入场）条件
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 多头入场条件
        dataframe.loc[
            (
                (dataframe["bullish_order_block"] == 1)  # 检测到看涨订单块
                & (dataframe["close"] > dataframe["ema200"])  # 当前价格高于200周期EMA
                & (dataframe["rsi"] < 10)  # RSI不超买
                & (dataframe["macd"] > dataframe["macdsignal"])  # MACD看涨交叉
                & (dataframe["close"] > dataframe["close"].shift(1))  # 当前价格高于前一根K线收盘价
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "Optimized_Bullish_Entry")  # 生成入场信号，并设置标签

        # 空头入场条件
        dataframe.loc[
            (
                (dataframe["bearish_order_block"] == 1)  # 检测到看跌订单块
                & (dataframe["close"] < dataframe["ema200"])  # 当前价格低于200周期EMA
                & (dataframe["rsi"] > 90)  # RSI不超卖
                & (dataframe["macd"] < dataframe["macdsignal"])  # MACD看跌交叉
                & (dataframe["close"] < dataframe["close"].shift(1))  # 当前价格低于前一根K线收盘价
            ),
            ["enter_short", "enter_tag"],
        ] = (1, "Optimized_Bearish_Entry")  # 生成做空信号，并设置标签

        return dataframe

    # 定义卖出（出场）条件
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # 多头退出条件
        # dataframe.loc[
        #     (
        #         (dataframe["close"] < dataframe["ema200"])  # 价格跌破EMA200
        #         | (dataframe["rsi"] > 70)  # RSI超买
        #         | (dataframe["macd"] < dataframe["macdsignal"])  # MACD死叉
        #     ),
        #     ["exit_long", "exit_tag"],
        # ] = (1, "Optimized_Bullish_Exit")  # 生成退出多头信号，并设置标签

        # 空头退出条件
        # dataframe.loc[
        #     (
        #         (dataframe["close"] > dataframe["ema200"])  # 价格突破EMA200
        #         | (dataframe["rsi"] < 30)  # RSI超卖
        #         | (dataframe["macd"] > dataframe["macdsignal"])  # MACD金叉
        #     ),
        #     ["exit_short", "exit_tag"],
        # ] = (1, "Optimized_Bearish_Exit")  # 生成退出空头信号，并设置标签

        return dataframe

    # 新增 leverage 函数，用于根据每笔交易的风险动态设置杠杆
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
        根据 ATR 动态调整杠杆，控制每笔交易的风险
        """
        # 设定每笔交易的最大风险为账户的1%
        # account_risk_percent = 0.70
        # 获取 ATR 值
        # dataframe = self.dp.get_pair_dataframe(pair=pair, timeframe=self.timeframe)
        # atr = dataframe["atr"].iloc[-1]
        # 计算单位风险
        # unit_risk = atr / current_rate
        # 计算杠杆
        # leverage = min((account_risk_percent / unit_risk), max_leverage)
        # return max(2.0, leverage)  # 确保杠杆不低于2倍
        return max_leverage

    # 设置动态止损（使用策略中的 custom_stoploss 函数）
    def custom_stoploss(
        self,
        pair: str,
        trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> float:
        """
        使用 ATR 动态调整止损水平
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]

        # 计算动态止损价位
        if trade.is_short:
            stoploss_price = last_candle["close"] + last_candle["atr_stop"]
        else:
            stoploss_price = last_candle["close"] - last_candle["atr_stop"]

        # 计算止损比例
        stoploss_ratio = (stoploss_price - current_rate) / current_rate

        # 对于多头，止损比例应为负数；对于空头，止损比例应为正数
        if trade.is_short:
            stoploss_ratio = max(stoploss_ratio, 0)
        else:
            stoploss_ratio = min(stoploss_ratio, 0)

        return stoploss_ratio

    # 设置动态的获利水平（可选）
    def adjust_trade_position(self, trade, order_type, amount, rate, time_in_force, **kwargs):
        """
        可以根据交易的浮动盈亏，动态调整持仓或部分平仓（此处为示例，可根据需要实现）
        """
        pass
