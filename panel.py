# panel.py
import os
import time
import threading
from data_manager import DataManager
from engine import TradingEngine
from settings import SYMBOLS
from config import API_KEY, API_SECRET, CONFIGS
from notifications import Notifier
from plotter import Plotter

class TradingPanel:
    def __init__(self):
        self.data_manager = DataManager(API_KEY, API_SECRET)
        self.notifier = Notifier()
        self.plotter = Plotter()
        self.engine = TradingEngine(API_KEY, API_SECRET, self.data_manager, self.notifier, self.plotter)
        self.running = True
        self.start_engine()

    def clear_screen(self):
        # Terminal ekranını temizler (Windows ve Unix uyumlu)
        os.system('cls' if os.name == 'nt' else 'clear')

    def start_engine(self):
        # TradingEngine'ı ayrı bir thread'de başlatır
        self.engine_thread = threading.Thread(target=self.engine.start)
        self.engine_thread.daemon = True
        self.engine_thread.start()

    def display_panel(self):
        while self.running:
            self.clear_screen()

            # 1. Bölüm: Fiyatlar
            print("=== AKTİF FİYATLAR ===")
            for symbol in SYMBOLS:
                price = self.data_manager.get_current_price(symbol)
                print(f"{symbol}: {price:.2f} USDT")
            print()

            # 2. Bölüm: Bildirimler (Log Ekranı)
            print("=== BİLDİRİMLER ===")
            for msg in self.notifier.messages[-10:]:  # Son 10 bildirimi göster
                print(msg)
            print()

            # 3. Bölüm: İşlemler ve Performans
            print("=== İŞLEMLER VE PERFORMANS ===")
            for symbol in SYMBOLS:
                for config_name in CONFIGS:
                    stats, _ = self.data_manager.get_stats(symbol, config_name)
                    print(stats)
                    last_trades = self.data_manager.get_last_trades(symbol, config_name, count=3)
                    print(last_trades)
                    print()
            print("Çıkmak için Ctrl+C kullanın.")
            
            # Her saniye güncelle
            time.sleep(1)

    def run(self):
        try:
            self.display_panel()
        except KeyboardInterrupt:
            print("\nPanel kapatılıyor...")
            self.running = False
            self.engine.stop()
            print("Panel kapatıldı.")

if __name__ == "__main__":
    panel = TradingPanel()
    panel.run()