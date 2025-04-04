# notifications.py
import requests
from config import DISCORD_WEBHOOK_URL

class Notifier:
    def __init__(self, webhook_url=DISCORD_WEBHOOK_URL):
        self.webhook_url = webhook_url

    def send_message(self, message):
        if self.webhook_url:
            try:
                payload = {"content": message}
                requests.post(self.webhook_url, json=payload)
            except Exception as e:
                print(f"Discord bildirimi gönderilemedi: {e}")
        else:
            print(f"Bildirim: {message}")