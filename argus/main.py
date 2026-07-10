from dotenv import load_dotenv
import logging
from argus.config_loader import load_config
from argus.state_store import StateStore
from argus.adapters import register_adapter, get_adapter
from argus.adapters.mock import MockAdapter
from argus.adapters.bestbuy import BestBuyAdapter
from argus.notifiers.discord import DiscordNotifier

CONFIG_PATH = "config/products.yaml"
STATE_STORE_PATH = "state/state.json"

logger = logging.getLogger("argus")


def main():

    logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    load_dotenv()

    # Load Config
    config = load_config(CONFIG_PATH)
    products = config["products"]
    settings = config["settings"]

    # Initialize State Store
    state_store = StateStore(STATE_STORE_PATH)

    # Register Adapters
    register_adapter(MockAdapter())
    register_adapter(BestBuyAdapter())

    # Initialize Notifiers
    notifiers = []
    discord_notifier = DiscordNotifier()
    notifiers.append(discord_notifier)

    # Enter the scheduler loop
    run_scheduler(products, state_store, notifiers, settings)


def run_scheduler(products, state_store, notifiers, settings):
    ...

if __name__ == "__main__":
    main()