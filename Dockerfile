FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor wget gnupg curl && \
    rm -rf /var/lib/apt/lists/*

# Install Playwright browsers for scraping fallback
RUN pip install --no-cache-dir playwright && \
    playwright install chromium --with-deps

# Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# App code
COPY . /app
WORKDIR /app

# Supervisor config
COPY supervisor.conf /etc/supervisor/conf.d/taxclarity.conf

# Cloud Run expects port 8080
EXPOSE 8080

CMD ["supervisord", "-n"]
