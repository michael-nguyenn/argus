from argus.adapters.base import BaseAdapter, CheckResult, StockStatus
import requests
import time
import logging

logger = logging.getLogger("argus.adapters.bestbuy")

AVAILABILITY_URL = "https://www.bestbuy.ca/ecomm-api/availability/products"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://www.bestbuy.ca/",
}

class BestBuyAdapter(BaseAdapter):
    def source_name(self):
        return "bestbuy"
    
    def check(self, product: dict) -> CheckResult:
        """
        Bestbuy uses SKU to identify each product.
        A invalid SKU will result in an OUT_OF_STOCK status.
        TODO: Add purchase limit and items left 
        """

        # extracts the sku at the end of the url
        sku = product["url"].rstrip('/').rsplit('/', 1)[-1]

        params = {
            "accept": "application/vnd.bestbuy.standardproduct.v1+json",
            "skus": sku,
        }

        start = time.monotonic()
        try:
            resp = requests.get(AVAILABILITY_URL, params=params, headers=HEADERS, timeout=10)
        except requests.RequestException as e:
            latency_ms = (time.monotonic() - start) * 1000
            logger.error(f"sku={sku} request failued: {e}")
            return CheckResult(StockStatus.UNKNOWN,latency_ms, f"request failed {e}")

        latency_ms = (time.monotonic() - start) * 1000
        if 200 <= resp.status_code < 300:
            # Success
            try:
                data = resp.json()
                shipping = data["availabilities"][0]["shipping"]
                purchasable: bool = shipping["purchasable"]
                quantity_remain: int = shipping["quantityRemaining"]
                order_limit = shipping["orderLimit"]
            except (ValueError, KeyError, IndexError) as e:
                logger.error(f"sku={sku} json error: {e}")
                return CheckResult(StockStatus.UNKNOWN,latency_ms, f"json error {e}")
            
            # Finally form a good response
            status = StockStatus.IN_STOCK if purchasable else StockStatus.OUT_OF_STOCK
            logger.info(f"checked sku={sku} purchasable={purchasable} qty={quantity_remain} limit={order_limit} latency={latency_ms:.0f}ms")
            return CheckResult(status, latency_ms)
            
        else:
            logger.error(f"sku={sku} response status code: {resp.status_code}")
            return CheckResult(StockStatus.UNKNOWN,latency_ms, f"http {resp.status_code}")


