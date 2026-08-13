import tomllib
from pathlib import Path
from typing import Any
from datetime import datetime

from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.trading.config import ImportableStrategyConfig
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.backtest.node import BacktestDataConfig
from nautilus_trader.backtest.node import BacktestVenueConfig
from nautilus_trader.backtest.node import BacktestEngineConfig
from nautilus_trader.backtest.node import BacktestRunConfig
from nautilus_trader.backtest.node import BacktestNode


class Backtest:
    node: BacktestNode  # 回测节点
    config: dict[str, Any]  # 回测配置

    def __init__(self, config_path: str):
        """
        初始化回测运行器
        :param config_path: 配置文件路径
        """
        with open(config_path, "rb") as f:
            self.config = tomllib.load(f)

        self.venues: list[BacktestVenueConfig] = []  # 交易所配置
        self.data: list[BacktestDataConfig] = []  # 数据配置
        self.strategies: list[ImportableStrategyConfig] = []  # 策略配置

    def load_venues(self):
        """加载交易所配置"""
        for venue_config in self.config["venues"]:
            self.venues.append(
                BacktestVenueConfig(
                    name=venue_config["name"],
                    oms_type=venue_config["oms_type"],
                    account_type=venue_config["account_type"],
                    base_currency=venue_config["base_currency"],
                    starting_balances=venue_config["starting_balances"],
                )
            )

    def load_data(self):
        """加载数据配置"""
        for data_config in self.config["data"]:
            mapping = {"Klines": Bar, "Bar": Bar, "TradeTick": TradeTick, "QuoteTick": QuoteTick}
            data_cls = mapping.get(data_config["data_cls"])
            if data_cls is None:
                raise ValueError(f"Unsupported data class: {data_config['data_cls']}")
            self.data.append(
                BacktestDataConfig(
                    catalog_path=data_config["catalog_path"],
                    data_cls=data_cls,
                    instrument_id=InstrumentId.from_str(data_config["instrument_id"]),
                    start_time=data_config["start_time"],
                    end_time=data_config["end_time"],
                )
            )

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

    def run(self, log_level: str = "INFO"):
        """
        运行回测
        :param log_level: 日志级别，默认INFO
        """
        if not self.venues:
            raise ValueError("缺少交易所配置，运行前请先加载交易所配置")
        if not self.data:
            raise ValueError("缺少数据配置，运行前请先加载数据配置")
        if not self.strategies:
            raise ValueError("缺少策略配置，运行前请先加载策略配置")

        run_config = BacktestRunConfig(
            engine=BacktestEngineConfig(
                strategies=self.strategies,
                logging=LoggingConfig(log_level=log_level),
            ),
            data=self.data,
            venues=self.venues,
            dispose_on_completion=False,
        )
        self.node = BacktestNode(configs=[run_config])
        self.node.run()

    def generate_report(self):
        """生成回测报告"""
        analysis_config = self.config["analysis"]
        engine = self.node.get_engines()[0]
        dir_name = f"{analysis_config['file_prefix']}_{datetime.now().strftime("%Y%m%d_%H%M%S")}"
        dir_path = analysis_config['output_path'] / Path(dir_name)
        dir_path.mkdir(exist_ok=True)
        create_tearsheet(
            engine=engine,
            output_path=dir_path / "performance_report.html",
        )

        account_reports = []
        for venue in analysis_config["venues"]:
            account_reports.append(engine.trader.generate_account_report(Venue(venue)))
        positions_report = engine.trader.generate_positions_report()
        order_fills_report = engine.trader.generate_order_fills_report()

        account_report_paths = []
        for venue in analysis_config["venues"]:
            account_report_paths.append(dir_path / f"account_report({venue}).csv")
        positions_report_path = dir_path / f"positions_report.csv"
        order_fills_report_path = dir_path / f"order_fills_report.csv"

        for account_report, account_report_path in zip(account_reports, account_report_paths):
            account_report.to_csv(account_report_path, index=False, encoding='utf-8-sig')
        positions_report.to_csv(positions_report_path, index=False, encoding='utf-8-sig')
        order_fills_report.to_csv(order_fills_report_path, index=False, encoding='utf-8-sig')

    def dispose(self):
        """释放资源"""
        self.node.dispose()
