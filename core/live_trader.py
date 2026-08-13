from typing import Any
import tomllib

from nautilus_trader.live.node import TradingNode
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import BarType
from nautilus_trader.common.config import InstrumentProviderConfig
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.adapters.okx.constants import OKX
from nautilus_trader.adapters.okx.config import OKXDataClientConfig
from nautilus_trader.adapters.okx.config import OKXExecClientConfig
from nautilus_trader.adapters.okx.factories import OKXLiveDataClientFactory
from nautilus_trader.adapters.okx.factories import OKXLiveExecClientFactory
from nautilus_trader.core.nautilus_pyo3 import OKXContractType
from nautilus_trader.core.nautilus_pyo3 import OKXEnvironment
from nautilus_trader.core.nautilus_pyo3 import OKXInstrumentType
from nautilus_trader.core.nautilus_pyo3 import OKXMarginMode


class LiveTrader:
    node: TradingNode  # 交易节点
    node_config: TradingNodeConfig  # 交易节点配置

    def __init__(self, config_path: str):
        """
        初始化交易节点
        :param config_path: 配置文件路径
        """
        with open(config_path, "rb") as f:
            self.config = tomllib.load(f)

        self.data_clients: dict = {}  # 数据客户端配置
        self.exec_clients: dict = {}  # 执行客户端配置
        self.strategies: list[ImportableStrategyConfig] = []  # 策略配置
        self.venues_enabled: list[str] = []  # 启用的交易所

    def load_okx_client(self, base_url_http: str | None = None, base_url_ws: str | None = None):
        """
        加载OKX客户端
        :param base_url_http: HTTP基础URL
        :param base_url_ws: WebSocket基础URL
        """
        okx_config = self.config["okx"]
        environment = OKXEnvironment.DEMO if okx_config["environment"] == "DEMO" else OKXEnvironment.LIVE
        instrument_types = []
        contract_types = []

        instrument_mapping = {
            "ANY": OKXInstrumentType.ANY,
            "SPOT": OKXInstrumentType.SPOT,
            "MARGIN": OKXInstrumentType.MARGIN,
            "SWAP": OKXInstrumentType.SWAP,
            "FUTURES": OKXInstrumentType.FUTURES,
            "OPTION": OKXInstrumentType.OPTION,
            "EVENTS": OKXInstrumentType.EVENTS
        }

        contract_mapping = {
            "NONE": OKXContractType.NONE,
            "LINEAR": OKXContractType.LINEAR,
            "INVERSE": OKXContractType.INVERSE,
        }

        for instrument_type in okx_config["instrument_types"]:
            instrument_types.append(instrument_mapping[instrument_type])
        for contract_type in okx_config["contract_types"]:
            contract_types.append(contract_mapping[contract_type])

        self.data_clients[OKX] = OKXDataClientConfig(
            api_key=okx_config["api_key"],
            api_secret=okx_config["api_secret"],
            api_passphrase=okx_config["api_passphrase"],
            base_url_http=base_url_http,
            base_url_ws=base_url_ws,
            environment=environment,
            instrument_provider=InstrumentProviderConfig(load_all=True),
            instrument_types=tuple(instrument_types),
            contract_types=tuple(contract_types),
            proxy_url=okx_config["proxy_url"],
        )

        self.exec_clients[OKX] = OKXExecClientConfig(
            api_key=okx_config["api_key"],
            api_secret=okx_config["api_secret"],
            api_passphrase=okx_config["api_passphrase"],
            base_url_http=base_url_http,
            base_url_ws=base_url_ws,
            environment=environment,
            instrument_provider=InstrumentProviderConfig(load_all=True),
            instrument_types=tuple(instrument_types),
            contract_types=tuple(contract_types),
            proxy_url=okx_config["proxy_url"],
        )

        self.venues_enabled.append(OKX)

    def load_strategies(self):
        """加载策略配置"""
        for strategy in self.config["strategies"]:
            strategy_config = strategy["config"]
            strategy_config["instrument_id"] = InstrumentId.from_str(strategy_config["instrument_id"])
            strategy_config["venue"] = Venue(strategy_config["venue"])
            strategy_config["bar_type"] = BarType.from_str(strategy_config["bar_type"])
            strategy_config["base_currency"] = Currency.from_str(strategy_config["base_currency"])
            strategy_config["quote_currency"] = Currency.from_str(strategy_config["quote_currency"])
            self.strategies.append(
                ImportableStrategyConfig(
                    strategy_path=strategy["strategy_path"],
                    config_path=strategy["config_path"],
                    config=strategy_config
                ),
            )

    def run(self, log_level="INFO"):
        """运行交易节点"""
        node_config = TradingNodeConfig(
            data_clients=self.data_clients,
            exec_clients=self.exec_clients,
            strategies=self.strategies,
            logging=LoggingConfig(log_level=log_level)
        )
        self.node = TradingNode(config=node_config)
        if OKX in self.venues_enabled:
            self.node.add_data_client_factory(OKX, OKXLiveDataClientFactory)
            self.node.add_exec_client_factory(OKX, OKXLiveExecClientFactory)
        self.node.build()
        self.node.run()

    def dispose(self):
        """释放交易节点资源"""
        self.node.dispose()
