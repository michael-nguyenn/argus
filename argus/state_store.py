import json
from argus.adapters.base import StockStatus
import time
import os

class StateStore:
    """
    Persists product state to JSON.

    Includes the last known status and last alert timestamp per product.
    """

    def __init__(self, path: str):
        """
        Loads existing state from disk
        """
        self.path = path

        try:
            with open(path, 'r') as file:
                self.entries = json.load(file)
        except FileNotFoundError:
            self.entries = {}

    def get_last_status(self, product_id: str) -> StockStatus | None:
        if product_id in self.entries:
            last_status = self.entries[product_id].get("last_status")
            return StockStatus(last_status) if last_status else None
        return None

    
    def get_last_alert_ts(self, product_id: str) -> float | None:
        if product_id in self.entries:
            last_alert = self.entries[product_id].get("last_alert_ts")
            return last_alert if last_alert else None
        return None
    
    def update(self, product_id: str, status: StockStatus, alerted: bool = False):
        """
        Update status for a product and flush

        If alerted=True, we'll also update last_alert_ts
        """
        if product_id not in self.entries:
            self.entries[product_id] = {}

        # We'll leave the status as the last definitive status
        if status is not StockStatus.UNKNOWN:
            self.entries[product_id]["last_status"] = status.value

        self.entries[product_id]["last_check_ts"] = time.time()

        if alerted:
            self.entries[product_id]["last_alert_ts"] = time.time()

        tmp = self.path + ".tmp"
        with open(tmp, "w") as file:
            json.dump(self.entries, file, indent=2)
        
        os.replace(tmp, self.path)