from abc import ABC, abstractmethod
from enum import Enum

class StockStatus(Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNKNOWN = "UNKNOWN"

class ErrorKind(Enum):
    NONE = "none"                      
    TIMEOUT = "timeout"                 # retryable
    CONNECTION = "connection"           # retryable
    HTTP_5XX = "http_5xx"               # retryable
    RATE_LIMITED = "rate_limited"       # HTTP 429 - retry with longer backoff
    HTTP_4XX = "http_4xx"               # not retryable
    BLOCKED = "blocked"                 # not retryable
    PARSE = "parse"                     # not retryable (200 but unrecognizable format)

RETRYABLE = {ErrorKind.TIMEOUT, ErrorKind.CONNECTION, ErrorKind.HTTP_5XX, ErrorKind.RATE_LIMITED}

def is_retryable(kind: ErrorKind) -> bool:
    return kind in RETRYABLE

class CheckResult:
    """
    Encapsulates the results of a single stock check.
    """
    def __init__(self, status: StockStatus, 
                 latency_ms: float,
                 error: str | None = None,
                 error_kind = ErrorKind.NONE,
                 retry_after_s: float | None = None):
        self.status = status
        self.latency_ms = latency_ms
        self.error = error
        self.error_kind = error_kind
        self.retry_after_s = retry_after_s

class BaseAdapter(ABC):
    """
    Abstract base class for all source adaptors.

    Each Adapter knows how to check a single retail source. The adaptor receives the product
    configuration dictionary and returns a CheckResult object.
    """

    @abstractmethod
    def check(self, product: dict) -> CheckResult:
        """
        Check the stock status of a product.
        """
        ...
    
    @abstractmethod
    def source_name(self) -> str:
        """
        Gets the string key that maps to this adaptor (e.g. "bestbuy")
        """
        ...
