from argus.adapters.mock import MockAdapter
from argus.adapters.base import StockStatus, CheckResult


def test_mock_adapter():
    product = {
        "id": "mock-restock",
        "name": "Mock Restock",
        "source": "mock",
        "url": "n/a",
        "script": ["OUT_OF_STOCK", "IN_STOCK", "UNKNOWN"],
    }

    expected = [StockStatus.OUT_OF_STOCK, 
                StockStatus.IN_STOCK, 
                StockStatus.UNKNOWN,
                StockStatus.OUT_OF_STOCK, 
                StockStatus.IN_STOCK, 
                StockStatus.UNKNOWN]  

    mock_adapter = MockAdapter()

    for i in range(6):
        result: CheckResult = mock_adapter.check(product)
        assert result.status == expected[i]