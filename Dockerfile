FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir cryptography

COPY netease_mcp_server.py .

CMD python netease_mcp_server.py
