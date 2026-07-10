from argus.adapters.base import BaseAdapter

_REGISTRY: dict[str, BaseAdapter] = {}

def register_adapter(adapter: BaseAdapter):
    """
    Register an adapter instance by its source name
    """
    _REGISTRY[adapter.source_name()] = adapter

def get_adapter(source_name: str) -> BaseAdapter:
    """
    Look up an adapter by source name

    Raises:
        KeyError if no adapter is registered
    """
    if source_name in _REGISTRY:
        return _REGISTRY[source_name]

    raise KeyError(f"adapter: {source_name} is not registered!")