# utils.py
import numpy as np
import requests
import json
from datetime import datetime

def pivot_high(series, left, right):
    series = np.array(series)
    pivots = []
    for i in range(left, len(series) - right):
        left_slice = series[i - left:i]
        right_slice = series[i + 1:i + right + 1]
        if np.all(series[i] > left_slice) and np.all(series[i] > right_slice):
            pivots.append((i, float(series[i])))
    return pivots

def pivot_low(series, left, right):
    series = np.array(series)
    pivots = []
    for i in range(left, len(series) - right):
        left_slice = series[i - left:i]
        right_slice = series[i + 1:i + right + 1]
        if np.all(series[i] < left_slice) and np.all(series[i] < right_slice):
            pivots.append((i, float(series[i])))
    return pivots

def send_discord_message(webhook_url, message):
    payload = {"content": message}
    requests.post(webhook_url, json=payload)

def save_data(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, default=str)

def load_data(filename, default_data):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default_data