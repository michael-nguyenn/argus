from argus.adapters.base import is_retryable, ErrorKind, CheckResult
import random
import logging
import time

logger = logging.getLogger("argus.retry")
JITTER_AMOUNT = 1

def with_retries(fn, max_attempts: int = 3, 
                 base_delay: float = 1.0, 
                 max_delay: float = 30.0) -> CheckResult:
    """
    Call fn() up to max_attemps times.

    - Retry only when is_retryable(result.error_kind)
    - HTTP_4XX, BLOCKED or PARSE won't reattempt
    - Use exponential backoff for time between attempts
    - If all attempts fail, return the final UNKNOWN with last error
    """
    for attempt in range(max_attempts):
        result: CheckResult = fn()

        if not is_retryable(result.error_kind):
            return result

        if attempt == max_attempts - 1:
            return result
        
        # Otherwise we'll retry
        if result.error_kind == ErrorKind.RATE_LIMITED and result.retry_after_s:
            delay = result.retry_after_s
        else:
            delay = min(base_delay * 2**(attempt), max_delay)
        
        delay += random.uniform(0, JITTER_AMOUNT)
        logger.info(f"retry {attempt + 1}/{max_attempts} after {result.error_kind.value}, sleeping {delay:.1f}s")        
        time.sleep(delay)
