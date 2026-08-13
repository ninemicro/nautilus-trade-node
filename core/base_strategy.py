from decimal import Decimal
from collections import deque
from datetime import datetime, timedelta
import pandas as pd
import pytz
import redis
import time
import msgspec

from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events.order import OrderFilled
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.objects import Currency


class BaseStrategyConfig(StrategyConfig, frozen=True, kw_only=True):
    """基础参数"""
    instrument_id: InstrumentId  # 合约ID
    base_currency: Currency  # 目标货币
    quote_currency: Currency  # 量价货币
    venue: Venue  # 交易所
    bar_type: BarType  # K线类型

    """风险参数"""
    safe_pct: float = 0.2  # 安全比例(控制资金投入)
    stop_loss_pct: float = 0.2  # 止损比例(预防黑天鹅事件)
    stop_profit_pct: float = 0.2  # 止盈比例(控制利润预防大回撤)
    max_position_ratio: float = 0.9  # 最大持仓比例比例(限制单笔投入)
    min_position_ratio: float = 0.1  # 最小持仓比例比例(避免频繁交易)
    max_leverage: int = 3  # 最大杠杆倍数(默认3倍)

    """交易参数"""
    warmup_bars: int = 30  # 预热K线数量（指标需要足够数据）
    warmup_mode: bool = False  # 是否开启预热模式
    warmup_timedelta: timedelta = timedelta(days=30)  # 预热历史时间范围（默认最近30天）
    use_hyphens_in_client_order_ids: bool = False  # 是否在客户端订单ID中使用连字符

    """数据参数"""
    redis_host: str = "localhost"  # Redis主机地址
    redis_port: int = 6379  # Redis端口号
    redis_db: int = 0  # Redis数据库索引
    redis_prefix: str = "trade_node1"  # Redis键前前缀(防止跨应用冲突)
    enable_redis: bool = False  # 是否开启Redis存储
    max_period: int = 1000  # 最大时间周期数量(超过数量会删除旧数据)


class BaseStrategy(Strategy):
    def __init__(self, config: BaseStrategyConfig):
        """
        初始化策略
        :param config: 策略配置
        """
        super().__init__(config)
        self.hold_price = None  # 持仓价格
        self.current_price = None  # 当前价格
        self.equity_value = None  # 资产值
        self.account = None  # 账户对象
        self.redis_client = None  # Redis客户端

        self.encoder = msgspec.msgpack.Encoder()  # 消息编码器
        self.decoder = msgspec.msgpack.Decoder()  # 消息解码器

        self.klines_key = f"{self.config.redis_prefix}:klines"  # K线数据键
        self.analysis_key = f"{self.config.redis_prefix}:analysis"  # 分析数据键
        self.orders_key = f"{self.config.redis_prefix}:orders"  # 订单数据键
        self.tech_key = f"{self.config.redis_prefix}:tech"  # 技术指标数据键

    def on_start(self):
        """初始化策略，获取账户信息，订阅K线数据，预热K线数据"""
        self.account = self.portfolio.account(venue=self.config.venue)

        if self.config.warmup_mode:
            start_time = datetime.now(pytz.UTC) - self.config.warmup_timedelta
            self.request_bars(
                self.config.bar_type,  # 请求线类型
                start_time,  # 请求预热时间范围开始时间(为了实时性最好不要指定结束时间)
                limit=self.config.warmup_bars,  # 最多warmup_bars根K线
                callback=lambda _: self.subscribe_bars(self.config.bar_type),  # 预热完成后订阅K线
            )
        else:
            self.subscribe_bars(self.config.bar_type)

        if self.config.enable_redis:
            self.redis_client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                db=self.config.redis_db,
                decode_responses=False,
                max_connections=10,
                socket_timeout=5,
            )
            self.redis_client.delete(self.klines_key)
            self.redis_client.delete(self.analysis_key)
            self.redis_client.delete(self.orders_key)
            self.redis_client.delete(self.tech_key)

    def on_bar(self, bar: Bar):
        """
        处理K线数据，更新持仓价格，更新权益，检查止损条件
        :param bar: K线数据
        """
        if not self.indicators_initialized():
            return
        self.current_price = bar.close
        if self.hold_price:
            return_ratio = (self.current_price - self.hold_price) / self.hold_price
            if not self.portfolio.is_flat(self.config.instrument_id) and return_ratio < -self.config.stop_loss_pct:
                print(f"止损触发，当前持仓比例：{self.get_position()}")
                self.close_all_positions(self.config.instrument_id)
                self.hold_price = None
            if not self.portfolio.is_flat(self.config.instrument_id) and return_ratio > self.config.stop_profit_pct:
                self.close_all_positions(self.config.instrument_id)
                self.hold_price = None

        if self.config.enable_redis:
            kline_data = {
                "datetime": bar.ts_init,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume),
            }
            self.redis_client.lpush(self.klines_key, self.encoder.encode(kline_data))
            self.redis_client.ltrim(self.klines_key, 0, self.config.max_period - 1)

            equity_value = self.get_equity()
            if self.equity_value is None:
                return_value = 0
            else:
                return_value = equity_value - self.equity_value
            self.equity_value = float(equity_value)
            analysis_data = {
                "datetime": bar.ts_init,
                "equity": float(equity_value),
                "return": return_value,
            }
            self.redis_client.lpush(self.analysis_key, self.encoder.encode(analysis_data))
            self.redis_client.ltrim(self.analysis_key, 0, self.config.max_period - 1)

    def get_equity(self) -> Decimal:
        """
        获取当前账户权益
        :return: 资益金额
        """
        equity = self.portfolio.equity(venue=self.config.venue)
        equity_amount = equity[self.config.quote_currency]
        return equity_amount

    def set_position(self, target_ratio: float):
        """
        设置持仓比例
        :param target_ratio: 目标持仓比例
        """
        if abs(target_ratio) > self.config.max_position_ratio:
            target_ratio = self.config.max_position_ratio if target_ratio > 0 else -self.config.max_position_ratio
        equity_value = self.get_equity()
        target_position = Decimal(target_ratio) * equity_value  # 目标持仓金额
        current_position = self.get_position() * equity_value  # 当前持仓金额
        delta_value = target_position - current_position
        side = OrderSide.BUY if delta_value > 0 else OrderSide.SELL
        # print(
        #     f"target_ratio: {target_ratio},current_ratio: {self.get_position()}, delta_value: {delta_value}, side: {side}")

        order = self.order_factory.market(
            self.config.instrument_id,
            side,
            Quantity(abs(delta_value), Decimal("2")),
            quote_quantity=True,
        )
        self.submit_order(order)
        self.hold_price = self.current_price

    def get_position(self):
        """
        获取当前持仓比例
        :return: 持仓比例
        """
        mark_values = self.portfolio.mark_values(self.config.venue, self.account.id)
        equity = self.portfolio.equity(venue=self.config.venue)
        equity_quote = equity[self.config.quote_currency]
        if not mark_values:
            return 0
        return mark_values[self.config.quote_currency] / equity_quote

    def on_order_filled(self, event: OrderFilled):
        self.log.info(
            f"Filled {event.last_qty} @ {event.last_px} "
            f"({event.liquidity_side}) commission={event.commission}",
        )

        order_data = {
            "datetime": event.ts_event,
            "trade_id": str(event.trade_id),
            "side": "BUY" if event.order_side == OrderSide.BUY else "SELL",
            "price": float(event.last_px),
            "quantity": float(event.last_qty),
            "commission": float(event.commission),
        }

        if self.config.enable_redis:
            self.redis_client.lpush(self.orders_key, self.encoder.encode(order_data))
            self.redis_client.ltrim(self.orders_key, 0, self.config.max_period - 1)

    def on_stop(self):
        """
        策略停止时，关闭所有持仓
        """
        self.close_all_positions(self.config.instrument_id)
        self.hold_price = None
