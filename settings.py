# settings.py

# Plotlama ayarları (her bot için aynı)
PLOT_CANDLES_BEFORE = 10
PLOT_CANDLES_AFTER = 5
PLOT_TIMEFRAME = "15m"  # Mum zaman dilimi

# Genel ayarlar
SYMBOLS = ["BTCUSDT","ETHUSDT","BNBUSDT"]  # İşlem çiftleri
DATA_WINDOW = 250  # Kaç mum geriye bakılacak
PROXIMITY_THRESHOLD = 0.001  # Pivot yakınlık eşiği (%0.1)