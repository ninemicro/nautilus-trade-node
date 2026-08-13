from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.indicators import RelativeStrengthIndex
from nautilus_trader.indicators import BollingerBands
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
import pandas as pd
from decimal import Decimal

from core import BaseStrategyConfig
from core import BaseStrategy


class RsiMeanReversionConfig(BaseStrategyConfig, frozen=True, kw_only=True):
    rsi_period: int = 14
    bb_period: int = 20
    bb_deviation: float = 2.0
    upper_rsi_threshold: float = 0.7
    lower_rsi_threshold: float = 0.3
    # stop_loss_pct: float = 0.02


class RsiMeanReversion(BaseStrategy):
    def __init__(self, config: RsiMeanReversionConfig):
        super().__init__(config)

        self.rsi = RelativeStrengthIndex(config.rsi_period)
        self.bb = BollingerBands(config.bb_period, config.bb_deviation)

        self.prev_rsi = None
        self.current_rsi = None
        self.hold_period_count = 0  # 持仓周期计数器
        self.hold_rsi = None  # 持仓rsi值

    def on_start(self):
        super().on_start()
        self.register_indicator_for_bars(self.config.bar_type, self.rsi)
        self.register_indicator_for_bars(self.config.bar_type, self.bb)

    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        if not self.indicators_initialized():
            return

        self.prev_rsi = self.current_rsi
        self.current_rsi = self.rsi.value

        self.trade()

        if self.config.enable_redis:
            tech_data = {
                "datetime": bar.ts_init,
                "rsi": self.rsi.value,
                "bb_upper": self.bb.upper,
                "bb_middle": self.bb.middle,
                "bb_lower": self.bb.lower,
            }
            self.redis_client.lpush(self.tech_key, self.encoder.encode(tech_data))
            # print(tech_data)

    def trade(self):
        if self.portfolio.is_flat(self.config.instrument_id) and self.prev_rsi is not None:
            if self.rsi.value < self.config.lower_rsi_threshold and self.current_rsi > self.prev_rsi:
                self.set_position(1)
                self.hold_period_count = 0
                self.hold_rsi = self.current_rsi
        if self.portfolio.is_net_long(self.config.instrument_id) and self.prev_rsi is not None:
            self.hold_period_count += 1
            # if self.rsi.value > 0.5 and self.current_rsi < self.prev_rsi:
            if self.rsi.value > 0.5:
                # current_position = self.get_position()
                # if current_position <= 0.5:
                #     self.close_all_positions(self.config.instrument_id)  # 仓位不足0.5，直接全平
                # else:
                #     self.set_position(current_position - Decimal(0.5))
                self.close_all_positions(self.config.instrument_id)
            elif self.hold_rsi is not None and self.hold_period_count > 15:
                self.close_all_positions(self.config.instrument_id)
