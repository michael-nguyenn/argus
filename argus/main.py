from dotenv import load_dotenv
import logging
import time
from random import uniform
import argparse
from collections import defaultdict
import os

from argus.config_loader import load_config
from argus.state_store import StateStore
from argus.notifiers.discord import DiscordNotifier
from argus.adapters.base import StockStatus, CheckResult
from argus.status_server import StatusServer
from argus.queue import JobQueue
from argus.messages import make_job

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
    q_settings = settings["queue"]

    # Initialize State Store
    state_store: StateStore = StateStore(args.state)

    # Initialize Notifiers
    notifiers = []
    discord_notifier = DiscordNotifier()
    notifiers.append(discord_notifier)

    # Set up health endpoint
    snapshot_ref = {"current": {}}
    status = StatusServer(
        settings["status_port"],
        lambda: snapshot_ref["current"]
    )
    # start up our daemon thread
    status.start()

    # Set up our Message Queue
    queue_url = os.getenv("ARGUS_QUEUE_URL", q_settings["url"])
    queue: JobQueue = JobQueue(queue_url)

    run_coordinator(products, state_store, notifiers, settings, queue, q_settings, snapshot_ref)


def run_coordinator(products, state_store, notifiers, settings, queue, q_settings, snapshot_ref):
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

    # Empty means everything is due
    next_check = {} # product_id -> epoch time stamp
    in_flight = {} # job_id -> (product_id, dispatched_ts)
    in_flight_products = set()
    

    status_data = {} # prod_id -> entry dict
    error_counts = defaultdict(int)
    last_heartbeat = {} # worker_id -> heartbeat msg
    products_by_id = {p["id"]: p for p in products}
    while True:
        now = time.time()

        # === PHASE 1 - DISAPTCH: For each product due and not in flight, submit a job request ===
        for product in products:
            product_id = product["id"]

            # 0 means never scheduled -> do it now
            if now < next_check.get(product_id, 0):
                continue

            # Submit job, update in_flight and future_to_product
            if product_id not in in_flight_products:
                job = make_job(product)
                queue.publish(q_settings["jobs_queue"], job)
                in_flight[job["job_id"]] = (product_id, job["dispatched_ts"])
                in_flight_products.add(product_id)

        # === PHASE 2 - Harvest: Drain results until empty. ===
        drain_results(queue, q_settings, products_by_id, in_flight, in_flight_products,
                    state_store, notifiers, settings, status_data, error_counts,
                    next_check, now)

        # === PHASE 3 — Drain heartbeats ===
        drain_heartbeats(queue, q_settings, last_heartbeat)

        # === PHASE 4 — Timeout sweep ===
        sweep_timeouts(in_flight, in_flight_products, settings, now)

        # === PHASE 5 — Liveness sweep ===
        sweep_liveness(last_heartbeat, settings, now)

        # Update our snapshot - use copies to prevent race conditions
        snapshot_ref["current"] = {
            "products": dict(status_data),
            "errors_since_startup": dict(error_counts),
            "queue_depth": queue.depth(q_settings["jobs_queue"]),
            "in_flight": len(in_flight),
            "workers": {wid: round(now - msg["ts"], 1) for wid, msg in last_heartbeat.items()},
        }

        # So we don't blast thru our CPU cycles 
        time.sleep(SLEEP_INTERVAL)


def drain_results(queue, q_settings, products_by_id, in_flight, in_flight_products,
                  state_store, notifiers, settings, status_data, error_counts,
                  next_check, now):
    while True:
        got = queue.consume(q_settings["results_queue"])
        if got is None:
            break

        msg, tag = got
        queue.ack(tag)

        job_id = msg["job_id"]
        if job_id not in in_flight:
            logger.warning(f"stale result dropped: job={job_id} product={msg['product_id']} worker={msg['worker_id']}")
            continue

        # resolve which product this result belongs to
        product_id, _ = in_flight[job_id]
        product = products_by_id[product_id]

        result = CheckResult(StockStatus(msg["status"]), msg["latency_ms"], msg["error"])

        if result.status == StockStatus.UNKNOWN:
            error_counts[product["source"]] += 1

        alerted = process_and_alert(result, product, state_store, settings, notifiers, now)
        state_store.update(product_id, result.status, alerted=alerted)

        status_data[product_id] = {
            "last_status": result.status.value,
            "last_check_ts": now,
            "last_latency_ms": result.latency_ms,
        }

        logger.info(f"checked {product_id} source={product['source']} status={result.status.value} latency={result.latency_ms:.0f}ms")

        interval = product["interval_seconds"]
        next_check[product_id] = now + interval + uniform(-JITTER_AMOUNT, JITTER_AMOUNT) * interval

        # completed — release the product for future dispatch
        del in_flight[job_id]
        in_flight_products.discard(product_id)


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

def drain_heartbeats(queue, q_settings, last_heartbeat):
    while True:
        got = queue.consume(q_settings["heartbeats_queue"])
        if got is None:
            break
        msg, tag = got
        queue.ack(tag)
        last_heartbeat[msg["worker_id"]] = msg

def sweep_timeouts(in_flight, in_flight_products, settings, now):
    expired = [job_id for job_id, (pid, ts) in in_flight.items() 
               if now - ts > settings["job_timeout_seconds"]]

    for job_id in expired:
        product_id, ts = in_flight[job_id]
        logger.warning(f"job timed out: job={job_id} product={product_id} age={now - ts:.0f}s")
        del in_flight[job_id]
        in_flight_products.discard(product_id)

def sweep_liveness(last_heartbeat, settings, now):
    timeout = settings["worker_liveness_timeout_seconds"]
    evict_after = timeout * 10

    # Evict workers silent so long they're considered gone, not just stale
    dead = [worker_id for worker_id, msg in last_heartbeat.items()
            if now - msg["ts"] > evict_after]
    for worker_id in dead:
        logger.warning(f"worker removed from roster: {worker_id} silent for {now - last_heartbeat[worker_id]['ts']:.0f}s")
        del last_heartbeat[worker_id]

    # Warn about stale but not yet evicted workers
    for worker_id, msg in last_heartbeat.items():
        if now - msg["ts"] > timeout:
            logger.warning(f"worker stale: {worker_id} last_seen={now - msg['ts']:.0f}s ago")


if __name__ == "__main__":
    main()