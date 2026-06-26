FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    bluez \
    dbus \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install bleak aiohttp

COPY govee.py .
COPY motion_controller.py .
COPY webhook_sensor.py .

CMD ["python3", "motion_controller.py", "webhook"]
