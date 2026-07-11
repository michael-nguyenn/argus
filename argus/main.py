from dotenv import load_dotenv
import logging
import time
from random import uniform
from argus.config_loader import load_config
from argus.state_store import StateStore
from argus.adapters import register_adapter, get_adapter
from argus.adapters.mock import MockAdapter
from argus.adapters.bestbuy import BestBuyAdapter
from argus.notifiers.discord import DiscordNotifier
from argus.adapters.base import StockStatus

CONFIG_PATH = "config/products.yaml"
STATE_STORE_PATH = "state/state.json"
SLEEP_INTERVAL = 5

logger = logging.getLogger("argus")



def main():

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv()

    # Load Config
    config = load_config(CONFIG_PATH)
    products = config["products"]
    settings = config["settings"]

    # Initialize State Store
    state_store: StateStore = StateStore(STATE_STORE_PATH)

    # Register Adapters
    register_adapter(MockAdapter())
    register_adapter(BestBuyAdapter())

    # Initialize Notifiers
    notifiers = []
    discord_notifier = DiscordNotifier()
    notifiers.append(discord_notifier)

    # Enter the scheduler loop
    run_scheduler(products, state_store, notifiers, settings)


"""
product = {
    'id': 'chaos-rising-etb', 
    'name': 'Pokémon TCG: Chaos Rising Elite Trainer Box', 
    'source': 'bestbuy', 
    'url': 'https://www.bestbuy.ca/en-ca/product/pokemon-tcg-mega-evolution-chaos-rising-elite-trainer-box/19906421', 
    'cooldown_minutes': 5, 
    'interval_seconds': 60, 
    'notify': True
    'script': [] | None
}
"""
def run_scheduler(products, state_store, notifiers, settings):

    # product_id -> epoch time stamp
    # empty means everything is due
    next_check = {}

    while True:
        now = time.time()

        for product in products:
            product_id = product["id"]
            # 0 means never scheduled -> do it now
            if now < next_check.get(product_id, 0):
                continue

            adapter = get_adapter(product["source"])
            result = adapter.check(product)

            old: StockStatus | None = state_store.get_last_status(product_id)
            
            alerted = False
            if result.status != StockStatus.UNKNOWN:
                if old == StockStatus.OUT_OF_STOCK and result.status == StockStatus.IN_STOCK:
                    last_alert = state_store.get_last_alert_ts(product_id)
                    if  product.get("notify", True) and (last_alert is None or (now - last_alert) > product["cooldown_minutes"] * 60):
                        for notifier in notifiers:
                            ok = notifier.notify(product, old.value, result.status.value, now)
                            alerted = alerted or ok
                    
            state_store.update(product_id, result.status, alerted=alerted)
            interval = product["interval_seconds"]
            logger.info(f"checked {product_id} source={product['source']} status={result.status.value} latency={result.latency_ms:.0f}ms")
            next_check[product_id] = now + interval + uniform(-0.2,0.2) * interval

        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    main()