# core.py
import signal
import sys
from engine import TradingEngine
from notifications import Notifier
from plotter import Plotter
from data_manager import DataManager
from config import API_KEY, API_SECRET

# Nesneleri global olarak tanımla
notifier = Notifier()
plotter = Plotter()
data_manager = DataManager(API_KEY, API_SECRET)
engine = TradingEngine(API_KEY, API_SECRET, data_manager, notifier, plotter)

def signal_handler(sig, frame):
    """Ctrl+C veya sistem sinyali alındığında çağrılır."""
    print("\nCore servis kapatılıyor...")
    engine.stop()  # Websocket bağlantısını kapat
    print("Core servis tamamen kapatıldı.")
    sys.exit(0)

if __name__ == "__main__":
    # Sinyal yakalayıcıyı kaydet (Ctrl+C için)
    signal.signal(signal.SIGINT, signal_handler)  # Windows ve Unix için Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Sistem sonlandırma sinyali

    print("Core servis başlatıldı. Çıkmak için Ctrl+C kullanın.")
    engine.start()
    try:
        while True:
            pass  # Ana döngü
    except Exception as e:
        print(f"Beklenmeyen bir hata oluştu: {e}")
    finally:
        engine.stop()  # Her durumda websocket’i kapat
        sys.exit(0)