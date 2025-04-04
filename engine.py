# engine.py
from binance import ThreadedWebsocketManager
import pandas as pd
from config import CONFIGS
from settings import SYMBOLS, DATA_WINDOW, PROXIMITY_THRESHOLD
from utils import pivot_high, pivot_low
from datetime import datetime, timedelta

class TradingEngine:
    def __init__(self, api_key, api_secret, data_manager, notifier, plotter):
        self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret)
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
        self.data_manager = data_manager
        self.notifier = notifier
        self.plotter = plotter

    def process_candle(self, msg):
        if msg['e'] == 'kline' and msg['k']['x']:
            symbol = msg['s']
            candle = msg['k']
            timestamp = pd.to_datetime(int(candle['t']), unit='ms')
            new_row = {
                'open_time': timestamp,
                'open': float(candle['o']),
                'high': float(candle['h']),
                'low': float(candle['l']),
                'close': float(candle['c'])
            }
            for config_name, config in CONFIGS.items():
                self.data[symbol][config_name] = pd.concat(
                    [self.data[symbol][config_name], pd.DataFrame([new_row])], 
                    ignore_index=True
                )
                self.data[symbol][config_name] = self.data[symbol][config_name].tail(DATA_WINDOW)
                self.check_pivot_proximity(symbol, config_name, config)
                self.run_strategy(symbol, config_name, config)

    def check_pivot_proximity(self, symbol, config_name, config):
        df = self.data[symbol][config_name]
        if len(df) < (config["LEFT"] + config["RIGHT"] + 1):
            return
        high = df['high'].values
        low = df['low'].values
        close = df['close'].values[-1]
        ph = pivot_high(high, config["LEFT"], config["RIGHT"])
        pl = pivot_low(low, config["LEFT"], config["RIGHT"])
        ph_dict = {idx: price for idx, price in ph}
        pl_dict = {idx: price for idx, price in pl}
        i = len(df) - 1

        for ph_idx, ph_price in ph_dict.items():
            if ph_idx in self.used_pivots[symbol][config_name]:
                continue
            if abs(close - ph_price) / ph_price < PROXIMITY_THRESHOLD:
                self.notifier.send_message(f"[{symbol}/{config_name}] DİKKAT: Fiyat Pivot High ({ph_price}) seviyesine çok yakın!")

        for pl_idx, pl_price in pl_dict.items():
            if pl_idx in self.used_pivots[symbol][config_name]:
                continue
            if abs(pl_price - close) / pl_price < PROXIMITY_THRESHOLD:
                self.notifier.send_message(f"[{symbol}/{config_name}] DİKKAT: Fiyat Pivot Low ({pl_price}) seviyesine çok yakın!")

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

        # Sell side sweep (short)
        for ph_idx, ph_price in active_ph.items():
            if ph_idx in self.used_pivots[symbol][config_name]:
                continue
            if current_high > ph_price:
                manipulation_ratio = (current_high - ph_price) / ph_price
                if manipulation_ratio >= config["MANIPULATION_THRESHOLD"]:
                    self.sweeps_ph[symbol][config_name].append((ph_idx, ph_price, current_high, i, current_low, current_high))
                    self.used_pivots[symbol][config_name].add(ph_idx)
                    self.notifier.send_message(f"[{symbol}/{config_name}] Sell side sweep: Pivot High: {ph_price}, Sweep High: {current_high}")

        # Buy side sweep (long)
        for pl_idx, pl_price in active_pl.items():
            if pl_idx in self.used_pivots[symbol][config_name]:
                continue
            if current_low < pl_price:
                manipulation_ratio = (pl_price - current_low) / pl_price
                if manipulation_ratio >= config["MANIPULATION_THRESHOLD"]:
                    self.sweeps_pl[symbol][config_name].append((pl_idx, pl_price, current_low, i, current_low, current_high))
                    self.used_pivots[symbol][config_name].add(pl_idx)
                    self.notifier.send_message(f"[{symbol}/{config_name}] Buy side sweep: Pivot Low: {pl_price}, Sweep Low: {current_low}")

        # Long işlemleri (buy side sweep sonrası)
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
                            'type': 'long', 'entry_time': str(index[i]), 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': pl_price, 'sweep_low': sweep_low, 'sweep_time': str(index[sweep_idx]),
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_pl[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)

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
                            'type': 'long', 'entry_time': str(index[i]), 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': pl_price, 'sweep_low': sweep_low, 'sweep_time': str(index[sweep_idx]),
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_pl[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)

        # Short işlemleri (sell side sweep sonrası)
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
                            'type': 'short', 'entry_time': str(index[i]), 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': ph_price, 'sweep_high': sweep_high, 'sweep_time': str(index[sweep_idx]),
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_ph[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)

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
                            'type': 'short', 'entry_time': str(index[i]), 'entry_price': entry_price,
                            'sl': sl_price, 'tp': tp_price, 'size': position_size,
                            'pivot_price': ph_price, 'sweep_high': sweep_high, 'sweep_time': str(index[sweep_idx]),
                            'manip_low': manip_low, 'manip_high': manip_high, 'risk_amount': risk_amount
                        }
                        self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem açıldı: Entry: {entry_price}, SL: {sl_price}, TP: {tp_price}")
                        self.positions[symbol][config_name].append(trade)
                        self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=True)
                        self.sweeps_ph[symbol][config_name].remove(sweep)
                        self.data_manager.save_data(symbol, config_name, self)

        # Pozisyon kapama
        for pos in self.positions[symbol][config_name][:]:
            if pos['type'] == 'long':
                if current_low <= pos['sl']:
                    profit = -pos['risk_amount']
                    trade = pos | {'exit_time': str(index[i]), 'exit_price': pos['sl'], 'profit': profit}
                    self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem kapandı (SL): Entry: {pos['entry_price']}, Exit: {pos['sl']}, Profit: {profit}")
                    self.data_manager.close_position(symbol, config_name, trade, self)
                    self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=False)
                    self.positions[symbol][config_name].remove(pos)
                elif current_high >= pos['tp']:
                    profit = pos['risk_amount'] * config["RISK_REWARD_RATIO"]
                    trade = pos | {'exit_time': str(index[i]), 'exit_price': pos['tp'], 'profit': profit}
                    self.notifier.send_message(f"[{symbol}/{config_name}] Long işlem kapandı (TP): Entry: {pos['entry_price']}, Exit: {pos['tp']}, Profit: {profit}")
                    self.data_manager.close_position(symbol, config_name, trade, self)
                    self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=False)
                    self.positions[symbol][config_name].remove(pos)
            elif pos['type'] == 'short':
                if current_high >= pos['sl']:
                    profit = -pos['risk_amount']
                    trade = pos | {'exit_time': str(index[i]), 'exit_price': pos['sl'], 'profit': profit}
                    self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem kapandı (SL): Entry: {pos['entry_price']}, Exit: {pos['sl']}, Profit: {profit}")
                    self.data_manager.close_position(symbol, config_name, trade, self)
                    self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=False)
                    self.positions[symbol][config_name].remove(pos)
                elif current_low <= pos['tp']:
                    profit = pos['risk_amount'] * config["RISK_REWARD_RATIO"]
                    trade = pos | {'exit_time': str(index[i]), 'exit_price': pos['tp'], 'profit': profit}
                    self.notifier.send_message(f"[{symbol}/{config_name}] Short işlem kapandı (TP): Entry: {pos['entry_price']}, Exit: {pos['tp']}, Profit: {profit}")
                    self.data_manager.close_position(symbol, config_name, trade, self)
                    self.plotter.save_trade_graph(symbol, config_name, trade, self.data[symbol][config_name], is_opening=False)
                    self.positions[symbol][config_name].remove(pos)

    def start(self):
        for symbol in SYMBOLS:
            self.twm.start_kline_socket(callback=self.process_candle, symbol=symbol, interval='15m')
        self.notifier.send_message(f"Futures sistemi başlatıldı: {', '.join(SYMBOLS)} için Safe, Mid, Agresif botlar aktif.")

    def stop(self):
        self.twm.stop()