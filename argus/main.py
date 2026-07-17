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
from argus.adapters.base import StockStatus, CheckResult
import argparse
from concurrent.futures import ThreadPoolExecutor
from argus.rate_limiter import SiteRateLimiter
from argus.retry import with_retries

SLEEP_INTERVAL = 5 # seconds between each scheduling loop
JITTER_AMOUNT = 0.2 # add variation to the stock check intervals

logger = logging.getLogger("argus")


def main():

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv()

    # Load Config
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/products.yaml")
    parser.add_argument("--state", default="state/state.json")
    args = parser.parse_args()

    config = load_config(args.config)
    products = config["products"]
    settings = config["settings"]
    rate_limits = settings["rate_limits"]

    # Initialize State Store
    state_store: StateStore = StateStore(args.state)

    # Register Adapters
    register_adapter(MockAdapter())
    register_adapter(BestBuyAdapter())

    # Initialize Notifiers
    notifiers = []
    discord_notifier = DiscordNotifier()
    notifiers.append(discord_notifier)

    # Initialize our rate limiter
    rate_limiter = SiteRateLimiter(rate_limits)

    # Enter the scheduler loop
    with ThreadPoolExecutor(max_workers=settings["max_threads"]) as executor:
        run_scheduler(products, state_store, notifiers, settings, executor, rate_limiter)


def run_scheduler(products, state_store, notifiers, settings, executor, rate_limiter):
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

    # product_id -> epoch time stamp
    # empty means everything is due
    next_check = {}
    
    in_flight = set() # this keeps track of products already being handled
    future_to_product = {} # this maps a Future object to a products dict

    while True:
        now = time.time()

        # === PHASE 1 - DISAPTCH: For each product due and not in flight, submit a job request ===
        for product in products:
            product_id = product["id"]

            # 0 means never scheduled -> do it now
            if now < next_check.get(product_id, 0):
                continue

            # Submit job, update in_flight and future_to_product
            if product_id not in in_flight:
                future = executor.submit(check_product, product, rate_limiter)
                in_flight.add(product_id)
                future_to_product[future] = product

        # === PHASE 2 - Harvest: For each done future, process the result. ===

        # Go thru each future, and check if it's done
        done = [f for f in future_to_product if f.done()] # this gets a snapshot of the state of each future

        # Using a copy lets us mutate without worry
        for future in done:
            product = future_to_product[future]
            product_id = product["id"]

            try:
                result = future.result()
            except Exception as e:
                logger.error(f"check for {product_id} raised: {e}")
                del future_to_product[future]
                in_flight.discard(product_id)
                continue

            # Send off the result to process and alert our notifiers
            alerted = process_and_alert(result, product, state_store, settings, notifiers, now)
            
            # Remove from our set and dict
            del future_to_product[future]
            in_flight.discard(product_id)

            # Update Storage
            state_store.update(product_id, result.status, alerted=alerted)
            interval = product["interval_seconds"]
            logger.info(f"checked {product_id} source={product['source']} status={result.status.value} latency={result.latency_ms:.0f}ms")

            # +- JITTER_AMOUNT to add some randomness to the stock checking
            next_check[product_id] = now + interval + uniform(-JITTER_AMOUNT,JITTER_AMOUNT) * interval

        # So we don't blast thru our CPU cycles 
        time.sleep(SLEEP_INTERVAL)


def check_product(product: dict, rate_limiter) -> CheckResult:
    """
    Runs inside a worker thread.

    Get the rate limiter for the product's site, and then call the adaptor's check().
    """
    adapter = get_adapter(product["source"])
    rate_limiter.acquire(product["source"])
    return with_retries(lambda: adapter.check(product))


def process_and_alert(result, product, state_store, settings, notifiers, now) -> bool:
    product_id = product["id"]

    old: StockStatus | None = state_store.get_last_status(product_id)
    
    alerted = False

    # UNKNOWN never particaptes in transitions or state: a bad network between two
    # IN_STOCK checks shouldn't look like a restock
    if result.status != StockStatus.UNKNOWN:

        # Alert on the OUT -> IN scenario only. 
        # If old is None, it's the product's first definitive check, and records it silently
        if old == StockStatus.OUT_OF_STOCK and result.status == StockStatus.IN_STOCK:
            last_alert = state_store.get_last_alert_ts(product_id)
            cooldown = product.get("cooldown_minutes", settings["cooldown_minutes"])

            # Cooldown surpresses repeat alerts. State is still updated below
            # Per product override handles cooldown
            if  product.get("notify", True) and (last_alert is None or (now - last_alert) > cooldown * 60):

                # Alerted accumulates across notifiers. True if any delivery succeeds.
                # All failures leaves the last_alert_ts unset, so that the next transition retires
                # rather than cooldown surpression on an alert that never went thru
                for notifier in notifiers:
                    ok = notifier.notify(product, old.value, result.status.value, now)
                    alerted = alerted or ok

    return alerted

if __name__ == "__main__":
    main()