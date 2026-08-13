from nautilus_trader.indicators import MovingAverageConvergenceDivergence
from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.indicators import BollingerBands
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
import pandas as pd

from core import BaseStrategyConfig
from core import BaseStrategy


class MacdReversionConfig(BaseStrategyConfig, frozen=True, kw_only=True):
    fast_period: int = 7
    slow_period: int = 21
    signal_period: int = 9
    # stop_loss_pct: float = 0.1


class MacdReversion(BaseStrategy):
    def __init__(self, config: MacdReversionConfig):
        super().__init__(config)
        self.bollinger_bands = BollingerBands(config.slow_period, 2)
        self.nsignal = ExponentialMovingAverage(config.signal_period)
        self.ema_fast = ExponentialMovingAverage(config.fast_period)
        self.ema_slow = ExponentialMovingAverage(config.slow_period)  # 价格基准

        self.prev_nmacd_value = None
        self.nmacd_value = None
        self.prev_nsignal_value = None
        self.nsignal_value = None

        self.candidate_available = True  # 是否有候选信号

    def on_start(self):
        super().on_start()
        self.register_indicator_for_bars(self.config.bar_type, self.ema_fast)
        self.register_indicator_for_bars(self.config.bar_type, self.ema_slow)
        self.register_indicator_for_bars(self.config.bar_type, self.bollinger_bands)

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        if not self.indicators_initialized():
            return
        self.prev_nmacd_value = self.nmacd_value
        self.prev_nsignal_value = self.nsignal_value

        self.nmacd_value = (self.ema_fast.value - self.ema_slow.value) / self.ema_slow.value
        self.nsignal.update_raw(self.nmacd_value)
        self.nsignal_value = self.nsignal.value

        if self.prev_nmacd_value is not None:
            if (self.prev_nmacd_value > 0 > self.nmacd_value) or (self.prev_nmacd_value < 0 < self.nmacd_value):
                self.candidate_available = True

        self.trade()

        if self.config.enable_redis:
            tech_data = {
                "datetime": bar.ts_init,
                "nmacd": self.nmacd_value,
                "nsignal": self.nsignal_value,
                "bollinger_upper": self.bollinger_bands.upper,
                "bollinger_middle": self.bollinger_bands.middle,
                "bollinger_lower": self.bollinger_bands.lower,
            }
            self.redis_client.lpush(self.tech_key, self.encoder.encode(tech_data))
            # print(tech_data)

    def trade(self):
        if self.prev_nmacd_value is not None:
            nmacd_slope = self.nmacd_value - self.prev_nmacd_value
            if self.portfolio.is_flat(self.config.instrument_id):
                if self.nmacd_value > 0 > nmacd_slope and self.candidate_available and self.nmacd_value > 0.01:
                    self.set_position(-1)
                    self.candidate_available = False

                if self.nmacd_value < 0 < nmacd_slope and self.candidate_available and self.nmacd_value < -0.01:
                    self.set_position(1)
                    self.candidate_available = False

            elif self.portfolio.is_net_long(self.config.instrument_id):
                if self.nmacd_value > 0 > nmacd_slope and self.candidate_available:
                    self.close_all_positions(self.config.instrument_id)
            elif self.portfolio.is_net_short(self.config.instrument_id):
                if self.nmacd_value < 0 < nmacd_slope and self.candidate_available:
                    self.close_all_positions(self.config.instrument_id)
