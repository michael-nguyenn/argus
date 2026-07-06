from argus.notifiers.base import BaseNotifier
import os
import requests
from datetime import datetime, timezone
import logging

logger = logging.getLogger("argus.notifiers.discord")

class DiscordNotifier(BaseNotifier):
    """
    Sends restock alerts to a Discord Channel via webhook.

    Webhook URL is loaded from the DISCORD_WEBHOOK_URL env variable.
    """

    def __init__(self):
        """
        Load webhook URL from environment.
        Raise an error at startup if it's missing.
        """
        self.webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL not found")


    def notify(self, product: dict, old_status: str, new_status: str, timestamp: float) -> bool:
        """
        POST a rich embed to the Discord webhook.

        Include: product name, source, URL (clickable), old -> new status, and timestamp
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

        embed_data = {
            "embeds": [
                {
                    "title": product["name"],
                    "url": product["url"],
                    "description": f"{old_status} -> {new_status}",
                    "timestamp": dt.isoformat(),
                    "fields": [
                        {"name": "Source", "value": product["source"], "inline": True},
                    ]
                }
            ]
        }

        try:
            resp = requests.post(self.webhook_url, json=embed_data, timeout=5)
        except requests.RequestException as e:
            logger.error(f"Discord webhook POST failed: {e}")
            return False
        
        # Manually Check if Discord rejected the POST
        if resp.status_code < 200 or resp.status_code >= 300:
            logger.error(f"Discord Rejected POST request with Code: {resp.status_code}")
            return False
        
        return True

            
