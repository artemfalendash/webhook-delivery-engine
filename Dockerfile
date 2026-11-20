FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# requirements-dev.txt pulls in requirements.txt (-r) plus the test tools
# (pytest, pytest-asyncio, respx), so tests can run inside the container.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .
