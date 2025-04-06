# core.py
import logging
import time
from binance.client import Client
from config import API_KEY, API_SECRET
from data_manager import DataManager
from notifications import Notifier
from plotter import Plotter
from engine import TradingEngine

logging.basicConfig(
    filename='trades.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class Core:
    def __init__(self):
        self.client = Client(API_KEY, API_SECRET)
        self.data_manager = DataManager(API_KEY, API_SECRET)
        self.notifier = Notifier()
        self.plotter = Plotter()
        self.engine = TradingEngine(API_KEY, API_SECRET, self.data_manager, self.notifier, self.plotter)

    def execute_trade(self, symbol, trade_type, price, quantity):
        time.sleep(1)
        trade_details = {
            'symbol': symbol,
            'type': trade_type,
            'price': price,
            'quantity': quantity,
            'timestamp': time.time()
        }
        logging.info(f"Trade completed: {trade_details}")
        print(f"Trade executed: {trade_details}")

    def start(self):
        print("Trading sistemi başlatılıyor...")
        self.engine.start()
        print("Sistem çalışıyor. Çıkmak için Ctrl+C kullanın.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nSistem durduruluyor...")
            self.engine.stop()
            print("Sistem durduruldu.")

if __name__ == "__main__":
    core = Core()
    core.execute_trade('BTCUSDT', 'buy', 50000, 0.1)
    core.execute_trade('ETHUSDT', 'sell', 3000, 0.5)
    core.start()