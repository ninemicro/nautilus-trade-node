import finplot as fplt
import pandas as pd
import redis
import msgspec
import numpy as np


class AnalysisDrawer:
    def __init__(self, trade_node: str, rows: int,
                 redis_host="localhost", redis_port=6379, redis_db=0):
        fplt.candle_bull_body_color = '#26a69a'  # 蜡烛图阳线颜色
        fplt.candle_bear_body_color = '#ef5350'  # 蜡烛图阴线颜色
        fplt.volume_bull_color = '#26a69a'  # 成交量阳线颜色
        fplt.volume_bear_color = '#ef5350'  # 成交量阴线颜色

        self.ax = fplt.create_plot('BTCUSDT.BINANCE', rows=rows)

        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=False,
            max_connections=10,
            socket_timeout=5,
        )

        self.encoder = msgspec.msgpack.Encoder()  # 消息编码器
        self.decoder = msgspec.msgpack.Decoder()  # 消息解码器

        self.trade_node = trade_node

        self.data_map: dict[str, pd.DataFrame | None] = {
            f"{trade_node}:klines": None,  # K线数据
            f"{trade_node}:analysis": None,  # 分析数据
            f"{trade_node}:tech": None,  # 技术指标数据
            f"{trade_node}:orders": None,  # 订单数据
        }

    def load_data(self, index="datetime", start=0, end=-1):
        """
        从Redis加载数据到内存
        :param index: 索引列名，默认"datetime"
        :param start: 开始索引，默认0
        :param end: 结束索引，默认-1（加载所有数据）
        """
        for key in self.data_map.keys():
            try:
                values = self.redis_client.lrange(key, start, end)
                values = [self.decoder.decode(value) for value in values]
                df = pd.DataFrame(values)
                df = df.set_index(index)
                df.sort_index(inplace=True)
                self.data_map[key] = df
            except Exception as e:
                print(e, key)

    def draw_klines(self, axis):
        """
        绘制K线图
        :param axis: 子图索引
        """
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:klines"])
        if df is None or df.empty:
            return
        fplt.candlestick_ochl(df[['open', 'close', 'high', 'low']], ax=self.ax[axis])

    def draw_orders(self, axis):
        """
        绘制订单点
        :param axis: 子图索引
        """
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:orders"])
        if df is None or df.empty:
            return
        buy_df = df[df['side'] == 'BUY']
        sell_df = df[df['side'] == 'SELL']

        buy_dates = pd.to_datetime(buy_df.index)
        buy_prices = buy_df['price'].values.astype(float)

        sell_dates = pd.to_datetime(sell_df.index)
        sell_prices = sell_df['price'].values.astype(float)

        fplt.plot(buy_dates, buy_prices, style='^', color='green', size=10, ax=self.ax[axis])
        fplt.plot(sell_dates, sell_prices, style='v', color='dodgerblue', size=10, ax=self.ax[axis])

        # 添加买入标签
        if len(buy_df) > 0:
            buy_labels = ['B'] * len(buy_df)  # 或者使用具体价格
            fplt.labels(buy_dates, buy_prices, labels=buy_labels,
                        color='green', ax=self.ax[axis], anchor=(0.5, 0))

        # 添加卖出标签
        if len(sell_df) > 0:
            sell_labels = ['S'] * len(sell_df)
            fplt.labels(sell_dates, sell_prices, labels=sell_labels,
                        color='dodgerblue', ax=self.ax[axis], anchor=(0.5, 1))

    def draw_macd(self, axis, normalize=False):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        macd_dates = df.index
        if normalize:
            macd_values = df["nmacd"].values * 100
            signal_values = df["nsignal"].values * 100
            fplt.plot(macd_dates, macd_values, color='#1f77b4', width=2, legend='NMACD %', ax=self.ax[axis])
            fplt.plot(macd_dates, signal_values, color='#ff7f0e', width=2, legend='NSignal %', ax=self.ax[axis])
        else:
            macd_values = df["macd"].values
            signal_values = df["signal"].values
            fplt.plot(macd_dates, macd_values, color='#1f77b4', width=2, legend='MACD', ax=self.ax[axis])
            fplt.plot(macd_dates, signal_values, color='#ff7f0e', width=2, legend='Signal', ax=self.ax[axis])
        histogram = np.array(macd_values) - np.array(signal_values)

        fplt.add_line((macd_dates[0], 0), (macd_dates[-1], 0), color='#000000', width=1, ax=self.ax[axis])
        # hist_colors = ['#ef5350' if h < 0 else '#26a69a' for h in histogram]
        # fplt.bar(macd_dates, histogram, color=hist_colors, ax=self.ax[axis], legend='Histogram')
        # # 构造虚拟的OHLC数据用于volume_ocv
        hist_df = pd.DataFrame({
            'open': np.minimum(histogram, 0),  # 负数部分
            'close': np.maximum(histogram, 0),  # 正数部分
            'high': histogram,
            'low': 0
        }, index=macd_dates)
        fplt.volume_ocv(hist_df[['open', 'close', 'high', 'low']], ax=self.ax[axis])

    def draw_candidate_point(self, axis):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        sell_candidate_df = df[(df['candidate'] == True) & (df["nmacd"] > 0)]
        buy_candidate_df = df[(df['candidate'] == True) & (df["nmacd"] < 0)]

        sell_candidate_dates = pd.to_datetime(sell_candidate_df.index)
        sell_candidate_nmacd_values = sell_candidate_df['nmacd'].values.astype(float)
        sell_candidate_nmacd_values = sell_candidate_nmacd_values * 100

        buy_candidate_dates = pd.to_datetime(buy_candidate_df.index)
        buy_candidate_nmacd_values = buy_candidate_df['nmacd'].values.astype(float)
        buy_candidate_nmacd_values = buy_candidate_nmacd_values * 100

        fplt.plot(sell_candidate_dates, sell_candidate_nmacd_values, style='v', color='#9B59B6', ax=self.ax[axis])
        fplt.plot(buy_candidate_dates, buy_candidate_nmacd_values, style='^', color='#00BFFF', ax=self.ax[axis])

    def draw_macd_v(self, axis):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        macd_dates = df.index
        macd_v_values = df["macd-v"].values
        fplt.plot(macd_dates, macd_v_values, color='#1f77b4', width=2, legend='MACD-V %', ax=self.ax[axis])
        fplt.add_line((macd_dates[0], 0), (macd_dates[-1], 0), color='#000000', width=1, ax=self.ax[axis])

    def draw_bollinger_bands(self, axis):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        bb_dates = df.index
        bb_upper_values = df["bb_upper"].values
        bb_middle_values = df["bb_middle"].values
        bb_lower_values = df["bb_lower"].values

        fplt.plot(bb_dates, bb_upper_values, color='#E74C3C', width=2, legend='BB Upper', style='-', ax=self.ax[axis])
        fplt.plot(bb_dates, bb_middle_values, color='#F39C12', width=2, legend='BB Middle', style='-', ax=self.ax[axis])
        fplt.plot(bb_dates, bb_lower_values, color='#27AE60', width=2, legend='BB Lower', style='-', ax=self.ax[axis])

    def draw_keltner_channel(self, axis):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        kc_dates = df.index
        kc_upper_values = df["kc_upper"].values
        kc_middle_values = df["kc_middle"].values
        kc_lower_values = df["kc_lower"].values

        fplt.plot(kc_dates, kc_upper_values, color='#E74C3C', width=2, legend='KC Upper', style='--', ax=self.ax[axis])
        fplt.plot(kc_dates, kc_middle_values, color='#F39C12', width=2, legend='KC Middle', style='--', ax=self.ax[axis])
        fplt.plot(kc_dates, kc_lower_values, color='#27AE60', width=2, legend='KC Lower', style='--', ax=self.ax[axis])

    def draw_rsi(self, axis):
        df = pd.DataFrame(self.data_map[f"{self.trade_node}:tech"])
        if df is None or df.empty:
            return
        rsi_dates = df.index
        rsi_values = df["rsi"].values
        fplt.plot(rsi_dates, rsi_values, color='#1f77b4', width=2, legend='RSI %', ax=self.ax[axis])

        fplt.add_line((rsi_dates[0], 0.5), (rsi_dates[-1], 0.5), color='#000000', width=1, ax=self.ax[axis])

    @staticmethod
    def show():
        fplt.show()


def test():
    drawer = AnalysisDrawer("trade_node1", 2)
    drawer.load_data()
    drawer.draw_klines(axis=0)
    drawer.draw_orders(axis=0)
    drawer.draw_bollinger_bands(axis=0)
    drawer.draw_keltner_channel(axis=0)
    drawer.show()


if __name__ == "__main__":
    test()
