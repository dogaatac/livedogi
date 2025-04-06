# data_manager.py
from binance.client import Client
import pandas as pd
from config import CONFIGS, DATA_FILES
from settings import SYMBOLS
from utils import save_data, load_data
from datetime import datetime, timedelta
import threading
import time
import logging

logging.basicConfig(
    filename='trades.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class DataManager:
    def __init__(self, api_key, api_secret):
        self.client = Client(api_key, api_secret)
        self.client.API_URL = 'https://fapi.binance.com'
        self.trades = {symbol: {name: [] for name in CONFIGS} for symbol in SYMBOLS}
        self.balances = {symbol: {name: CONFIGS[name]["INITIAL_BALANCE"] for name in CONFIGS} for symbol in SYMBOLS}
        self.stats = {symbol: {name: {"total_trades": 0, "monthly_trades": 0, "tp_count": 0, "sl_count": 0, "last_month": datetime.now().month} for name in CONFIGS} for symbol in SYMBOLS}
        self.current_prices = {symbol: 0.0 for symbol in SYMBOLS}
        self.load_data()
        self.start_price_updater()

    def load_data(self):
        for symbol in SYMBOLS:
            for name in CONFIGS:
                default_data = {
                    "trades": [],
                    "balance": CONFIGS[name]["INITIAL_BALANCE"],
                    "stats": {"total_trades": 0, "monthly_trades": 0, "tp_count": 0, "sl_count": 0, "last_month": datetime.now().month}
                }
                filename = DATA_FILES[name].replace(".json", f"_{symbol}.json")
                data = load_data(filename, default_data)
                self.trades[symbol][name] = data["trades"]
                self.balances[symbol][name] = data["balance"]
                self.stats[symbol][name] = data["stats"]

    def save_data(self, symbol, config_name, engine):
        data = {
            "positions": engine.positions[symbol][config_name],
            "trades": self.trades[symbol][config_name],
            "balance": self.balances[symbol][config_name],
            "used_pivots": list(engine.used_pivots[symbol][config_name]),
            "sweeps_pl": engine.sweeps_pl[symbol][config_name],
            "sweeps_ph": engine.sweeps_ph[symbol][config_name],
            "stats": self.stats[symbol][config_name]
        }
        filename = DATA_FILES[config_name].replace(".json", f"_{symbol}.json")
        save_data(filename, data)
        logging.info(f"Veriler kaydedildi: {symbol}/{config_name}")

    def start_price_updater(self):
        def update_prices():
            while True:
                for symbol in SYMBOLS:
                    try:
                        ticker = self.client.futures_symbol_ticker(symbol=symbol)
                        price = float(ticker['price'])
                        self.current_prices[symbol] = price
                    except Exception as e:
                        logging.error(f"Futures fiyat güncelleme hatası ({symbol}): {e}")
                time.sleep(0.5)

        price_thread = threading.Thread(target=update_prices)
        price_thread.daemon = True
        price_thread.start()

    def close_position(self, symbol, config_name, trade, engine):
        self.balances[symbol][config_name] += trade['profit']
        self.trades[symbol][config_name].append(trade)
        self.update_stats(symbol, config_name, trade)
        self.save_data(symbol, config_name, engine)

    def update_stats(self, symbol, config_name, trade):
        self.stats[symbol][config_name]["total_trades"] += 1
        if datetime.now().month == self.stats[symbol][config_name]["last_month"]:
            self.stats[symbol][config_name]["monthly_trades"] += 1
        else:
            self.stats[symbol][config_name]["monthly_trades"] = 1
            self.stats[symbol][config_name]["last_month"] = datetime.now().month
        if trade["profit"] > 0:
            self.stats[symbol][config_name]["tp_count"] += 1
        else:
            self.stats[symbol][config_name]["sl_count"] += 1

    def get_stats(self, symbol, config_name, period=None):
        trades = pd.DataFrame(self.trades[symbol][config_name])
        if trades.empty:
            return f"[{symbol}/{config_name}] Henüz işlem yok.", trades
        
        if period:
            now = datetime.now()
            if period == "1ay":
                start = now - timedelta(days=30)
            elif period == "3ay":
                start = now - timedelta(days=90)
            elif period == "6ay":
                start = now - timedelta(days=180)
            trades['exit_time'] = pd.to_datetime(trades['exit_time'])
            trades = trades[trades['exit_time'] >= start]

        total_trades = len(trades)
        tp_count = len(trades[trades['profit'] > 0])
        sl_count = len(trades[trades['profit'] < 0])
        total_profit = trades['profit'].sum()
        return (f"[{symbol}/{config_name}] Performans ({period or 'Tüm Zaman'}):\n"
                f"Toplam İşlem: {total_trades}\n"
                f"TP: {tp_count}, SL: {sl_count}\n"
                f"Toplam Kâr/Zarar: {total_profit:.2f} USD"), trades

    def get_last_trades(self, symbol, config_name, count=5):
        trades = self.trades[symbol][config_name][-count:]
        if not trades:
            return f"[{symbol}/{config_name}] Henüz işlem yok."
        result = f"[{symbol}/{config_name}] Son {min(count, len(trades))} İşlem:\n"
        for trade in trades:
            result += (f"{trade['type'].capitalize()} - Entry: {trade['entry_price']}, "
                       f"Exit: {trade['exit_price']}, Profit: {trade['profit']:.2f}, "
                       f"Time: {trade['exit_time']}\n")
        return result

    def get_current_price(self, symbol):
        return self.current_prices.get(symbol, 0.0)

    def get_current_futures_price(self, symbol):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            logging.error(f"Futures fiyat alınamadı [{symbol}]: {e}")
            return None

    def handle_query(self, symbol, bot_name, command, engine):
        if symbol not in SYMBOLS:
            return f"Geçersiz symbol ({', '.join(SYMBOLS)})."
        if bot_name not in CONFIGS:
            return "Geçersiz bot adı (safe, mid, agresif)."
        
        if command == "kasa":
            return (f"[{symbol}/{bot_name}] Güncel Kasa: {self.balances[symbol][bot_name]:.2f} USD "
                    f"(Başlangıç: {CONFIGS[bot_name]['INITIAL_BALANCE']} USD)\n"
                    f"Anlık Fiyat: {self.get_current_price(symbol):.2f} USDT")
        elif command == "işlem":
            return self.get_last_trades(symbol, bot_name)
        elif command.startswith("performans"):
            period = command.split()[-1] if len(command.split()) > 1 else None
            if period not in ["1ay", "3ay", "6ay", None]:
                return "Geçersiz dönem (1ay, 3ay, 6ay)."
            stats, _ = self.get_stats(symbol, bot_name, period)
            return stats
        elif command == "durum":
            open_pos = len(engine.positions[symbol][bot_name])
            pending_sweeps = len(engine.sweeps_pl[symbol][bot_name]) + len(engine.sweeps_ph[symbol][bot_name])
            return (f"[{symbol}/{bot_name}] Durum:\n"
                    f"Anlık Fiyat: {self.get_current_price(symbol):.2f} USDT\n"
                    f"Açık Pozisyon: {open_pos}\n"
                    f"Bekleyen Sweep: {pending_sweeps}\n"
                    f"Aylık İşlem: {self.stats[symbol][bot_name]['monthly_trades']}")
        else:
            return "Geçersiz komut (kasa, işlem, performans, durum)."