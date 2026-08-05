from dotenv import load_dotenv
import logging
import time
import argparse
import socket
import uuid
import threading
import os

# ARGUS RELATED STUFF
from argus.adapters.base import CheckResult, StockStatus, ErrorKind
from argus.adapters import register_adapter, get_adapter
from argus.adapters.pokemon_center import PokemonCenterAdapter
from argus.adapters.bestbuy import BestBuyAdapter

from argus.config_loader import load_config
from argus.rate_limiter import SiteRateLimiter
from argus.queue import JobQueue
from argus.messages import make_heartbeat, make_result
from argus.retry import with_retries


logger = logging.getLogger("argus.worker")

def worker_main():

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv()

    # Load Config
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/products.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    settings = config["settings"]

    # Set a unique worker id
    worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"

    # Register Adapters
    register_adapter(BestBuyAdapter())
    register_adapter(PokemonCenterAdapter())

    # Initialize Rate Limits
    rate_limiter = SiteRateLimiter(settings["rate_limits"])

    # Set up our Message Queue
    q_settings = settings["queue"]
    heartbeat_q: str = q_settings["heartbeats_queue"]
    jobs_q: str = q_settings["jobs_queue"]
    res_q: str = q_settings["results_queue"]

    queue_url = os.getenv("ARGUS_QUEUE_URL", q_settings["url"])
    queue = JobQueue(queue_url)

    # Set up some tracking variables
    jobs_completed = 0
    current_job_id = None

    # We're gonna get a daemon thread to run this
    def heartbeat_loop():
        queue_url = os.getenv("ARGUS_QUEUE_URL", q_settings["url"])
        hb_queue = JobQueue(queue_url)

        while True:
            hb_queue.publish(heartbeat_q, 
                             make_heartbeat(worker_id, jobs_completed, current_job_id))
            time.sleep(settings["heartbeat_interval_seconds"])

    threading.Thread(target=heartbeat_loop, daemon=True).start()

    # === MAIN WORKER LOOP ===
    while True:
        got: tuple[dict, int] | None = queue.consume(jobs_q)

        # If there are no messages in the queue we'll wait a little before looking again
        if not got:
            time.sleep(2)
            continue

        message, tag = got
        current_job_id = message["job_id"]

        # If the job is stale we'll simply drop it
        now = time.time()
        if now - message["dispatched_ts"] > settings["job_timeout_seconds"]:
            logger.warning(f"stale job dropped: {message['job_id']} product={message['product']['id']} age={now - message['dispatched_ts']:.0f}s")
            current_job_id = None
            queue.ack(tag)
            continue

        # Otherwise we'll process the job
        product = message["product"]

        try:
            result: CheckResult = check_product(product, rate_limiter)
        except Exception as e:
            logger.error(f"check for {product['id']} raised: {e}")
            result = CheckResult(
                status=StockStatus.UNKNOWN,
                latency_ms=0.0,
                error=f"worker exception: {e}",
                error_kind=ErrorKind.PARSE
            )

        queue.publish(res_q, 
                      make_result(message["job_id"], product["id"], result, worker_id))

        queue.ack(tag)
        jobs_completed += 1
        current_job_id = None
        logger.info(f"completed job={message['job_id']} product={product['id']} status={result.status.value} worker={worker_id}")

def check_product(product: dict, rate_limiter) -> CheckResult:
    """
    Runs inside a worker thread.

    Get the rate limiter for the product's site, and then call the adaptor's check().
    """
    adapter = get_adapter(product["source"])
    rate_limiter.acquire(product["source"])
    return with_retries(lambda: adapter.check(product))

if __name__ == "__main__": 
    worker_main()