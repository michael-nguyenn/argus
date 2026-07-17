from threading import Lock
import time
import random

DEFAULT_INTERVAL = 30
DEFAULT_JITTER = 5

class SiteRateLimiter:
    """
    Enforces a minimum delay b/w requests to the same site with random jitter
    to break up reg patterns.

    Thread Safe
    """
    
    def __init__(self, rate_limits: dict[str, dict[str, float]]):
        self.default_rates = {
            "min_interval_seconds": DEFAULT_INTERVAL, 
            "jitter_seconds": DEFAULT_JITTER
            
            }
        self.rate_limits = rate_limits
        self.site_requests: dict[str, float] = {} # tracks str -> timestamp of last checked
        self.lock = Lock()


    def acquire(self, site: str):
        """
        Block until it's safe to make a request to our site
        """
        
        # Lookup the site's min interval & jitter or fallback to defaults
        rates = self.rate_limits.get(site, self.default_rates)
        min_interval = rates["min_interval_seconds"]
        jitter = rates["jitter_seconds"]

        wait = 0

        with self.lock:
            last = self.site_requests.get(site, 0) # 0 means we haven't requested yet
            now = time.monotonic()
            elapsed = now - last

            wait = max(0, min_interval - elapsed) + random.uniform(0, jitter)

            # reserve the slot before sleeping
            self.site_requests[site] = now + wait

        if wait > 0:
            time.sleep(wait)