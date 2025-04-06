# panel.py
import dash
from dash import dcc, html, Input, Output
import pandas as pd
import plotly.graph_objects as go
from engine import TradingEngine
from notifications import Notifier
from plotter import Plotter
from data_manager import DataManager
from config import API_KEY, API_SECRET, CONFIGS
from settings import SYMBOLS, PLOT_CANDLES_BEFORE, PLOT_CANDLES_AFTER
import threading
import sys
import argparse
from datetime import datetime, timedelta

log_messages = []

class CustomNotifier(Notifier):
    def send_message(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_messages.append(f"[{timestamp}] {message}")
        super().send_message(message)

notifier = CustomNotifier()
plotter = Plotter()
data_manager = DataManager(API_KEY, API_SECRET)
engine = TradingEngine(API_KEY, API_SECRET, data_manager, notifier, plotter)

app = dash.Dash(__name__, assets_folder='assets')

app.layout = html.Div([
    html.H1("Trading Bot Dashboard"),
    html.Div([
        html.H3("Log Kayıtları"),
        html.Pre(id='log-output', children="\n".join(log_messages[-10:]), className='log-section')
    ], className='section'),
    html.Div([
        html.H3("Fiyatlar ve Kasa"),
        html.Div(id='bot-summary', className='summary-section')
    ], className='section'),
    html.Div([
        html.Label("Pair Seçimi:", style={'color': '#bfd2ff'}),
        dcc.Dropdown(id='symbol-dropdown', options=[{'label': s, 'value': s} for s in SYMBOLS], value=SYMBOLS[0], className='dropdown'),
        html.Label("Bot Seçimi:", style={'color': '#bfd2ff'}),
        dcc.Dropdown(id='bot-dropdown', options=[{'label': name.capitalize(), 'value': name} for name in CONFIGS.keys()], value='safe', className='dropdown')
    ], className='section'),
    html.Div([
        html.H3("İstatistikler"),
        dcc.Dropdown(id='period-dropdown', options=[
            {'label': 'Tüm Zaman', 'value': None}, 
            {'label': '1 Ay', 'value': '1ay'}, 
            {'label': '3 Ay', 'value': '3ay'}, 
            {'label': '6 Ay', 'value': '6ay'}
        ], value=None, className='dropdown'),
        html.Pre(id='stats-text'),
        dcc.Graph(id='profit-graph')
    ], className='section stats-trades-section'),
    html.Div([
        html.H3("Son İşlemler"),
        html.Pre(id='trades-text'),
        dcc.Dropdown(id='trade-dropdown', className='dropdown'),
        dcc.Graph(id='trade-graph')
    ], className='section stats-trades-section'),
    dcc.Interval(id='interval-component', interval=5*1000, n_intervals=0)
])

def run_cli():
    parser = argparse.ArgumentParser(description="Trading Bot CLI - Bot durumunu sorgula", prog="TradingBotCLI")
    parser.add_argument("symbol", help=f"İşlem çifti (ör: BTCUSDT, seçenekler: {', '.join(SYMBOLS)})")
    parser.add_argument("bot", help=f"Bot adı (ör: safe, mid, agresif, seçenekler: {', '.join(CONFIGS.keys())})")
    parser.add_argument("command", help="Komut (kasa, işlem, performans, durum)")
    parser.add_argument("--period", help="Performans dönemi (1ay, 3ay, 6ay)", default=None)
    
    print("\033[1;36m=== Trading Bot CLI ===\033[0m")
    print("Komutları girin (ör: 'BTCUSDT mid kasa') veya '--help' ile yardım alın. Çıkmak için 'çıkış' yazın.")
    
    while True:
        query = input("\033[1;32m> \033[0m").strip()
        if query.lower() == "çıkış":
            print("\033[1;31mCLI Panel kapatıldı.\033[0m")
            sys.exit(0)
        if query.lower() in ["--help", "-h"]:
            print(parser.format_help())
            continue
        
        try:
            args = parser.parse_args(query.split())
            symbol = args.symbol.upper()
            bot_name = args.bot.lower()
            command = args.command.lower()
            if args.period:
                command += f" {args.period}"
            response = data_manager.handle_query(symbol, bot_name, command, engine)
            print(f"\033[1;33m{response}\033[0m")
        except SystemExit:
            print("\033[1;31mHata: Geçersiz komut. Örnek: 'BTCUSDT mid kasa' veya '--help' ile yardım alın.\033[0m")
        except Exception as e:
            print(f"\033[1;31mHata: {e}\033[0m")

@app.callback(Output('log-output', 'children'), Input('interval-component', 'n_intervals'))
def update_log(n_intervals):
    return "\n".join(log_messages[-10:])

@app.callback(Output('bot-summary', 'children'), [Input('symbol-dropdown', 'value'), Input('bot-dropdown', 'value'), Input('interval-component', 'n_intervals')])
def update_summary(symbol, bot_name, n_intervals):
    if symbol is None or bot_name is None:
        return html.P("Lütfen bir pair ve bot seçin.")
    try:
        return [
            html.P(f"Anlık Fiyat: {data_manager.get_current_price(symbol):.2f} USDT"),
            html.P(f"Kasa: {data_manager.balances[symbol][bot_name]:.2f} USD (Başlangıç: {CONFIGS[bot_name]['INITIAL_BALANCE']} USD)"),
            html.P(f"Açık Pozisyon: {len(engine.positions[symbol][bot_name])}"),
            html.P(f"Toplam İşlem: {len(data_manager.trades[symbol][bot_name])}"),
            html.P(f"Aylık İşlem: {data_manager.stats[symbol][bot_name]['monthly_trades']}")
        ]
    except KeyError:
        return html.P("Veri yüklenemedi, lütfen tekrar deneyin.")

@app.callback([Output('stats-text', 'children'), Output('profit-graph', 'figure')], [Input('symbol-dropdown', 'value'), Input('bot-dropdown', 'value'), Input('period-dropdown', 'value')])
def update_stats(symbol, bot_name, period):
    if symbol is None or bot_name is None:
        return "Lütfen bir pair ve bot seçin.", go.Figure()
    stats, trades = data_manager.get_stats(symbol, bot_name, period)
    if not trades.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=trades['exit_time'], y=trades['profit'].cumsum(), mode='lines+markers', name='Kâr/Zarar', line=dict(color='#8da2fb')))
        fig.update_layout(title=f'{symbol}/{bot_name} Kâr/Zarar ({period or "Tüm Zaman"})', xaxis_title='Tarih', yaxis_title='Kâr/Zarar (USD)', template='plotly_dark', title_font_color='#8da2fb')
    else:
        fig = go.Figure()
        fig.update_layout(title='Henüz Veri Yok', template='plotly_dark', title_font_color='#8da2fb')
    return stats, fig

@app.callback([Output('trades-text', 'children'), Output('trade-dropdown', 'options')], [Input('symbol-dropdown', 'value'), Input('bot-dropdown', 'value')])
def update_trades(symbol, bot_name):
    if symbol is None or bot_name is None:
        return "Lütfen bir pair ve bot seçin.", []
    trades = data_manager.get_last_trades(symbol, bot_name, count=10)
    options = [{'label': f'İşlem {i+1}', 'value': i} for i in range(min(10, len(data_manager.trades[symbol][bot_name])))]
    return trades, options

@app.callback(Output('trade-graph', 'figure'), [Input('symbol-dropdown', 'value'), Input('bot-dropdown', 'value'), Input('trade-dropdown', 'value')])
def update_trade_graph(symbol, bot_name, trade_idx):
    if symbol is None or bot_name is None or trade_idx is None or trade_idx >= len(data_manager.trades[symbol][bot_name]):
        return go.Figure()
    
    trade = data_manager.trades[symbol][bot_name][trade_idx]
    df = engine.data[symbol][bot_name].set_index('open_time')
    entry_time = pd.to_datetime(trade['entry_time'])
    exit_time = pd.to_datetime(trade['exit_time'])
    sweep_time = pd.to_datetime(trade['sweep_time'])
    start_time = sweep_time - timedelta(minutes=15 * PLOT_CANDLES_BEFORE)
    end_time = exit_time + timedelta(minutes=15 * PLOT_CANDLES_AFTER)
    df_plot = df.loc[start_time:end_time].copy()

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name='Fiyat'))
    fig.add_trace(go.Scatter(x=[sweep_time], y=[trade['sweep_low'] if trade['type'] == 'long' else trade['sweep_high']], mode='markers', marker=dict(symbol='circle', size=10, color='#bfd2ff'), name=f'Sweep'))
    fig.add_trace(go.Scatter(x=[entry_time], y=[trade['entry_price']], mode='markers', marker=dict(symbol='triangle-up', size=10, color='#8da2fb'), name=f'Giriş: {trade["entry_price"]:.2f}'))
    fig.add_trace(go.Scatter(x=[exit_time], y=[trade['exit_price']], mode='markers', marker=dict(symbol='triangle-down', size=10, color='#ff4d4d' if trade['profit'] < 0 else '#8da2fb'), name=f'Çıkış: {trade["exit_price"]:.2f}'))
    fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['sl']] * len(df_plot), mode='lines', line=dict(dash='dash', color='#ff4d4d'), name=f'SL: {trade["sl"]:.2f}'))
    fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['tp']] * len(df_plot), mode='lines', line=dict(dash='dash', color='#8da2fb'), name=f'TP: {trade["tp"]:.2f}'))
    fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['pivot_price']] * len(df_plot), mode='lines', line=dict(dash='dash', color='#bfd2ff'), name=f'Pivot: {trade["pivot_price"]:.2f}'))
    manip_extreme = trade['manip_low'] if trade['type'] == 'long' else trade['manip_high']
    fig.add_trace(go.Scatter(x=[sweep_time], y=[manip_extreme], mode='markers', marker=dict(symbol='x', size=10, color='#bfd2ff'), name=f'Manip'))
    fig.update_layout(title=f'{symbol}/{bot_name} İşlem {trade_idx + 1}: {trade["type"].capitalize()} (Kâr/Zarar: {trade["profit"]:.2f} USD)', xaxis_title='Zaman', yaxis_title='Fiyat (USDT)', template='plotly_dark', title_font_color='#8da2fb')
    return fig

if __name__ == "__main__":
    engine.start()
    cli_thread = threading.Thread(target=run_cli)
    cli_thread.daemon = True
    cli_thread.start()
    app.run(debug=True, host='0.0.0.0', port=5000)