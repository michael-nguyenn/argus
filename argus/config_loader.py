import yaml

REQUIRED_FIELDS = ["id", "source", "url"]
DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_COOLDOWN_MINUTES = 10

def load_config(path: str) -> dict:
    """
    Load and validate the YAML config file.
    
    Returns:
        {
            "settings": { "default_interval_seconds": int, "cooldown_minutes": int },
            "products": [ { "id": str, "name": str, "source": str, "url": str, ... }, ... ]
        }
    
    Raises:
        ValueError — if a product is missing required fields: id, source, url
    """

    # Open the file and load the data
    with open(path, 'r') as file:

        data = yaml.safe_load(file)

        # Products will be an array of dicts
        products_config = data.get('products', [])
        settings = data.get('settings', {})

        # Handle missing settings dict
        if not settings:
            settings = {
                "default_interval_seconds": DEFAULT_INTERVAL_SECONDS,
                "cooldown_minutes": DEFAULT_COOLDOWN_MINUTES
            }

            data['settings'] = settings


        # Handle missing fields
        for index, config in enumerate(products_config):
            for required_field in REQUIRED_FIELDS:
                if required_field not in config:
                    raise ValueError(f'Product {index} is missing a required field: {required_field}')
            
            # Setting Default Values
            if 'interval_seconds' not in config:
                config['interval_seconds'] = settings['default_interval_seconds']


            if 'notify' not in config:
                config['notify'] = True


    return data

