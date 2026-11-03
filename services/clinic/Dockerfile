FROM python:3.12-slim
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn>=0.32" "httpx>=0.27" "psycopg[binary]>=3.2" "mcp>=2" "spiffe==0.4.0"
COPY clinic /app/clinic
WORKDIR /app
ENV PYTHONUNBUFFERED=1
