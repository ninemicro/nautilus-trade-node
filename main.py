from warnings import filterwarnings

from core import Backtest, LiveTrader

filterwarnings("ignore")


def run_backtest():
    """运行回测"""
    backtest = Backtest("configs/backtest/rsi_mean_btc.toml")
    backtest.load_venues()
    backtest.load_data()
    backtest.load_strategies()
    try:
        backtest.run()
        backtest.generate_report()
    finally:
        backtest.dispose()


def run_live_trader():
    """运行实盘交易"""
    live_trader = LiveTrader("configs/live/macd_cross_btc_demo.toml")
    live_trader.load_okx_client()
    live_trader.load_strategies()
    try:
        live_trader.run()
    finally:
        live_trader.dispose()


if __name__ == "__main__":
    run_backtest()
    # run_live_trader()
