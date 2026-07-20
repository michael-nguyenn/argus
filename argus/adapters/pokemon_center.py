from argus.adapters.base import BaseAdapter, CheckResult

class PokemonCenterAdapter(BaseAdapter):
    def check(self, product:dict) -> CheckResult:
        ...

    def source_name(self):
        return "pokemoncenter"