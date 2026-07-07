from argus.adapters.base import BaseAdapter, CheckResult, StockStatus

class MockAdapter(BaseAdapter):
    """
    Used to simulate the pipeline (scheduler -> state -> alerts -> cooldown -> discord)

    Each product carries carries a script = ["OUT_OF_STOCK", "IN_STOCK", "UKNOWN", "IN_STOCK"]. 
    Each check consumes the next entry, wrapping around product["script"] if needed.
    """

    def __init__(self):
        self.script_pos: dict[str, int] = {}

    def check(self, product: dict) -> CheckResult:
        if "script" not in product:
            raise KeyError(f"mock product '{product['id']}' has no script")
        
        if product["id"] not in self.script_pos:
            self.script_pos[product["id"]] = 0

        script_idx = self.script_pos[product["id"]]
        status = StockStatus(product["script"][script_idx])
        self.script_pos[product["id"]] = (self.script_pos[product["id"]] + 1) % len(product["script"]) # to next pos in script

        return CheckResult(status=status, latency_ms=0)
        
    def source_name(self):
        return "mock"