from abc import ABC, abstractmethod

class BaseNotifier(ABC):
    """
    Abstract base class for all notification channels. 
    """

    @abstractmethod
    def notify(self, product: dict, old_status: str, new_status: str, timestamp: float) -> bool:
        """
        Send a notification about a status change.

        Args:
            product: The product config dict
            old_status: Previous status string
            new_status: New Status string
            timestamp: When the change was detected (epoch seconds)
        Returns:
            True if delivered ; False otherwise.
            Delivery Failure is treated as a return value (not an exception). The scheduler 
            will handle each notification individually.
        """
        ...