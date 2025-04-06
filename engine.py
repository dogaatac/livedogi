# engine.py
from binance import ThreadedWebsocketManager
import pandas as pd
import logging
import threading
import time
from config import CONFIGS
from settings import SYMBOLS, DATA_WINDOW, PROXIMITY_THRESHOLD
from utils import pivot_high, pivot_low
from datetime import datetime, timedelta

logging.basicConfig(
    filename='trades.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class TradingEngine:
    def __init__(self, api_key, api_secret, data_manager, notifier, plotter):
        self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret, testnet=False)
        self.twm.start()
        self.data = {
            symbol: {
                name: pd.DataFrame(columns=['open_time', 'open', 'high', 'low', 'close']).astype({
                    'open_time': 'datetime64[ns]', 'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64'
                }) for name in CONFIGS
            } for symbol in SYMBOLS
        }
        self.positions = {symbol: {name: [] for name in CONFIGS} for symbol in SYMBOLS}
        self.sweeps_pl = {symbol: {name: [] for name in CONFIGS} for symbol in SYMBOLS}
        self.sweeps_ph = {symbol: {name: [] for name in CONFIGS} for symbol in SYMBOLS}
        self.used_pivots = {symbol: {name: set() for name in CONFIGS} for symbol in SYMBOLS}
        self.pivot_history = {symbol: {name: {'ph': {}, 'pl': {}} for name in CONFIGS} for symbol in SYMBOLS}
        self.notified_events = {symbol: {name: set() for name in CONFIGS} for symbol in SYMBOLS}
        self.data_manager = data_manager
        self.notifier = notifier
        self.plotter = plotter
        self.position_monitors = {symbol: {name: [] for name in CONFIGS} for symbol in SYMBOLS}
        self.running = True
        self.streams = {}
        self.initial_data_loaded = {symbol: {name: False for name in CONFIGS} for symbol in SYMBOLS}  # Yeni: Veri yükleme kontrolü

    def load_initial_data(self, symbol, config_name):
        if self.initial_data_loaded[symbol][config_name]:
            return  # Veri zaten yüklendiyse tekrar çekme
        try:
            start_time = int((datetime.now() - timedelta(minutes=3750)).timestamp() * 1000)  # Yaklaşık 62 saatlik veri (15m * 250)
            klines = self.data_manager.client.futures_historical_klines(
                symbol=symbol, interval='15m', start_str=str(start_time), limit=250
            )
            df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
            df = df[['open_time', 'open', 'high', 'low', 'close']].astype({
                'open_time': 'datetime64[ms]', 'open': 'float64', 'high': 'float64', 'low': 'float64', 'close': 'float64'
            })
            self.data[symbol][config_name] = df
            self.update_pivot_history(symbol, config_name, CONFIGS[config_name])
            self.initial_data_loaded[symbol][config_name] = True
            logging.info(f"[{symbol}/{config_name}] 250 barlık geçmiş veri yüklendi.")
        except Exception as e:
            logging.error(f"Geçmiş veri yükleme hatası [{symbol}/{config_name}]: {e}")

    def process_candle(self, msg):
        if isinstance(msg, dict) and 'data' in msg:
            kline = msg['data']
            symbol = kline['s']
            candle = kline['k']
            timestamp = pd.to_datetime(int(candle['t']), unit='ms')
            new_row = {
                'open_time': timestamp,
                'open': float(candle['o']),
                'high': float(candle['h']),
                'low': float(candle['l']),
                'close': float(candle['c'])
            }
            for config_name, config in CONFIGS.items():
                # İlk veri yüklenmediyse önce yükle
                if not self.initial_data_loaded[symbol][config_name]:
                    self.load_initial_data(symbol, config_name)
                self.data[symbol][config_name] = pd.concat(
                    [self.data[symbol][config_name], pd.DataFrame([new_row])],
                    ignore_index=True
                )
                self.data[symbol][config_name] = self.data[symbol][config_name].tail(DATA_WINDOW)
                self.update_pivot_history(symbol, config_name, config)
                self.check_manipulation_zones(symbol, config_name, config)
                self.run_strategy(symbol, config_name, config)
        else:
            logging.warning(f"Beklenmeyen WebSocket mesajı: {msg}")

    def update_pivot_history(self, symbol, config_name, config):
        df = self.data[symbol][config_name]
        if len(df) < (config["LEFT"] + config["RIGHT"] + 1):
            return
        high = df['high'].values
        low = df['low'].values
        ph = pivot_high(high, config["LEFT"], config["RIGHT"])
        pl = pivot_low(low, config["LEFT"], config["RIGHT"])
        ph_dict = {idx: price for idx, price in ph}
        pl_dict = {idx: price for idx, price in pl}
        current_idx = len(df) - 1
        self.pivot_history[symbol][config_name]['ph'] = {k: v for k, v in ph_dict.items() if current_idx - k <= 250}
        self.pivot_history[symbol][config_name]['pl'] = {k: v for k, v in pl_dict.items() if current_idx - k <= 250}

    def check_manipulation_zones(self, symbol, config_name, config):
        df = self.data[symbol][config_name]
        if len(df) < 1:
            return
        current_price = self.data_manager.get_current_futures_price(symbol)
        if current_price is None:
            return
        ph_dict = self.pivot_history[symbol][config_name]['ph']
        pl_dict = self.pivot_history[symbol][config_name]['pl']
        for ph_idx, ph_price in ph_dict.items():
            if ph_idx in self.used_pivots[symbol][config_name]:
                continue
            proximity_key = f"ph_proximity_{ph_price}"
            manip_key = f"ph_manip_{ph_price}"
            proximity = abs(current_price - ph_price) / ph_price
            if proximity < PROXIMITY_THRESHOLD and proximity_key not in self.notified_events[symbol][config_name]:
                self.notifier.send_message(f"[{symbol}/{config_name}] UYARI: Fiyat Pivot High ({ph_price}) manipülasyon bölgesine yakın! (Mesafe: {proximity*100:.2f}%)")
                self.notified_events[symbol][config_name].add(proximity_key)
            if current_price > ph_price:
                manip_ratio = (current_price - ph_price) / ph_price
                if manip_ratio >= config["MANIPULATION_THRESHOLD"] and manip_key not in self.notified_events[symbol][config_name]:
                    self.notifier.send_message(f"[{symbol}/{config_name}] DİKKAT: Manipülasyon olabilir! Pivot High ({ph_price}) aşıldı, oran: {manip_ratio*100:.2f}%")
                    self.notified_events[symbol][config_name].add(manip_key)
        for pl_idx, pl_price in pl_dict.items():
            if pl_idx in self.used_pivots[symbol][config_name]:
                continue
            proximity_key = f"pl_proximity_{pl_price}"
            manip_key = f"pl_manip_{pl_price}"
            proximity = abs(pl_price - current_price) / pl_price
            if proximity < PROXIMITY_THRESHOLD and proximity_key not in self.notified_events[symbol][config_name]:
                self.notifier.send_message(f"[{symbol}/{config_name}] UYARI: Fiyat Pivot Low ({pl_price}) manipülasyon bölgesine yakın! (Mesafe: {proximity*100:.2f}%)")
                self.notified_events[symbol][config_name].add(proximity_key)
            if current_price < pl_price:
                manip_ratio = (pl_price - current_price) / pl_price
                if manip_ratio >= config["MANIPULATION_THRESHOLD"] and manip_key not in self.notified_events[symbol][config_name]:
                    self.notifier.send_message(f"[{symbol}/{config_name}] DİKKAT: Manipülasyon olabilir! Pivot Low ({pl_price}) altına inildi, oran: {manip_ratio*100:.2f}%")
                    self.notified_events[symbol][config_name].add(manip_key)

    def monitor_position(self, symbol, config_name, pos):
        while self.running and pos in self.positions[symbol][config_name]:
            try:
                current_price = self.data_manager.get_current_futures_price(symbol)
                if current_price is None:
                    time.sleep(1)
                    continue
                if pos['type'] == 'long':
                    if current_price <= pos['sl']:
                        self.close_position(symbol, config_name, pos, 'sl')
                        break
                    elif current_price >= pos['tp']:
                        self.close_position(symbol, config_name, pos, 'tp')
                        break
                elif pos['type'] == 'short':
                    if current_price >= pos['sl']:
                        self.close_position(symbol, config_name, pos, 'sl')
                        break
                    elif current_price <= pos['tp']:
                        self.close_position(symbol, config_name, pos, 'tp')
                        break
                time.sleep(1)
            except Exception as e:
                logging.error(f"Pozisyon izleme hatası [{symbol}/{config_name}]: {e}")
                time.sleep(1)

    def close_position(self, symbol, config_name, pos, reason):
        if reason == 'sl':
            profit = -pos['risk_amount']
            exit_price = pos['sl']
            message = f"[{symbol}/{config_name}] {pos['type'].capitalize()} işlem kapandı (SL): Entry: {pos['entry_price']}, Exit: {exit_price}, Profit: {profit}"
        elif reason == 'tp':
            profit = pos['risk_amount'] * CONFIGS[config_name]["RISK_REWARD_RATIO"]
            exit_price = pos['tp']
            message = f"[{symbol}/{config_name}] {pos['type'].capitalize()} işlem kapandı (TP): Entry: {pos['entry_price']}, Exit: {exit_price}, Profit: {profit}"
        trade = pos | {'exit_time': datetime.now(), 'exit_price': exit_price, 'profit': profit}
        event_key = f"close_{pos['entry_time']}_{reason}"
        if event_key not in self.notified_events[symbol][config_name]:
            self.notifier.send_message(message)
            self.notified_events[symbol][config_name].add(event_key)
        self.data_manager.close_position(symbol, config_name, trade, self)
        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=False)
        self.positions[symbol][config_name].remove(pos)
        logging.info(f"Trade closed: {trade}")

    def run_strategy(self, symbol, config_name, config):
        df = self.data[symbol][config_name]
        if len(df) < (config["LEFT"] + config["RIGHT"] + 1):
            return
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values
        open_ = df['open'].values
        index = df['open_time']
        ph = pivot_high(high, config["LEFT"], config["RIGHT"])
        pl = pivot_low(low, config["LEFT"], config["RIGHT"])
        ph_dict = {idx: price for idx, price in ph}
        pl_dict = {idx: price for idx, price in pl}
        i = len(df) - 1
        current_high = float(high[i])
        current_low = float(low[i])
        current_close = float(close[i])
        active_ph = {k: v for k, v in ph_dict.items() if k > i - DATA_WINDOW and k < i}
        active_pl = {k: v for k, v in pl_dict.items() if k > i - DATA_WINDOW and k < i}
        
        for ph_idx, ph_price in active_ph.items():
            if ph_idx in self.used_pivots[symbol][config_name]:
                continue
            if current_high > ph_price:
                manipulation_ratio = (current_high - ph_price) / ph_price
                if manipulation_ratio >= config["MANIPULATION_THRESHOLD"]:
                    self.sweeps_ph[symbol][config_name].append((ph_idx, ph_price, current_high, i, current_low, current_high))
                    self.used_pivots[symbol][config_name].add(ph_idx)
                    event_key = f"sweep_ph_{ph_price}"
                    if event_key not in self.notified_events[symbol][config_name]:
                        self.notifier.send_message(f"[{symbol}/{config_name}] Sell side sweep: Pivot High: {ph_price}, Sweep High: {current_high}")
                        self.notified_events[symbol][config_name].add(event_key)
        
        for pl_idx, pl_price in active_pl.items():
            if pl_idx in self.used_pivots[symbol][config_name]:
                continue
            if current_low < pl_price:
                manipulation_ratio = (pl_price - current_low) / pl_price
                if manipulation_ratio >= config["MANIPULATION_THRESHOLD"]:
                    self.sweeps_pl[symbol][config_name].append((pl_idx, pl_price, current_low, i, current_low, current_high))
                    self.used_pivots[symbol][config_name].add(pl_idx)
                    event_key = f"sweep_pl_{pl_price}"
                    if event_key not in self.notified_events[symbol][config_name]:
                        self.notifier.send_message(f"[{symbol}/{config_name}] Buy side sweep: Pivot Low: {pl_price}, Sweep Low: {current_low}")
                        self.notified_events[symbol][config_name].add(event_key)
        
        for sweep in self.sweeps_pl[symbol][config_name][:]:
            pl_idx, pl_price, sweep_low, sweep_idx, manip_low, manip_high = sweep
            bars_since_sweep = i - sweep_idx
            if bars_since_sweep > config["MAX_CANDLES"]:
                self.sweeps_pl[symbol][config_name].remove(sweep)
                continue
            if current_close <= pl_price:
                manip_low = min(manip_low, current_low)
                manip_high = max(manip_high, current_high)
                self.sweeps_pl[symbol][config_name][self.sweeps_pl[symbol][config_name].index(sweep)] = (pl_idx, pl_price, sweep_low, sweep_idx, manip_low, manip_high)
            if bars_since_sweep >= config["CONSECUTIVE_CANDLES"]:
                closes_above = all(float(close[i - j]) > pl_price for j in range(config["CONSECUTIVE_CANDLES"]))
                if closes_above:
                    entry_price = float(open_[i])
                    sl_price = manip_low
                    sl_distance = entry_price - sl_price
                    if sl_distance > 0:
                        risk_amount = config["INITIAL_BALANCE"] * config["MAX_RISK"]
                        position_size = risk_amount / sl_distance
                        tp_price = entry_price + sl_distance * config["RISK_REWARD_RATIO"]
                        trade = {
                            'type': 'long', 'entry_time': index[i], 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': pl_price, 'sweep_low': sweep_low, 'sweep_time': index[sweep_idx],
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        event_key = f"long_open_{index[i]}"
                        if event_key not in self.notified_events[symbol][config_name]:
                            self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                            self.notified_events[symbol][config_name].add(event_key)
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_pl[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)
                        monitor_thread = threading.Thread(target=self.monitor_position, args=(symbol, config_name, trade))
                        monitor_thread.daemon = True
                        monitor_thread.start()
                        self.position_monitors[symbol][config_name].append(monitor_thread)
            if bars_since_sweep >= config["MIN_CANDLES_FOR_SECOND_CONDITION"]:
                closes_below = all(float(close[i - j]) < pl_price for j in range(config["MIN_CANDLES_FOR_SECOND_CONDITION"], min(bars_since_sweep + 1, config["MAX_CANDLES_FOR_SECOND_CONDITION"] + 1)))
                if closes_below and current_close > pl_price:
                    entry_price = float(open_[i])
                    sl_price = manip_low
                    sl_distance = entry_price - sl_price
                    if sl_distance > 0:
                        risk_amount = config["INITIAL_BALANCE"] * config["MAX_RISK"]
                        position_size = risk_amount / sl_distance
                        tp_price = entry_price + sl_distance * config["RISK_REWARD_RATIO"]
                        trade = {
                            'type': 'long', 'entry_time': index[i], 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': pl_price, 'sweep_low': sweep_low, 'sweep_time': index[sweep_idx],
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        event_key = f"long_open_{index[i]}"
                        if event_key not in self.notified_events[symbol][config_name]:
                            self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                            self.notified_events[symbol][config_name].add(event_key)
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_pl[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)
                        monitor_thread = threading.Thread(target=self.monitor_position, args=(symbol, config_name, trade))
                        monitor_thread.daemon = True
                        monitor_thread.start()
                        self.position_monitors[symbol][config_name].append(monitor_thread)
        
        for sweep in self.sweeps_ph[symbol][config_name][:]:
            ph_idx, ph_price, sweep_high, sweep_idx, manip_low, manip_high = sweep
            bars_since_sweep = i - sweep_idx
            if bars_since_sweep > config["MAX_CANDLES"]:
                self.sweeps_ph[symbol][config_name].remove(sweep)
                continue
            if current_close >= ph_price:
                manip_low = min(manip_low, current_low)
                manip_high = max(manip_high, current_high)
                self.sweeps_ph[symbol][config_name][self.sweeps_ph[symbol][config_name].index(sweep)] = (ph_idx, ph_price, sweep_high, sweep_idx, manip_low, manip_high)
            if bars_since_sweep >= config["CONSECUTIVE_CANDLES"]:
                closes_below = all(float(close[i - j]) < ph_price for j in range(config["CONSECUTIVE_CANDLES"]))
                if closes_below:
                    entry_price = float(open_[i])
                    sl_price = manip_high
                    sl_distance = sl_price - entry_price
                    if sl_distance > 0:
                        risk_amount = config["INITIAL_BALANCE"] * config["MAX_RISK"]
                        position_size = risk_amount / sl_distance
                        tp_price = entry_price - sl_distance * config["RISK_REWARD_RATIO"]
                        trade = {
                            'type': 'short', 'entry_time': index[i], 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': ph_price, 'sweep_high': sweep_high, 'sweep_time': index[sweep_idx],
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        event_key = f"short_open_{index[i]}"
                        if event_key not in self.notified_events[symbol][config_name]:
                            self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                            self.notified_events[symbol][config_name].add(event_key)
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_ph[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)
                        monitor_thread = threading.Thread(target=self.monitor_position, args=(symbol, config_name, trade))
                        monitor_thread.daemon = True
                        monitor_thread.start()
                        self.position_monitors[symbol][config_name].append(monitor_thread)
            if bars_since_sweep >= config["MIN_CANDLES_FOR_SECOND_CONDITION"]:
                closes_above = all(float(close[i - j]) > ph_price for j in range(config["MIN_CANDLES_FOR_SECOND_CONDITION"], min(bars_since_sweep + 1, config["MAX_CANDLES_FOR_SECOND_CONDITION"] + 1)))
                if closes_above and current_close < ph_price:
                    entry_price = float(open_[i])
                    sl_price = manip_high
                    sl_distance = sl_price - entry_price
                    if sl_distance > 0:
                        risk_amount = config["INITIAL_BALANCE"] * config["MAX_RISK"]
                        position_size = risk_amount / sl_distance
                        tp_price = entry_price - sl_distance * config["RISK_REWARD_RATIO"]
                        trade = {
                            'type': 'short', 'entry_time': index[i], 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': ph_price, 'sweep_high': sweep_high, 'sweep_time': index[sweep_idx],
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        event_key = f"short_open_{index[i]}"
                        if event_key not in self.notified_events[symbol][config_name]:
                            self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                            self.notified_events[symbol][config_name].add(event_key)
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_ph[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)
                        monitor_thread = threading.Thread(target=self.monitor_position, args=(symbol, config_name, trade))
                        monitor_thread.daemon = True
                        monitor_thread.start()
                        self.position_monitors[symbol][config_name].append(monitor_thread)

    def start(self):
        for symbol in SYMBOLS:
            for config_name in CONFIGS:
                self.load_initial_data(symbol, config_name)  # Sadece bir kez başlangıç verisi çek
            stream = f"{symbol.lower()}@kline_15m"
            try:
                self.streams[symbol] = self.twm.start_multiplex_socket(callback=self.process_candle, streams=[stream], timeout=30)  # Zaman aşımı artırıldı
            except Exception as e:
                logging.error(f"WebSocket başlatma hatası [{symbol}]: {e}")
                time.sleep(5)  # Hata sonrası 5 saniye bekle ve tekrar dene
                self.restart_websocket(symbol)
        self.notifier.send_message(f"Futures sistemi başlatıldı: {', '.join(SYMBOLS)} için Safe, Mid, Agresif botlar aktif.")

    def restart_websocket(self, symbol):
        if symbol in self.streams:
            self.twm.stop_socket(self.streams[symbol])
            del self.streams[symbol]
        stream = f"{symbol.lower()}@kline_15m"
        try:
            self.streams[symbol] = self.twm.start_multiplex_socket(callback=self.process_candle, streams=[stream], timeout=30)
            logging.info(f"[{symbol}] WebSocket yeniden bağlandı.")
        except Exception as e:
            logging.error(f"[{symbol}] WebSocket yeniden bağlanma hatası: {e}")
            time.sleep(10)  # Hata sonrası daha uzun bekle

    def stop(self):
        self.running = False
        self.twm.stop()
        for symbol in SYMBOLS:
            for config_name in CONFIGS:
                for thread in self.position_monitors[symbol][config_name]:
                    if thread.is_alive():
                        thread.join()