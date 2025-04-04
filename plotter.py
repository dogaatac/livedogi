# plotter.py
import os
import plotly.graph_objects as go
from datetime import timedelta
from settings import PLOT_CANDLES_BEFORE, PLOT_CANDLES_AFTER

class Plotter:
    def __init__(self):
        if not os.path.exists("islemler"):
            os.makedirs("islemler")

    def save_trade_graph(self, symbol, config_name, trade, df, is_opening=True):
        df = df.set_index('open_time')
        entry_time = pd.to_datetime(trade['entry_time'])
        sweep_time = pd.to_datetime(trade['sweep_time'])
        start_time = sweep_time - timedelta(minutes=15 * PLOT_CANDLES_BEFORE)
        
        if is_opening:
            end_time = entry_time + timedelta(minutes=15 * PLOT_CANDLES_AFTER)
            filename_suffix = "open"
        else:
            exit_time = pd.to_datetime(trade['exit_time'])
            end_time = exit_time + timedelta(minutes=15 * PLOT_CANDLES_AFTER)
            filename_suffix = "close"

        df_plot = df.loc[start_time:end_time].copy()
        fig = go.Figure()

        fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name='Fiyat'))
        sweep_price = trade['sweep_low'] if trade['type'] == 'long' else trade['sweep_high']
        fig.add_trace(go.Scatter(x=[sweep_time], y=[sweep_price], mode='markers', marker=dict(symbol='circle', size=10, color='purple'), name=f'Sweep: {sweep_price:.2f}'))
        fig.add_trace(go.Scatter(x=[entry_time], y=[trade['entry_price']], mode='markers', marker=dict(symbol='triangle-up', size=10, color='green'), name=f'Giriş: {trade["entry_price"]:.2f}'))
        if not is_opening:
            exit_time = pd.to_datetime(trade['exit_time'])
            fig.add_trace(go.Scatter(x=[exit_time], y=[trade['exit_price']], mode='markers', marker=dict(symbol='triangle-down', size=10, color='red' if trade['profit'] < 0 else 'green'), name=f'Çıkış: {trade["exit_price"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['sl']] * len(df_plot), mode='lines', line=dict(dash='dash', color='darkred'), name=f'SL: {trade["sl"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['tp']] * len(df_plot), mode='lines', line=dict(dash='dash', color='darkgreen'), name=f'TP: {trade["tp"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['pivot_price']] * len(df_plot), mode='lines', line=dict(dash='dash', color='blue'), name=f'Pivot: {trade["pivot_price"]:.2f}'))
        manip_extreme = trade['manip_low'] if trade['type'] == 'long' else trade['manip_high']
        fig.add_trace(go.Scatter(x=[sweep_time], y=[manip_extreme], mode='markers', marker=dict(symbol='x', size=10, color='orange'), name=f'Manip Extreme: {manip_extreme:.2f}'))

        title = f'{symbol}/{config_name} İşlem: {trade["type"].capitalize()} - {"Açılış" if is_opening else f"Kapanış (Kâr/Zarar: {trade["profit"]:.2f} USD)"}'
        fig.update_layout(title=title, xaxis_title='Zaman', yaxis_title='Fiyat (USDT)', template='plotly_dark')

        timestamp = entry_time.strftime('%Y%m%d_%H%M%S') if is_opening else exit_time.strftime('%Y%m%d_%H%M%S')
        filename = f"islemler/{config_name}_{symbol}_{timestamp}_{filename_suffix}.png"
        fig.write_image(filename, width=1200, height=800)
        print(f"Grafik kaydedildi: {filename}")