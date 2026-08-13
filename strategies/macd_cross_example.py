from nautilus_trader.indicators import MovingAverageConvergenceDivergence
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
import pandas as pd

from core import BaseStrategyConfig
from core import BaseStrategy


class MACDCrossConfig(BaseStrategyConfig, frozen=True, kw_only=True):
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9


class MACDCross(BaseStrategy):
    def __init__(self, config: MACDCrossConfig):
        super().__init__(config)
        self.macd = MovingAverageConvergenceDivergence(config.fast_period, config.slow_period)
        self.signal = ExponentialMovingAverage(config.signal_period)

        self.prev_macd_value = None
        self.macd_value = None
        self.prev_signal_value = None
        self.signal_value = None

    def on_start(self):
        super().on_start()
        self.register_indicator_for_bars(self.config.bar_type, self.macd)

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        if not self.indicators_initialized():
            return
        self.signal.update_raw(self.macd.value)
        self.prev_macd_value = self.macd_value
        self.macd_value = self.macd.value
        self.prev_signal_value = self.signal_value
        self.signal_value = self.signal.value

        self.trade()
        print(pd.to_datetime(bar.ts_init).isoformat(), bar.close)

        if self.config.enable_redis:
            tech_data = {
                "datetime": bar.ts_init,
                "macd": self.macd.value,
                "signal": self.signal.value,
            }
            self.redis_client.lpush(self.tech_key, self.encoder.encode(tech_data))

    def trade(self):
        if not (self.prev_macd_value is None or self.prev_signal_value is None):
            if self.prev_macd_value < self.prev_signal_value and self.macd_value > self.signal_value:
                self.set_position(1)
            elif self.prev_macd_value > self.prev_signal_value and self.macd_value < self.signal_value:
                self.set_position(-1)
