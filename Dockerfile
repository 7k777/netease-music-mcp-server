FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir mcp httpx cryptography

COPY netease_mcp_server.py .

EXPOSE 8000

CMD ["python", "netease_mcp_server.py", "--port", "8000"]
