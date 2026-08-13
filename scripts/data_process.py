from pathlib import Path
import pandas as pd
import os
import shutil

from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.test_kit.providers import TestInstrumentProvider
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.wranglers import BarDataWrangler, TradeTickDataWrangler, QuoteTickDataWrangler
from nautilus_trader.model.data import BarType


class BacktestDataProcessor:
    def __init__(self, instrument: CurrencyPair):
        """
        初始化数据处理器
        :param instrument: 交易对
        """
        self.instrument = instrument
        self.data_path = Path(os.environ.get("NAUTILUS_DATA_DIR", "../data")).expanduser()

    @staticmethod
    def read_klines_data(file_path: Path | str, col_map: dict, header=None):
        """
        读取K线数据CSV文件并返回DataFrame
        数据格式: (open_time, open, high, low, close, volume)
        :param file_path: Klines文件路径
        :param col_map: 列索引到列名的映射字典
        :param header: CSV文件的表头行索引，默认为None表示没有表头
        :return: Klines的DataFrame
        """
        df = pd.DataFrame(pd.read_csv(file_path, header=header))
        use_cols = sorted(col_map.keys())
        df = df.iloc[:, use_cols]
        df.columns = [col_map[idx] for idx in use_cols]
        if len(str(df["open_time"].iloc[0]))==16:
            df["open_time"] = pd.to_datetime(df["open_time"], unit="us")
        else:
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df.set_index('open_time').sort_index()
        return df

    @staticmethod
    def read_trades_data(file_path: Path | str, col_map: dict, header=None):
        """
        读取tradeTicks数据CSV文件并返回DataFrame
        数据格式: (trade_id, price, quantity, time, side)
        :param file_path: tradeTicks文件路径
        :param col_map: 列索引到列名的映射字典
        :param header: CSV文件的表头行索引，默认为None表示没有表头
        :return: tradeTicks的DataFrame
        """
        df = pd.DataFrame(pd.read_csv(file_path, header=header))
        use_cols = sorted(col_map.keys())
        df = df.iloc[:, use_cols]
        df.columns = [col_map[idx] for idx in use_cols]
        df['side'] = df['side'].replace({True: 'SELL', False: 'BUY'})
        if len(str(df["time"].iloc[0]))==16:
            df["time"] = pd.to_datetime(df["time"], unit="us")
        else:
            df["time"] = pd.to_datetime(df["time"], unit="ms")
        df = df.set_index('time').sort_index()
        return df

    @staticmethod
    def read_quotes_data(file_path: Path | str, col_map: dict, header=None):
        """
        读取quoteTicks数据CSV文件并返回DataFrame
        数据格式: (timestamp, bid_price, ask_price, volume)
        :param file_path: quoteTicks文件路径
        :param col_map: 列索引到列名的映射字典
        :param header: CSV文件的表头行索引，默认为None表示没有表头
        :return: quoteTicks的DataFrame
        """
        df = pd.DataFrame(pd.read_csv(file_path, header=header))
        use_cols = sorted(col_map.keys())
        df = df.iloc[:, use_cols]
        df.columns = [col_map[idx] for idx in use_cols]
        if len(str(df["timestamp"].iloc[0]))==16:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="us")
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index('timestamp').sort_index()
        return df

    def process_klines(self, col_map: dict, interval="1-MINUTE"):
        """
        处理K线数据，将CSV文件转换为Bar对象并写入ParquetDataCatalog
        :param col_map: 列索引到列名的映射字典
        :param interval: K线时间间隔
        """
        klines_path = self.data_path / self.instrument.id.value / "raw" / "klines"
        catalog_path = self.data_path / self.instrument.id.value / "catalog"
        if catalog_path.exists():
            shutil.rmtree(catalog_path)
        catalog_path.mkdir(parents=True)
        catalog = ParquetDataCatalog(catalog_path)
        catalog.write_data([self.instrument])
        bar_type = BarType.from_str(f"{self.instrument.id}-{interval}-LAST-EXTERNAL")
        wrangler = BarDataWrangler(bar_type, self.instrument)
        for file_path in klines_path.iterdir():
            if file_path.is_file() and (file_path.suffix == ".csv" or file_path.name.endswith(".csv.gz")):
                bars = wrangler.process(self.read_klines_data(file_path, col_map))
                catalog.write_data(bars)

    def process_trades(self, col_map: dict):
        """
        处理TradeTicks数据，将CSV文件转换为TradeTick对象并写入ParquetDataCatalog
        :param col_map: 列索引到列名的映射字典
        """
        trades_path = self.data_path / self.instrument.id.value / "raw" / "trades"
        catalog_path = self.data_path / self.instrument.id.value / "catalog"
        if catalog_path.exists():
            shutil.rmtree(catalog_path)
        catalog_path.mkdir(parents=True)
        catalog = ParquetDataCatalog(catalog_path)
        catalog.write_data([self.instrument])
        wrangler = TradeTickDataWrangler(self.instrument)
        for file_path in trades_path.iterdir():
            if file_path.is_file() and (file_path.suffix == ".csv" or file_path.name.endswith(".csv.gz")):
                ticks = wrangler.process(self.read_trades_data(file_path, col_map))
                catalog.write_data(ticks)

    def process_quotes(self, col_map: dict):
        """
        处理QuoteTicks数据，将CSV文件转换为QuoteTick对象并写入ParquetDataCatalog
        :param col_map: 列索引到列名的映射字典
        """
        quotes_path = self.data_path / self.instrument.id.value / "raw" / "quotes"
        catalog_path = self.data_path / self.instrument.id.value / "catalog"
        if catalog_path.exists():
            shutil.rmtree(catalog_path)
        catalog_path.mkdir(parents=True)
        catalog = ParquetDataCatalog(catalog_path)
        catalog.write_data([self.instrument])
        wrangler = QuoteTickDataWrangler(self.instrument)
        for file_path in quotes_path.iterdir():
            if file_path.is_file() and (file_path.suffix == ".csv" or file_path.name.endswith(".csv.gz")):
                ticks = wrangler.process(self.read_quotes_data(file_path, col_map))
                catalog.write_data(ticks)


def run():
    # instrument = TestInstrumentProvider.btcusdt_binance()
    instrument=TestInstrumentProvider.ethusdt_binance()
    processor = BacktestDataProcessor(instrument)
    cols = {0: "open_time", 1: "open", 2: "high", 3: "low", 4: "close", 5: "volume"}
    processor.process_klines(cols, interval="1-MINUTE")


if __name__ == "__main__":
    run()
