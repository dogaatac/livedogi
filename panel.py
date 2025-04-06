# panel.py
import tkinter as tk
from tkinter import ttk
import threading
from data_manager import DataManager
from engine import TradingEngine
from settings import SYMBOLS
from config import API_KEY, API_SECRET, CONFIGS
from notifications import Notifier
from plotter import Plotter

class TradingPanel:
    def __init__(self, root):
        self.root = root
        self.root.title("Trading Bot Panel")
        self.root.geometry("1200x600")
        self.data_manager = DataManager(API_KEY, API_SECRET)
        self.notifier = Notifier()
        self.plotter = Plotter()
        self.engine = TradingEngine(API_KEY, API_SECRET, self.data_manager, self.notifier, self.plotter)
        self.setup_ui()
        self.start_engine()
        self.update_ui()

    def setup_ui(self):
        self.pair_frame = ttk.LabelFrame(self.root, text="Aktif Pairler", padding=5)
        self.pair_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        self.pair_list = tk.Text(self.pair_frame, height=30, width=30)
        self.pair_list.pack(fill="both", expand=True)

        self.notify_frame = ttk.LabelFrame(self.root, text="Bildirimler", padding=5)
        self.notify_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        self.notify_text = tk.Text(self.notify_frame, height=30, width=50)
        self.notify_text.pack(fill="both", expand=True)

        self.trade_frame = ttk.LabelFrame(self.root, text="İşlemler ve Performans", padding=5)
        self.trade_frame.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        self.trade_text = tk.Text(self.trade_frame, height=30, width=50)
        self.trade_text.pack(fill="both", expand=True)

        self.root.columnconfigure((0, 1, 2), weight=1)
        self.root.rowconfigure(0, weight=1)

    def start_engine(self):
        self.engine_thread = threading.Thread(target=self.engine.start)
        self.engine_thread.daemon = True
        self.engine_thread.start()

    def update_ui(self):
        pair_info = ""
        for symbol in SYMBOLS:
            price = self.data_manager.get_current_price(symbol)
            pair_info += f"{symbol}: {price:.2f} USDT\n"
        self.pair_list.delete(1.0, tk.END)
        self.pair_list.insert(tk.END, pair_info)

        self.notify_text.delete(1.0, tk.END)
        for msg in self.notifier.messages[-20:]:
            self.notify_text.insert(tk.END, f"{msg}\n")

        trade_info = ""
        for symbol in SYMBOLS:
            for config_name in CONFIGS:
                stats, trades = self.data_manager.get_stats(symbol, config_name)
                trade_info += stats + "\n"
                last_trades = self.data_manager.get_last_trades(symbol, config_name, count=3)
                trade_info += last_trades + "\n\n"
        self.trade_text.delete(1.0, tk.END)
        self.trade_text.insert(tk.END, trade_info)

        self.root.after(1000, self.update_ui)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    root = tk.Tk()
    app = TradingPanel(root)
    app.run()