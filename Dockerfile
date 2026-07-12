# Base Image
FROM python:3.11-slim

# All subsequent paths are relative to /app inside the docker container
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# After copying move the source
COPY argus/ ./argus/
CMD ["python" , "-m", "argus.main", "--config", "/config/products.yaml", "--state", "/state/state.json"]