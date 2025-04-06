# core.py
import logging
import time
from binance.client import Client
from config import API_KEY, API_SECRET
from data_manager import DataManager
from notifications import Notifier
from plotter import Plotter
from engine import TradingEngine

# Loglama yapılandırması
logging.basicConfig(
    filename='trades.log',  # Loglar bu dosyaya kaydedilecek
    level=logging.INFO,     # INFO seviyesinde loglama
    format='%(asctime)s - %(message)s',  # Zaman damgası ve mesaj formatı
    datefmt='%Y-%m-%d %H:%M:%S'  # Tarih formatı
)

class Core:
    def __init__(self):
        self.client = Client(API_KEY, API_SECRET)
        self.data_manager = DataManager(API_KEY, API_SECRET)
        self.notifier = Notifier()
        self.plotter = Plotter()
        self.engine = TradingEngine(API_KEY, API_SECRET, self.data_manager, self.notifier, self.plotter)

    def execute_trade(self, symbol, trade_type, price, quantity):
        """
        Bir trade'i yürütür ve tamamlandığında loglar.
        
        Args:
            symbol (str): İşlem çifti (örneğin, 'BTCUSDT')
            trade_type (str): İşlem türü ('buy' veya 'sell')
            price (float): İşlem fiyatı
            quantity (float): İşlem miktarı
        """
        # Trade'i simüle et
        time.sleep(1)  # İşlem süresini simüle etmek için
        trade_details = {
            'symbol': symbol,
            'type': trade_type,
            'price': price,
            'quantity': quantity,
            'timestamp': time.time()
        }
        
        # Trade tamamlandığında logla ve terminale yaz
        logging.info(f"Trade completed: {trade_details}")
        print(f"Trade executed: {trade_details}")

        # Gerçek trade işlemi burada uygulanabilir
        # Örneğin: self.client.create_order(...)

    def start(self):
        """Sistemi başlatır ve WebSocket bağlantısını aktif eder."""
        print("Trading sistemi başlatılıyor...")
        self.engine.start()
        print("Sistem çalışıyor. Çıkmak için Ctrl+C kullanın.")
        
        # Sürekli çalışması için bir döngü
        try:
            while True:
                time.sleep(1)  # CPU'yu yormamak için
        except KeyboardInterrupt:
            print("\nSistem durduruluyor...")
            self.engine.stop()
            print("Sistem durduruldu.")

# Örnek kullanım
if __name__ == "__main__":
    core = Core()
    # Örnek trade'leri çalıştır (isteğe bağlı, test için)
    core.execute_trade('BTCUSDT', 'buy', 50000, 0.1)
    core.execute_trade('ETHUSDT', 'sell', 3000, 0.5)
    # Gerçek zamanlı sistemi başlat
    core.start()