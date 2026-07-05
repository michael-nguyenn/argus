from abc import ABC, abstractmethod
from enum import Enum

class StockStatus(Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNKNOWN = "UNKNOWN"

class CheckResult:
    """
    Encapsulates the results of a single stock check.
    """
    def __init__(self, status: StockStatus, latency_ms: float, error: str | None = None):
        self.status = status
        self.latency_ms = latency_ms
        self.error = error

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
