# plotter.py
import pandas as pd  # Pandas modülünü içe aktar
import plotly.graph_objects as go
from settings import PLOT_CANDLES_BEFORE, PLOT_CANDLES_AFTER

class Plotter:
    def save_trade_graph(self, symbol, config_name, trade, df, is_opening=False):
        """
        Trade grafiğini oluşturur ve kaydeder.
        
        Args:
            symbol (str): İşlem çifti
            config_name (str): Bot konfigürasyon adı
            trade (dict): Trade detayları
            df (pd.DataFrame): Fiyat verileri
            is_opening (bool): İşlem açılışı mı kapanışı mı?
        """
        entry_time = pd.to_datetime(trade['entry_time'])
        sweep_time = pd.to_datetime(trade['sweep_time'])
        start_time = sweep_time - pd.Timedelta(minutes=15 * PLOT_CANDLES_BEFORE)
        end_time = entry_time + pd.Timedelta(minutes=15 * PLOT_CANDLES_AFTER)
        df_plot = df.loc[start_time:end_time].copy()

        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_plot.index, open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name='Fiyat'))
        fig.add_trace(go.Scatter(x=[sweep_time], y=[trade['sweep_low'] if trade['type'] == 'long' else trade['sweep_high']], mode='markers', marker=dict(symbol='circle', size=10, color='white'), name=f'Sweep'))
        fig.add_trace(go.Scatter(x=[entry_time], y=[trade['entry_price']], mode='markers', marker=dict(symbol='triangle-up', size=10, color='cyan'), name=f'Giriş: {trade["entry_price"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['sl']] * len(df_plot), mode='lines', line=dict(dash='dash', color='red'), name=f'SL: {trade["sl"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['tp']] * len(df_plot), mode='lines', line=dict(dash='dash', color='cyan'), name=f'TP: {trade["tp"]:.2f}'))
        fig.add_trace(go.Scatter(x=df_plot.index, y=[trade['pivot_price']] * len(df_plot), mode='lines', line=dict(dash='dash', color='white'), name=f'Pivot: {trade["pivot_price"]:.2f}'))
        manip_extreme = trade['manip_low'] if trade['type'] == 'long' else trade['manip_high']
        fig.add_trace(go.Scatter(x=[sweep_time], y=[manip_extreme], mode='markers', marker=dict(symbol='x', size=10, color='white'), name=f'Manip'))

        fig.update_layout(
            title=f'{symbol}/{config_name} {"İşlem Açılışı" if is_opening else "İşlem Kapanışı"}',
            xaxis_title='Zaman',
            yaxis_title='Fiyat (USDT)',
            template='plotly_dark',
            title_font_color='cyan'
        )

        status = "opening" if is_opening else "closing"
        fig.write_image(f"trades/{symbol}_{config_name}_{trade['entry_time'].replace(':', '-')}_{status}.png")